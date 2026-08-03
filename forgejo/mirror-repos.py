#!/usr/bin/env python3
"""Mirror a list of GitHub repositories to Forgejo.

Reads environment variables from .env and a repository list from repos-to-mirror.json.
Can also fetch all repos for a GitHub user or organization via the GitHub API.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3


def load_env():
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        sys.exit(1)

    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def require_env(name):
    value = os.environ.get(name)
    if not value:
        print(f"Error: {name} is not set in .env")
        sys.exit(1)
    return value


def github_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }


def fetch_all_pages(url, headers):
    results = []
    while url:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"  GitHub API error: {response.status_code} {response.text}")
            return results
        results.extend(response.json())
        url = response.links.get("next", {}).get("url")
    return results


def fetch_github_user(github_token):
    response = requests.get("https://api.github.com/user", headers=github_headers(github_token))
    if response.status_code == 200:
        return response.json().get("login")
    return None


def fetch_github_repos(github_owner, github_token):
    headers = github_headers(github_token)
    auth_user = fetch_github_user(github_token)

    if auth_user and auth_user.lower() == github_owner.lower():
        print(f"Fetching repos for authenticated user {github_owner} (includes private repos)...")
        url = f"https://api.github.com/user/repos?affiliation=owner&per_page=100"
        return fetch_all_pages(url, headers)

    print(f"Fetching repos for {github_owner}...")
    url = f"https://api.github.com/users/{github_owner}/repos?per_page=100"
    repos = fetch_all_pages(url, headers)
    if repos:
        return repos

    print(f"Trying organization endpoint for {github_owner}...")
    url = f"https://api.github.com/orgs/{github_owner}/repos?per_page=100"
    return fetch_all_pages(url, headers)


def clone_addr(github_url):
    if not github_url.endswith(".git"):
        github_url += ".git"
    return github_url


def forgejo_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def requests_verify():
    value = os.environ.get("FORGEJO_VERIFY_SSL", "true").lower()
    return value not in ("false", "0", "no", "off")


def repo_exists(base_url, owner, repo, token):
    url = urljoin(base_url, f"/api/v1/repos/{owner}/{repo}")
    response = requests.get(url, headers=forgejo_headers(token), verify=requests_verify())
    return response.status_code == 200


def migrate_repo(base_url, forgejo_owner, repo_name, github_url, github_token, forgejo_token, interval, private):
    url = urljoin(base_url, "/api/v1/repos/migrate")
    payload = {
        "clone_addr": clone_addr(github_url),
        "auth_token": github_token,
        "repo_name": repo_name,
        "repo_owner": forgejo_owner,
        "mirror": True,
        "interval": interval,
        "private": private,
        "wiki": True,
        "milestones": True,
        "labels": True,
        "issues": True,
        "pull_requests": True,
        "releases": True,
    }

    response = requests.post(url, headers=forgejo_headers(forgejo_token), json=payload, verify=requests_verify())
    if response.status_code == 201:
        return True, None
    return False, response.text


def load_repos_from_file(repos_file):
    if not repos_file.exists():
        return []

    with repos_file.open() as f:
        data = json.load(f)

    if not isinstance(data, list):
        print(f"Error: {repos_file} should contain a JSON list")
        sys.exit(1)

    return data


def repos_from_github(github_owner, github_token):
    github_repos = fetch_github_repos(github_owner, github_token)
    return [
        {
            "github_url": repo["clone_url"],
            "forgejo_name": repo["name"],
            "private": repo["private"],
        }
        for repo in github_repos
    ]


def merge_repos(file_repos, github_repos):
    seen = set()
    merged = []

    for repo in file_repos + github_repos:
        github_url = repo.get("github_url")
        repo_name = repo.get("forgejo_name") or github_url.rstrip("/").split("/")[-1]

        if repo_name in seen:
            continue

        seen.add(repo_name)
        merged.append({
            "github_url": github_url,
            "forgejo_name": repo_name,
            "private": repo.get("private", False),
        })

    return merged


def main():
    parser = argparse.ArgumentParser(description="Mirror GitHub repositories to Forgejo")
    parser.add_argument(
        "--github-owner",
        help="GitHub user or organization whose repos should be mirrored",
    )
    parser.add_argument(
        "--repos-file",
        type=Path,
        default=Path(__file__).with_name("repos-to-mirror.json"),
        help="JSON file listing repos to mirror",
    )
    args = parser.parse_args()

    load_env()

    if not requests_verify():
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    github_token = require_env("GITHUB_TOKEN")
    forgejo_url = require_env("FORGEJO_ROOT_URL")
    forgejo_token = require_env("FORGEJO_TOKEN")
    forgejo_owner = require_env("FORGEJO_OWNER")
    interval = os.environ.get("MIRROR_INTERVAL", "8h")
    github_owner = args.github_owner or os.environ.get("GITHUB_OWNER")

    file_repos = load_repos_from_file(args.repos_file)
    github_repos = repos_from_github(github_owner, github_token) if github_owner else []
    repos = merge_repos(file_repos, github_repos)

    if not repos:
        print("No repositories to mirror. Add entries to repos-to-mirror.json or set GITHUB_OWNER.")
        return

    created = []
    skipped = []
    failed = []

    for repo in repos:
        github_url = repo.get("github_url")
        repo_name = repo.get("forgejo_name")
        private = repo.get("private", False)

        if not github_url or not repo_name:
            print("Skipping entry with missing github_url or forgejo_name")
            continue

        print(f"Processing {repo_name}...")

        if repo_exists(forgejo_url, forgejo_owner, repo_name, forgejo_token):
            skipped.append(repo_name)
            print(f"  Skipped: {repo_name} already exists in Forgejo")
            continue

        ok, error = migrate_repo(
            forgejo_url,
            forgejo_owner,
            repo_name,
            github_url,
            github_token,
            forgejo_token,
            interval,
            private,
        )

        if ok:
            created.append(repo_name)
            print(f"  Created mirror: {repo_name}")
        else:
            failed.append((repo_name, error))
            print(f"  Failed to create mirror: {repo_name}")
            print(f"    {error}")

    print()
    print(f"Created: {len(created)}")
    print(f"Skipped: {len(skipped)}")
    print(f"Failed: {len(failed)}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

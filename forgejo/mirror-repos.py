#!/usr/bin/env python3
"""Mirror a list of GitHub repositories to Forgejo.

Reads environment variables from .env and a repository list from repos-to-mirror.json.
"""

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


def migrate_repo(base_url, forgejo_owner, repo_name, github_url, github_token, interval, private):
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


def main():
    load_env()

    if not requests_verify():
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    github_token = require_env("GITHUB_TOKEN")
    forgejo_url = require_env("FORGEJO_ROOT_URL")
    forgejo_token = require_env("FORGEJO_TOKEN")
    forgejo_owner = require_env("FORGEJO_OWNER")
    interval = os.environ.get("MIRROR_INTERVAL", "8h")

    repos_file = Path(__file__).with_name("repos-to-mirror.json")
    if not repos_file.exists():
        print(f"Error: repos-to-mirror.json not found at {repos_file}")
        sys.exit(1)

    with repos_file.open() as f:
        repos = json.load(f)

    if not repos:
        print("No repositories listed in repos-to-mirror.json")
        return

    created = []
    skipped = []
    failed = []

    for repo in repos:
        github_url = repo.get("github_url")
        repo_name = repo.get("forgejo_name") or github_url.rstrip("/").split("/")[-1]
        private = repo.get("private", False)

        if not github_url:
            print("Skipping entry with missing github_url")
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

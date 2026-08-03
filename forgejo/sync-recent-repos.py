#!/usr/bin/env python3
"""Sync only GitHub repos that have commits by you since the last run.

Avoids Forgejo's mirror polling by checking GitHub explicitly, then triggering
a mirror sync (or creating the mirror) only when needed.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
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


def forgejo_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def requests_verify():
    value = os.environ.get("FORGEJO_VERIFY_SSL", "true").lower()
    return value not in ("false", "0", "no", "off")


def default_since():
    lookback_days = int(os.environ.get("SYNC_LOOKBACK_DAYS", "7"))
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    return since.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_repos(repos_file):
    if not repos_file.exists():
        return []

    with repos_file.open() as f:
        data = json.load(f)

    if not isinstance(data, list):
        print(f"Error: {repos_file} should contain a JSON list")
        sys.exit(1)

    return data


def load_state(state_file):
    if not state_file.exists():
        return {"repos": {}}

    with state_file.open() as f:
        return json.load(f)


def save_state(state_file, state):
    with state_file.open("w") as f:
        json.dump(state, f, indent=2)


def parse_repo_url(url):
    url = url.rstrip("/").replace(".git", "")
    parts = url.split("/")
    return parts[-2], parts[-1]


def has_recent_commits(repo_owner, repo_name, github_user, github_token, since):
    query = f"repo:{repo_owner}/{repo_name} author:{github_user} author-date:>{since}"
    url = "https://api.github.com/search/commits"
    params = {"q": query, "per_page": 1}

    try:
        response = requests.get(url, headers=github_headers(github_token), params=params)
        if response.status_code != 200:
            print(f"    GitHub API error: {response.status_code} {response.text}")
            return False
        return response.json().get("total_count", 0) > 0
    except requests.RequestException as e:
        print(f"    GitHub request failed: {e}")
        return False


def repo_exists(forgejo_url, forgejo_owner, repo_name, forgejo_token):
    url = urljoin(forgejo_url, f"/api/v1/repos/{forgejo_owner}/{repo_name}")
    try:
        response = requests.get(url, headers=forgejo_headers(forgejo_token), verify=requests_verify())
        return response.status_code == 200
    except requests.RequestException:
        return False


def create_mirror(forgejo_url, forgejo_owner, repo_name, github_url, github_token, forgejo_token, private):
    url = urljoin(forgejo_url, "/api/v1/repos/migrate")
    payload = {
        "clone_addr": github_url if github_url.endswith(".git") else github_url + ".git",
        "auth_token": github_token,
        "repo_name": repo_name,
        "repo_owner": forgejo_owner,
        "mirror": True,
        "interval": "8760h",  # once per year, we trigger sync manually
        "private": private,
        "wiki": True,
        "milestones": True,
        "labels": True,
        "issues": True,
        "pull_requests": True,
        "releases": True,
    }

    try:
        response = requests.post(url, headers=forgejo_headers(forgejo_token), json=payload, verify=requests_verify())
        return response.status_code == 201, response.text
    except requests.RequestException as e:
        return False, str(e)


def trigger_mirror_sync(forgejo_url, forgejo_owner, repo_name, forgejo_token):
    url = urljoin(forgejo_url, f"/api/v1/repos/{forgejo_owner}/{repo_name}/mirror-sync")
    try:
        response = requests.post(url, headers=forgejo_headers(forgejo_token), verify=requests_verify())
        return response.status_code in (200, 201, 202), response.text
    except requests.RequestException as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Sync GitHub repos to Forgejo only when you have new commits")
    parser.add_argument(
        "--repos-file",
        type=Path,
        default=Path(__file__).with_name("frequent-repos.json"),
        help="JSON file listing repos to watch",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(__file__).with_name("sync-state.json"),
        help="File to store last sync timestamps",
    )
    args = parser.parse_args()

    load_env()

    if not requests_verify():
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    github_token = require_env("GITHUB_TOKEN")
    forgejo_url = require_env("FORGEJO_ROOT_URL")
    forgejo_token = require_env("FORGEJO_TOKEN")
    forgejo_owner = require_env("FORGEJO_OWNER")
    github_user = require_env("GITHUB_OWNER")

    repos = load_repos(args.repos_file)
    state = load_state(args.state_file)

    if not repos:
        print("No repos listed in frequent-repos.json. Nothing to do.")
        return

    created = []
    synced = []
    unchanged = []
    failed = []

    for repo in repos:
        github_url = repo.get("github_url")
        repo_name = repo.get("forgejo_name") or github_url.rstrip("/").split("/")[-1]
        private = repo.get("private", False)

        if not github_url or not repo_name:
            print("Skipping entry with missing github_url or forgejo_name")
            continue

        repo_state = state["repos"].get(repo_name, {})
        since = repo_state.get("last_sync", default_since())

        gh_owner, gh_name = parse_repo_url(github_url)
        print(f"Checking {repo_name} since {since}...")

        try:
            changed = has_recent_commits(gh_owner, gh_name, github_user, github_token, since)
        except Exception as e:
            print(f"  Failed to check GitHub: {e}")
            failed.append((repo_name, f"GitHub check failed: {e}"))
            continue

        if not changed:
            unchanged.append(repo_name)
            print(f"  No new commits by you.")
            continue

        print(f"  New commits found. Syncing...")

        if not repo_exists(forgejo_url, forgejo_owner, repo_name, forgejo_token):
            ok, error = create_mirror(
                forgejo_url,
                forgejo_owner,
                repo_name,
                github_url,
                github_token,
                forgejo_token,
                private,
            )
            if ok:
                created.append(repo_name)
                print(f"  Created mirror in Forgejo.")
            else:
                failed.append((repo_name, f"Create mirror failed: {error}"))
                print(f"  Failed to create mirror: {error}")
                continue
        else:
            ok, error = trigger_mirror_sync(forgejo_url, forgejo_owner, repo_name, forgejo_token)
            if ok:
                synced.append(repo_name)
                print(f"  Triggered mirror sync.")
            else:
                failed.append((repo_name, f"Mirror sync failed: {error}"))
                print(f"  Failed to trigger sync: {error}")
                continue

        state["repos"][repo_name] = {"last_sync": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

    save_state(args.state_file, state)

    print()
    print(f"Created: {len(created)}")
    print(f"Synced: {len(synced)}")
    print(f"Unchanged: {len(unchanged)}")
    print(f"Failed: {len(failed)}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

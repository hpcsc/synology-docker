#!/usr/bin/env python3
"""Disable mirroring on all Forgejo repositories for a given owner.

Useful if you want to switch from automatic mirrors to manual sync.
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


def forgejo_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def requests_verify():
    value = os.environ.get("FORGEJO_VERIFY_SSL", "true").lower()
    return value not in ("false", "0", "no", "off")


def fetch_all_pages(url, headers, verify):
    results = []
    while url:
        response = requests.get(url, headers=headers, verify=verify)
        if response.status_code != 200:
            print(f"Error fetching repos: {response.status_code} {response.text}")
            sys.exit(1)
        results.extend(response.json())
        url = response.links.get("next", {}).get("url")
    return results


def list_repos(forgejo_url, owner, token, verify):
    url = urljoin(forgejo_url, f"/api/v1/users/{owner}/repos?limit=100")
    repos = fetch_all_pages(url, forgejo_headers(token), verify)
    if repos:
        return repos

    url = urljoin(forgejo_url, f"/api/v1/orgs/{owner}/repos?limit=100")
    return fetch_all_pages(url, forgejo_headers(token), verify)


def disable_mirror(forgejo_url, owner, repo_name, token, verify):
    url = urljoin(forgejo_url, f"/api/v1/repos/{owner}/{repo_name}")
    payload = {"mirror": False}
    response = requests.patch(url, headers=forgejo_headers(token), json=payload, verify=verify)
    return response.status_code == 200, response.text


def main():
    load_env()

    if not requests_verify():
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    forgejo_url = require_env("FORGEJO_ROOT_URL")
    forgejo_token = require_env("FORGEJO_TOKEN")
    forgejo_owner = require_env("FORGEJO_OWNER")
    verify = requests_verify()

    print(f"Fetching repos for {forgejo_owner}...")
    repos = list_repos(forgejo_url, forgejo_owner, forgejo_token, verify)

    mirrors = [repo for repo in repos if repo.get("mirror")]

    if not mirrors:
        print("No mirrored repositories found.")
        return

    print(f"Found {len(mirrors)} mirrored repo(s).")

    disabled = []
    failed = []

    for repo in mirrors:
        repo_name = repo["name"]
        print(f"Disabling mirror for {repo_name}...")

        ok, error = disable_mirror(forgejo_url, forgejo_owner, repo_name, forgejo_token, verify)
        if ok:
            disabled.append(repo_name)
            print(f"  Disabled mirror.")
        else:
            failed.append((repo_name, error))
            print(f"  Failed: {error}")

    print()
    print(f"Disabled: {len(disabled)}")
    print(f"Failed: {len(failed)}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

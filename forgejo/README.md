# Forgejo

Self-hosted Git service on Synology.

## First-time setup

1. On the Synology, create the host directory. The path is derived from `DOCKER_DATA_PATH` in `.env`:

```bash
mkdir -p /volume1/docker/forgejo/data
```

2. Copy and edit the environment file:

```bash
cp .env.example .env
```

3. The default `USER_UID=1026` and `USER_GID=100` match a typical first Synology user. Run `id` on your Synology and update `.env` if your user has different values.

4. Start the stack:

```bash
docker compose up -d
```

5. Open `http://<synology-ip>:3000` and complete the web installer.

## Reverse proxy

For HTTPS, configure Synology's Application Portal / Reverse Proxy. The source should match your `FORGEJO_ROOT_URL`:

- Source: `https://penguin-nas:4000`
- Destination: `http://localhost:3000` on port 3000

Enable WebSocket support if you plan to use the web IDE or live features.

## SSH access

Map external port `2222` to container port `22`. Users clone via:

```bash
git clone ssh://git@penguin-nas:2222/<user>/<repo>.git
```

Port 2222 is used instead of 22 to avoid conflicting with Synology DSM SSH.

## Backup

With SQLite, everything lives in one directory:

```text
${DOCKER_DATA_PATH}/forgejo/data/
├── gitea/
│   ├── gitea.db      # SQLite database
│   ├── conf/app.ini  # Forgejo configuration
│   └── repositories/ # Git repositories
├── attachments/    # issue attachments
└── avatars/        # user avatars
```

Back up the entire `${DOCKER_DATA_PATH}/forgejo/data` directory. The compose file is in Git.

## Mirror GitHub repositories

Fill in the mirroring values in `.env`.

### Mirror specific repos

List the repos in `repos-to-mirror.json`:

```json
[
  {
    "github_url": "https://github.com/your-username/your-repo",
    "forgejo_name": "your-repo",
    "private": false
  }
]
```

Then run:

```bash
python3 mirror-repos.py
```

### Mirror all repos for a user or organization

Set `GITHUB_OWNER` in `.env`:

```bash
GITHUB_OWNER=your-username
```

Then run:

```bash
python3 mirror-repos.py
```

If the `GITHUB_OWNER` matches the owner of the GitHub token, private repos are included. For other users, only public repos are fetched. Organizations include repos the token can access.

You can also pass the owner on the command line:

```bash
python3 mirror-repos.py --github-owner your-username
```

### Requirements

- Python 3
- `requests` (`pip install requests` if missing)

For private GitHub repos, use a classic personal access token with `repo` scope or a fine-grained token with read access to the repos.

The script skips repos that already exist in Forgejo. It sets each imported repo as a pull mirror with the interval from `MIRROR_INTERVAL`.

If your Forgejo instance uses a self-signed certificate (common with Synology reverse proxy), set `FORGEJO_VERIFY_SSL=false` in `.env`.

### Auto-mirror new repos on a schedule

The script only creates mirrors. Forgejo handles syncing existing mirrors on its own. If you want new repos added to `repos-to-mirror.json` to be created automatically without running the script manually, schedule it on Synology.

1. Open **Control Panel → Task Scheduler**.
2. Click **Create → Scheduled Task → User-defined script**.
3. Under **General**:
   - Task name: `forgejo-mirror-new-repos`
   - User: `root`
4. Under **Schedule**:
   - Run daily at a quiet time, e.g. `04:00`.
5. Under **Task Settings**:
   - Run command:
     ```bash
     cd /volume1/docker/synology-docker/forgejo
     python3 mirror-repos.py >> /var/log/forgejo-mirror.log 2>&1
     ```

Because the script skips repos that already exist, it is safe to run daily. It will only create mirrors for newly added entries in `repos-to-mirror.json`.

## Update

Run the provided update script from the `forgejo` directory:

```bash
./update.sh
```

The script will:

1. Stop Forgejo.
2. Back up the data directory with a timestamp.
3. Pull the latest image.
4. Restart Forgejo.
5. Clean up old images.

If something goes wrong, restore the backup it created and run `docker compose up -d`.

For major version updates, read the Forgejo release notes first.

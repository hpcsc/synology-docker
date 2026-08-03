# Synology Docker

Declarative Docker stacks for Synology NAS, one folder per app.

## Layout

```
.
├── README.md
├── forgejo/
│   ├── docker-compose.yml
│   └── .env.example
└── ... more apps
```

## How to deploy

1. Clone this repo onto your Synology, e.g.:

```bash
cd /volume1/docker
git clone https://github.com/<your-user>/synology-docker.git
```

2. For each app, copy `.env.example` to `.env` and fill in the values.

```bash
cd synology-docker/forgejo
cp .env.example .env
# edit .env with your settings
```

3. Create the host directory on Synology. The path is derived from `DOCKER_DATA_PATH` in `.env`:

```bash
mkdir -p /volume1/docker/forgejo/data
```

4. Start the stack.

```bash
docker compose up -d
```

No Portainer is required; these are plain Docker Compose files managed by Synology Container Manager or the Docker CLI.

## Backup

Back up the persistent bind mounts under `${DOCKER_DATA_PATH}/<app>/`. The compose files are already in Git.

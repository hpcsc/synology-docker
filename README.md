# Synology Docker

Declarative Docker stacks for Synology NAS, one folder per app.

## Layout

```
.
├── README.md
├── forgejo/
│   ├── docker-compose.yml
│   ├── .env.example
│   └── scripts/        # mirroring helpers
└── ... more apps
```

## How to deploy

There are two ways to deploy: via [Ansible](ansible/README.md) (recommended) or manually.

<details open>
<summary>Ansible (recommended)</summary>

Deployment is automated with [Ansible](ansible/README.md). It clones this repo onto the NAS, renders the `.env` files from [fnox](https://fnox.jdx.dev/)-injected secrets, creates the data directory, starts the stacks, and registers the DSM scheduled tasks.

From the repo root:

```bash
task deps      # install Ansible (mise) + collections
task secrets   # store the GitHub and Forgejo tokens in fnox
task deploy    # apply
task dry-run   # preview with --check
```

See [`ansible/README.md`](ansible/README.md) for the one-time SSH setup, the secrets flow, and Synology notes.

</details>

<details>
<summary>Manual deployment</summary>

1. Clone this repo onto your Synology, e.g.:

```bash
cd /volume1/docker
git clone https://github.com/<your-user>/synology-docker.git
```

2. For each app, copy `.env.example` to `.env` and fill in the values. Apps with mirror scripts also have a `scripts/.env.example`.

```bash
cd synology-docker/forgejo
cp .env.example .env
cp scripts/.env.example scripts/.env   # only if you use the mirror scripts
```

3. Create the host directory on Synology. The path is derived from `DOCKER_DATA_PATH` in `.env`:

```bash
mkdir -p /volume1/docker/forgejo/data
```

4. Start the stack.

```bash
docker compose up -d
```

</details>

No Portainer is required; these are plain Docker Compose files managed by Synology Container Manager or the Docker CLI.

## Backup

Back up the persistent bind mounts under `${DOCKER_DATA_PATH}/<app>/`. The compose files are already in Git.

# Ansible

Declarative deployment of the Docker stacks in this repo onto a Synology NAS.

Secrets (the GitHub and Forgejo tokens) are **not** stored in Ansible. They come
from [fnox](https://fnox.jdx.dev/) at run time, injected as environment
variables by wrapping the playbook:

```bash
fnox exec -- ansible-playbook -i inventory/hosts.yml site.yml
```

A `Taskfile.yml` at the repo root wraps these as `task` commands (run from the
repo root):

```bash
task deploy     # apply
task dry-run    # preview with --check
task check      # syntax-check only (no NAS, no secrets)
task deps       # install ansible (mise) + collections
task secrets    # set the GitHub and Forgejo tokens in fnox
```

## What it does

1. Clones (or fast-forward pulls) this repo onto the NAS.
2. Renders `forgejo/.env` (container) and `forgejo/scripts/.env` (mirroring),
   pulling the GitHub and Forgejo tokens from the fnox-injected environment.
3. Creates the Forgejo data directory.
4. Runs `docker compose up -d`.
5. Creates a **UI-visible** Synology Task Scheduler job
   (`forgejo-mirror-new-repos`) that mirrors new repos, by writing
   `/usr/syno/etc/synoschedule.d/root/<id>.task` and running
   `synoschedtask --sync`.

## Prerequisites: SSH access to the NAS

Ansible connects over SSH as `macmini-ssh` on port `1122`. Do this once:

1. **Enable SSH** — Control Panel → Terminal & SNMP → Terminal → check *Enable
   SSH service* (port `1122`).
2. **Admin-group user** — DSM only permits SSH (and `sudo`, which `become`
   needs) for members of the `administrators` group, so `macmini-ssh` must be in
   it.
3. **Key-based auth** from your Mac:

   ```bash
   ssh-copy-id -p 1122 macmini-ssh@penguin-nas
   ```

   Or manually: append `~/.ssh/id_ed25519.pub` to `~/.ssh/authorized_keys` on
   the NAS, then `chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys`.
4. **Verify**:

   ```bash
   ssh -p 1122 macmini-ssh@penguin-nas 'sudo -n true'
   ```

   If `sudo -n true` fails, sudo needs a password — set `ansible_become_password`
   in the inventory.

## Setup

1. Install Ansible and the collection (`task deps` does both):

   ```bash
   task deps
   ```

2. Configure fnox on this machine with two secrets named exactly
   `SYNOLOGY_DOCKER_GITHUB_TOKEN` and `SYNOLOGY_DOCKER_FORGEJO_TOKEN` (any provider; see fnox docs).

3. Push this repo to a git remote the NAS can reach, then set `repo_url` in
   `group_vars/all.yml`.

4. Edit `inventory/hosts.yml` (NAS host/user) and `group_vars/all.yml`
   (`forgejo_owner`, `github_owner`, and any paths/domains).

5. Run:

   ```bash
   fnox exec -- ansible-playbook -i inventory/hosts.yml site.yml
   ```

## How the secrets flow

```
fnox exec -- ansible-playbook site.yml
        │  fnox resolves SYNOLOGY_DOCKER_{GITHUB,FORGEJO}_TOKEN and exports them
        ▼
lookup('env', 'SYNOLOGY_DOCKER_GITHUB_TOKEN')   (evaluated on the control machine)
        ▼
template  ->  forgejo/scripts/.env  (on the NAS, mode 0600)
```

The playbook fails fast if either token is missing — that's the signal to run
through `fnox exec`. As noted elsewhere, the tokens still end up plaintext in
`forgejo/scripts/.env` on the NAS (and the GitHub token inside Forgejo's own
database); fnox removes plaintext from the repo and your laptop, not from the NAS.

## Synology notes

- **Python on the NAS**: Ansible modules need Python 3.9+ on the target, but DSM 7
  ships 3.8 (`/usr/bin/python3`). Install a 3.9+ Python (Entware or SynoCommunity)
  and set `ansible_python_interpreter` in the inventory to its path — this repo
  already points at `/usr/local/bin/python3.9`.
- **Docker Compose**: the `docker` CLI lives at `/usr/local/bin/docker` on
  Synology (set via `docker_cli` in group_vars). `docker compose` (v2 plugin) is
  assumed; if DSM only has the standalone `docker-compose` (v1), switch the
  compose command in the playbook.
- **git**: the NAS needs the `git` CLI (present on DSM 7 by default).
- **Scheduled tasks**: the `.task` file format is DSM 7's (reverse-engineered).
  If a task does not appear or run correctly, open Control Panel → Task
  Scheduler to check, and compare against the reference helper at
  <https://github.com/iamjairo/SYNO-dsm-task-scheduler-skill>.
- **Task ids**: `scheduled_tasks[].id` must be unique on the NAS; the defaults
  (91, 92) sit above the ids the GUI typically hands out.
- **become**: the playbook runs as root via `sudo`. `task deploy`/`task dry-run`
  pass `--ask-become-pass`, so Ansible prompts for the sudo password. For
  unattended runs, either configure passwordless sudo for the user on the NAS,
  or set `ansible_become_password` in the inventory (keep it out of git).

#!/bin/sh
set -e

# Load environment variables from .env
if [ ! -f .env ]; then
  echo "Error: .env file not found. Copy .env.example to .env and configure it first."
  exit 1
fi

set -a
. ./.env
set +a

BACKUP_DIR="${DOCKER_DATA_PATH}/forgejo/data-backup-$(date +%Y%m%d-%H%M%S)"

echo "Stopping Forgejo for a clean backup..."
docker compose down

echo "Backing up Forgejo data to ${BACKUP_DIR}..."
cp -r "${DOCKER_DATA_PATH}/forgejo/data" "${BACKUP_DIR}"

echo "Pulling the latest image..."
docker compose pull

echo "Starting Forgejo with the new image..."
docker compose up -d

echo "Cleaning up old images..."
docker image prune -f

echo ""
echo "Update complete. Forgejo should be running at https://${FORGEJO_DOMAIN}"
echo "If something went wrong, restore the backup: ${BACKUP_DIR}"

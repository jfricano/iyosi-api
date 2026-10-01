#!/bin/sh
# Install a reviewed root-owned copy as /usr/local/lib/app-backup-hooks/iyosi-snapshot.
set -eu
if [ "$#" -ne 1 ] || [ ! -d "$1" ]; then
    echo 'Usage: iyosi-snapshot STAGING_DIRECTORY' >&2
    exit 2
fi
cd "${IYOSI_DEPLOY_DIR:-/srv/apps/iyosi}"
export COMPOSE_FILE=compose.shared.yaml
export IYOSI_ENV_FILE=${IYOSI_ENV_FILE:-/etc/apps/iyosi/iyosi.env}
timeout 15m sh scripts/backup_db.sh "$1/iyosi-postgis.dump"

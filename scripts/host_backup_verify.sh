#!/bin/sh
# Install a reviewed root-owned copy as /usr/local/lib/app-backup-hooks/iyosi-verify.
set -eu
if [ "$#" -ne 1 ] || [ ! -f "$1/iyosi-postgis.dump" ]; then
    echo 'Usage: iyosi-verify STAGING_DIRECTORY (containing iyosi-postgis.dump)' >&2
    exit 2
fi
cd "${IYOSI_DEPLOY_DIR:-/srv/apps/iyosi}"
export COMPOSE_FILE=compose.shared.yaml
export IYOSI_ENV_FILE=${IYOSI_ENV_FILE:-/etc/apps/iyosi/iyosi.env}
timeout 20m sh scripts/verify_restore.sh "$1/iyosi-postgis.dump"

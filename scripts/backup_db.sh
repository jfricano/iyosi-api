#!/bin/sh
# Usage: scripts/backup_db.sh /secure/off-host-staging/backup.dump
# COMPOSE_FILE and IYOSI_ENV_FILE select the Compose stack and its credentials.
set -eu
umask 077
compose() { docker compose --env-file "${IYOSI_ENV_FILE:-.env}" "$@"; }

if [ "$#" -ne 1 ]; then
    echo 'Usage: scripts/backup_db.sh DESTINATION.dump' >&2
    exit 2
fi
destination=$1
if [ -e "$destination" ]; then
    echo "Refusing to overwrite $destination" >&2
    exit 2
fi
directory=$(dirname "$destination")
if [ ! -d "$directory" ]; then
    echo "Directory does not exist: $directory" >&2
    exit 2
fi
temporary=$(mktemp "$directory/.iyosi-backup.XXXXXX")
trap 'rm -f "$temporary"' EXIT HUP INT TERM

compose exec -T db sh -ec 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' > "$temporary"
compose exec -T db pg_restore --list < "$temporary" > /dev/null
mv "$temporary" "$destination"
trap - EXIT HUP INT TERM
echo "Backup created: $destination"

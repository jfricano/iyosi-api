#!/bin/sh
# Restores a custom-format dump into a new, disposable database and checks key schema/data.
set -eu
compose() { docker compose --env-file "${IYOSI_ENV_FILE:-.env}" "$@"; }

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
    echo 'Usage: scripts/verify_restore.sh BACKUP.dump' >&2
    exit 2
fi
backup=$1
restore_name="iyosi_restore_$(date -u +%Y%m%d%H%M%S)_$$"
created=0
cleanup() {
    if [ "$created" -eq 1 ]; then
        compose exec -T -e RESTORE_DB_NAME="$restore_name" db sh -ec 'dropdb -U "$POSTGRES_USER" --if-exists --force "$RESTORE_DB_NAME"' >&2
    fi
}
trap cleanup EXIT HUP INT TERM

compose exec -T -e RESTORE_DB_NAME="$restore_name" db sh -ec 'createdb -U "$POSTGRES_USER" -T template0 "$RESTORE_DB_NAME"'
created=1
compose exec -T -e RESTORE_DB_NAME="$restore_name" db sh -ec 'pg_restore --exit-on-error --no-owner --no-acl -U "$POSTGRES_USER" -d "$RESTORE_DB_NAME"' < "$backup"
compose exec -T -e RESTORE_DB_NAME="$restore_name" db sh -ec 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$RESTORE_DB_NAME"' <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '001_initial.sql') THEN
    RAISE EXCEPTION 'base migration missing';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM ncr_boundary WHERE id = 1 AND ST_IsValid(geom)) THEN
    RAISE EXCEPTION 'valid NCR boundary missing';
  END IF;
  PERFORM 1 FROM accounts LIMIT 1;
  PERFORM 1 FROM places LIMIT 1;
  PERFORM 1 FROM moderation_cases LIMIT 1;
END $$;
SQL
echo "Restore verified in disposable database $restore_name"

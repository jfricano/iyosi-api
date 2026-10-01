#!/bin/sh
# Run once, with the migration database credential, before an API rollout.
set -eu
cd "$(dirname "$0")/.."
python scripts/migrate.py
python scripts/load_boundary.py infra/db/ncr_boundary.geojson 'geoBoundaries gbOpen PHL ADM1 simplified, shapeID 36201628B69282955287113, CC BY 3.0 IGO'
if [ -n "${IYOSI_APP_DB_USER:-}" ]; then
    python scripts/provision_runtime_role.py
fi

#!/bin/sh
set -eu
cd /workspace
python scripts/migrate.py
python scripts/load_boundary.py infra/db/ncr_boundary.geojson 'geoBoundaries gbOpen PHL ADM1 simplified, shapeID 36201628B69282955287113, CC BY 3.0 IGO'
exec uvicorn api.main:app --host 0.0.0.0 --port 8000 --no-access-log

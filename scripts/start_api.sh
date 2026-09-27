#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
sh scripts/prepare_db.sh
exec sh scripts/serve_api.sh

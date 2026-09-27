#!/bin/sh
# Runtime starts with an already prepared database and no schema privileges.
set -eu
cd "$(dirname "$0")/.."
trusted_proxy_ips=${IYOSI_TRUSTED_PROXY_IPS:-127.0.0.1}
if [ "$trusted_proxy_ips" = '*' ]; then
    echo 'Refusing to trust forwarded headers from every peer' >&2
    exit 2
fi
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --proxy-headers --forwarded-allow-ips "$trusted_proxy_ips" --no-access-log

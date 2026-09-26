FROM postgres:17-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-postgis-3 \
    && rm -rf /var/lib/apt/lists/*

COPY infra/db/init.sql /docker-entrypoint-initdb.d/10-postgis.sql


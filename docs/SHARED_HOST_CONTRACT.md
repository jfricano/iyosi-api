# iYosi shared-host deployment contract

This is a **deployment candidate**, not a live service. It targets one ARM64-capable host shared with Roost and Lontra Creek. Only the iYosi API joins the shared ingress network; PostGIS stays on iYosi's private network and volume. Keep the existing Personal Treasury service separate. The host operator owns the ingress, schedules, encrypted off-host copies, alerts, DNS, and capacity test. Real place data and policy gates in [backend v1 delivery](BACKEND_V1_DELIVERY.md) still apply.

## Images, network, resources

Build `infra/api/Dockerfile` as `IYOSI_API_IMAGE` and `infra/db/Dockerfile` as `IYOSI_DB_IMAGE`, preferably pinned by digest after validation. Both use multi-architecture Debian images and were validated with `linux/arm64` builds. The API image is Python 3.12, runs as UID 10001 with a read-only root filesystem, and listens on **container port 8000**. The DB image is PostgreSQL 17 with PostGIS and listens on **private container port 5432**. There are no published host ports in [`compose.shared.yaml`](../compose.shared.yaml).

The host creates an external Docker network named by `IYOSI_EDGE_NETWORK` (`edge-iyosi` in the proposed Oracle ingress); only Caddy and the iYosi API join it. Proxy to `iyosi-api:8000` using the API's network alias. The `data` network is Compose-private to iYosi; only the API, migration job, and DB use it. PostgreSQL's named `postgres_data` volume is persistent and must be sized/monitored on the host. No other application gets this network or volume. Ingress must supply HTTPS and **replace** incoming `X-Forwarded-For` and `X-Forwarded-Proto` with the observed client IP and scheme. Set `IYOSI_TRUSTED_PROXY_IPS` to Caddy's **exact address** on `edge-iyosi`; the host must reserve that address so it stays valid after container recreation. Do not use `*` or a broad network containing other applications. Uvicorn ignores forwarded headers from untrusted peers. Verify client-IP rate buckets through the real ingress before accepting user traffic.

Initial container caps: API **0.5 CPU / 512 MiB**, DB **0.5 CPU / 1.5 GiB**, and one-shot migration **0.5 CPU / 512 MiB** while the API is stopped or not yet started. API plus DB are capped at the proposed 2 GiB iYosi budget. All three containers cap local JSON logs at 3 × 10 MiB each. API and DB get 30 seconds to stop cleanly. `/health` returns success only when the signing key, database, and NCR boundary are ready. These are ceilings for a small pilot, not measured reservations or a guarantee that the 2 OCPU / 12 GiB Oracle A1 host has enough headroom beside Lontra and Roost. The infrastructure lead owns a combined load and restore soak before choosing the host.

## Environment names

Use a host-only `.env.shared` file, mode `0600`, outside Git. Values below are **names only**; generate distinct high-entropy secrets. Hex database passwords avoid URL-encoding problems in Compose connection strings.

| Name | Purpose |
| --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Private DB name and migration/backup login. |
| `IYOSI_APP_DB_USER`, `IYOSI_APP_DB_PASSWORD` | Separate runtime login, granted data DML but no schema or role administration. |
| `IYOSI_SECRET` | Signed API token key, at least 32 characters. Rotating it invalidates existing tokens. |
| `IYOSI_EDGE_NETWORK`, `IYOSI_TRUSTED_PROXY_IPS` | Shared ingress network and exact trusted proxy peer address. |
| `IYOSI_API_IMAGE`, `IYOSI_DB_IMAGE` | Optional pinned image references; defaults are local build tags. |
| `GEOAPIFY_API_KEY` | Optional server-side address search key. `GEOCODER_URL` is only for a compatible local/test provider. |

The API image runs as **UID 10001 / GID 10001**. The PostGIS image's database account is **UID 999 / GID 999** in the validated image; its entrypoint starts as root to initialize the named volume, then drops to that account. A named volume needs no host bind-mount ownership preparation. If an operator substitutes a bind mount, they must confirm the pinned DB image's UID/GID and set mount ownership after a separate validation.

The migration job receives the migration DB URL and provisions the runtime role; the API receives only the runtime DB URL. The role has data access to the current application tables and read-only access to the NCR boundary. It cannot modify `schema_migrations`. A migration that adds a table must also update `scripts/provision_runtime_role.py` before rollout. The DB volume, not container lifespan, stores application data. The Docker host and its backup operator remain powerful trust boundaries.

## Prepare, update, and recover

For a fresh disposable rehearsal, create the shared edge network and set the environment file, then run `docker compose -f compose.shared.yaml --env-file .env.shared up -d --build --wait`. Compose waits for PostGIS, runs `migrate` once, then starts the API. Verify `docker compose ... ps`, call `/health` through ingress, and check `/admin` and a public viewport. Do not publish DNS before TLS and ingress checks pass.

For an update, stop iYosi API writes, back up and verify the current database, then run the migration job once before starting the new runtime image:

```sh
export COMPOSE_FILE=compose.shared.yaml IYOSI_ENV_FILE=.env.shared
docker compose --env-file "$IYOSI_ENV_FILE" stop api
sh scripts/backup_db.sh /secure/iyosi-backups/iyosi-predeploy.dump
sh scripts/verify_restore.sh /secure/iyosi-backups/iyosi-predeploy.dump
```

Copy the verified dump to encrypted off-host storage and confirm the copy before running the migration. Use a timestamped backup path instead of overwriting an earlier dump. Then roll out:

```sh
docker compose --env-file "$IYOSI_ENV_FILE" build api migrate
docker compose --env-file "$IYOSI_ENV_FILE" run --rm migrate
docker compose --env-file "$IYOSI_ENV_FILE" up -d --no-deps --force-recreate --wait api
```

Pin and record the previous image digest before deployment; changing `IYOSI_API_IMAGE` back and recreating `api` is a runtime rollback if the schema remains compatible. For a schema-incompatible change, restore the pre-upgrade dump to a **new** PostGIS database/volume, re-run `prepare_db.sh` there to provision the runtime role, validate health and public/admin reads, then cut over. Never restore into the live database in place. The [operations runbook](OPERATIONS.md) covers recovery ownership and retention.

The provided `scripts/backup_db.sh` uses a transactionally consistent `pg_dump` custom archive. `scripts/verify_restore.sh` restores it into a disposable database and checks migrations, NCR geometry, and core tables. They work with `COMPOSE_FILE=compose.shared.yaml` and `IYOSI_ENV_FILE=.env.shared`. For the proposed Oracle `backup-app.sh` interface, install reviewed root-owned copies of `scripts/host_backup_snapshot.sh` and `scripts/host_backup_verify.sh` as `/usr/local/lib/app-backup-hooks/iyosi-snapshot` and `iyosi-verify`, mode `0700`. Each accepts the orchestrator's mode-0700 staging directory; snapshot writes `iyosi-postgis.dump`, and verify restores that artifact to a temporary database. Their defaults expect the deployment at `/srv/apps/iyosi` and its mode-0600 environment at `/etc/apps/iyosi/iyosi.env`; override `IYOSI_DEPLOY_DIR` and `IYOSI_ENV_FILE` only in reviewed host configuration. Snapshot and verify have 15- and 20-minute timeouts and return nonzero on failure. Infrastructure owns `iyosi-export`: encrypt, copy off-host, verify the remote object, and apply approved retention. The orchestrator remains fail-closed until all three hooks exist. VM snapshots alone do not replace logical dumps.

## Host jobs and observations

Run `timeout 5m docker compose -f compose.shared.yaml --env-file /etc/apps/iyosi/iyosi.env exec -T api python scripts/cleanup.py` **daily** and `timeout 2m docker compose -f compose.shared.yaml --env-file /etc/apps/iyosi/iyosi.env exec -T api python scripts/ops_metrics.py` **hourly** from `/srv/apps/iyosi`. These commands exit nonzero on a container or script failure. Back up daily, verify each restore, and monitor successful off-host transfer. Poll `/health` through HTTPS every minute; alert after three failures. Alert on failed jobs, disk above 80%, abnormal 5xx and geocoder failure rates, and urgent/ordinary moderation case age targets in [performance baseline](PERFORMANCE.md). Logs expose route template, status, duration and request ID without query text, request bodies, or tokens. The host must configure a named alert recipient.

## Acceptance still needed

- ARM64 images built and the isolated Compose rehearsal passed locally; the **combined** Oracle host has not been provisioned or load-tested.
- Reserve Caddy's exact `edge-iyosi` address in the ingress Compose file, configure `IYOSI_TRUSTED_PROXY_IPS` to match it, and verify spoofed forwarding headers cannot change client-IP rate buckets; check HTTPS and iOS from a reachable device. The combined ingress remains untested.
- Supply a real Geoapify key, reviewed NCR records, moderator, privacy/retention decisions, off-host encrypted backup destination, and alert recipient before a private pilot. Public launch has additional age/recovery/legal gates.

The host choice and budget are coordinated in the infrastructure hosting assessment. This repository does not provision cloud resources, DNS or billing.

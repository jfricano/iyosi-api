# Private pilot operations

The [pilot Compose file](../compose.pilot.yaml) runs one immutable API container and a private PostGIS database. It binds the API to host loopback only. A host-managed HTTPS reverse proxy must forward to `127.0.0.1:8000`; expose only port 443 to clients. The database has no host port. This template is for a single trusted host, not a public launch.

## Initial setup and deployment

1. Copy `.env.example` to `.env.pilot` on the host. Generate separate `POSTGRES_PASSWORD` and `IYOSI_SECRET` values with `openssl rand -hex 32`. Keep this file mode `0600`, outside backups and Git. Set `GEOAPIFY_API_KEY` after creating a provider project; see [address search adapter](GEOCODER.md). Use hex credentials because Compose interpolates the password into a URL.
2. Run `docker compose -f compose.pilot.yaml --env-file .env.pilot up -d --build --wait`. Confirm `curl -fsS http://127.0.0.1:8000/health` returns `{"status":"ok"}`. The API entrypoint applies append-only migrations and loads the committed boundary before serving. Deploy only one API instance during migrations.
3. Configure a trusted TLS proxy with automatic certificate renewal and HTTPS-only routing. Point the iOS client at its HTTPS URL. Restrict host login and Docker access to the operator; Docker access implies access to the database and its secrets.
4. Before each update, take and verify a backup, run CI, review migrations, then rebuild. For a schema change, rehearse the upgrade against a restored copy first. If the API image must be rolled back after a migration, check compatibility; otherwise restore the pre-upgrade dump to a new database and cut over. Never edit an applied migration.

The health endpoint checks DB connectivity and the NCR boundary. Poll it from outside the host over HTTPS every minute and alert the named operator after three consecutive failures. Also alert on unavailable DB/container, disk utilization over 80%, failed backup or restore drill, and moderation queue age beyond the pilot response target. Correlate incident reports by the `X-Request-ID` response header; do not log tokens, passwords, private evidence, or full request bodies. Set a short, explicit log retention period with the host operator.

## Backup and tested restore

The dump contains account information and private moderation evidence. Store it encrypted off-host with access limited to the service owner. A local dump alone is not a backup. Schedule a daily dump, off-host transfer, and daily `verify_restore.sh` run; retain at least seven daily copies and one monthly copy until the pilot retention policy is approved. Check available disk before a restore drill.

```sh
export COMPOSE_FILE=compose.pilot.yaml IYOSI_ENV_FILE=.env.pilot
mkdir -m 700 -p "$HOME/iyosi-backups"
backup_path="$HOME/iyosi-backups/iyosi-$(date -u +%Y%m%dT%H%M%SZ).dump"
sh scripts/backup_db.sh "$backup_path"
sh scripts/verify_restore.sh "$backup_path"
```

`backup_db.sh` writes a custom-format `pg_dump` atomically and checks its archive catalog. `verify_restore.sh` creates a disposable database, restores the full archive with `--exit-on-error`, checks the base migration and valid NCR boundary plus core tables, and drops the disposable database. These scripts target the currently selected Compose database, including the development stack; use the correct `COMPOSE_FILE` and environment file. Do not put dumps under the repository in normal operation. Transfer dumps over an encrypted channel and record the off-host location, checksum, verification time, and operator.

To recover after data loss, stop the API and preserve the damaged database for investigation. Create a **new** PostGIS-enabled database on a replacement host, restore the selected verified dump with `pg_restore --exit-on-error --no-owner --no-acl`, and run the same schema/boundary checks as `verify_restore.sh`. Point `DATABASE_URL` at the restored database, start the API, then verify `/health`, place reads, and an audited admin queue read before re-enabling client traffic. Record the dump timestamp and expected data-loss window. Do not restore into the live database in place.

## Routine work

- Run `docker compose -f compose.pilot.yaml --env-file .env.pilot exec -T api python scripts/cleanup.py` daily to delete expired idempotency and rate-limit metadata. Check its exit code.
- Check `docker compose -f compose.pilot.yaml --env-file .env.pilot ps`, host disk, database size, and HTTPS certificate renewal daily. Review moderation queue age and provider errors with the response owner.
- Keep OS, Docker, Python image, and PostGIS image patches current through a tested rebuild. Pin image digests when choosing the actual host/release workflow.
- Grant admin only to a named trusted account through `scripts/grant_admin.py`; the command changes a powerful role and should be recorded. Rotate secrets after suspected exposure. Rotating `IYOSI_SECRET` invalidates existing tokens.

The final host, HTTPS proxy, off-host storage, alert destination, retention policy, named operator, and provider account are deployment decisions. A free host with sleeping services or expiring databases is suitable for disposable demos, not a reliable pilot containing user data.

## Disposable online demo recommendation

For a zero-cost **development demo**, use a Render Free web service built from `infra/api/Dockerfile` and a Neon Free PostGIS database. Configure Render's `DATABASE_URL` from a **direct** Neon PostgreSQL connection string with `sslmode=require`, plus `IYOSI_SECRET` and optional `GEOAPIFY_API_KEY` as host secrets; set health check path `/health`. Keep real accounts and unpublished evidence out of this disposable environment. A demo still needs an operator-run logical dump before changing its data.

This choice avoids [Render Free Postgres's 30-day expiry and lack of backups](https://render.com/docs/free). [Neon supports PostGIS](https://neon.com/blog/ten-most-popular-postgres-extensions), [scales idle compute to zero after five minutes](https://neon.com/blog/why-you-want-a-database-that-scales-to-zero), and currently lists [100 CU-hours and 0.5 GB per project](https://neon.com/blog/building-patterns-unlocked-by-scale-to-zero). Its [connection requires TLS](https://neon.com/blog/oops-proof-your-vibe-code-with-neon-because-mistakes-happen). Render provides [managed HTTPS](https://render.com/docs/web-services), but its Free service sleeps after 15 minutes idle, may take about a minute to wake, and can suspend unusually high external database traffic [under its free limits](https://render.com/docs/free). These limits make the combination a demo environment, not the private pilot release target.

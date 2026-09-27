# Pilot performance and observability baseline

**Measured 2026-09-26** on local Docker/PostGIS 17 and Python 3.12. This is a development baseline, not a hosted SLO measurement. The [benchmark script](../scripts/benchmark_viewports.py) inserts 5,000 deterministic synthetic points inside the committed NCR boundary into a **marked `_test` database**, with roughly one review per three places, one confirmation per two, and 990 open moderation cases. All benchmark inserts roll back. It runs the same SQL projection, visibility filters, cursor order, and `limit + 1` used by `/v1/places`, with ten warmups and 100 timed samples per viewport. Query times include local Python/Postgres transfer but not HTTP, TLS, network latency, or cold starts.

| Viewport | First-page DB query p50 | p95 | Plan |
| --- | ---: | ---: | --- |
| 0.05° × 0.05° | 0.85 ms | 1.34 ms | `places_location_idx` GiST bitmap scan, then sort and limit |
| 0.16° × 0.20° | 2.33 ms | 2.75 ms | `places_pkey` ordered scan stops after 51 matching rows |

`EXPLAIN (ANALYZE, BUFFERS)` also showed `confirmations_place_idx` and `reviews_place_idx` serving the per-place summary subqueries. The smaller viewport examined 257 spatial candidates; the broad viewport removed 54 rows while finding its first 51 matches. **No new index is justified at this volume.** Re-run after real pilot counts and distribution become known, especially for later cursor pages and high review density.

## Repeat the measurement

Create an empty database whose name ends in `_test`, add the same `iyosi_integration_test_guard` marker used by the integration suite, apply migrations, and load the committed NCR boundary. Then run:

```sh
docker compose run --rm -T \
  -e TEST_DATABASE_URL=postgresql://iyosi:PASSWORD@db:5432/iyosi_perf_test \
  workspace sh -ec 'PYTHONPATH=. python scripts/benchmark_viewports.py'
```

The script refuses any non-`_test` URL, missing marker, or missing boundary. Its JSON output includes sample latency, `EXPLAIN` index names, and queue gauges. Replace `PASSWORD` with the dedicated test DB password; use a local environment variable or secret rather than committing it.

## Provisional private-pilot targets

- `/v1/places` and detail **p95 under 500 ms** at the HTTPS edge under normal pilot load, excluding a documented free-tier cold start; database portion **p95 under 100 ms**. Measure over rolling 15-minute windows once a host and representative client traffic exist. Investigate sustained p95 above target, even when the service is still healthy.
- API 5xx rate **under 1%** of requests over 15 minutes; `/health` should be continuously successful from outside the host. Log route templates, status, elapsed milliseconds, and request ID, never full URL query strings, bodies, auth tokens, or location coordinates.
- Review urgent (`priority >= 2`) moderation cases within **4 hours** and other open cases within **24 hours** during the private pilot. `scripts/ops_metrics.py` prints open count, urgent count, oldest age in seconds, 24-hour resolutions, and DB size as JSON. Run it hourly and alert the named moderator when the age target is crossed. Adjust these targets with actual staffing and volume.
- Count `geocoder_failure` warning events by `reason` and provider HTTP status. Alert on three consecutive failures or more than 5% of address-search requests failing over 15 minutes. A missing provider is an explicit degraded state until configured. The logs omit search text and provider URL.
- Alert on DB disk utilization above 80% and failed daily backup/restore drill. Use request IDs to correlate reports with logs.

Run the queue gauge from the pilot image with `docker compose -f compose.pilot.yaml --env-file .env.pilot exec -T api sh -ec 'PYTHONPATH=. python scripts/ops_metrics.py'`. The structured `request_complete` and `geocoder_failure` JSON records are emitted through the Uvicorn error logger; the host log collector can aggregate them without adding another service to the pilot stack. There is no external alert route until a pilot host and operator are chosen.

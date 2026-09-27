# Backend v1 delivery record

**Status:** Implementation complete for local and deployment-ready private-pilot code, 2026-09-26. Jason Fricano is the sole credited author. The hosted pilot is not live.

## Delivered

- Versioned FastAPI `/v1` and checked-in OpenAPI for place browsing, bounded viewport and nearby queries, detail, suggestions, accounts, proposals, confirmations, reviews, reports, deletion requests, and moderation.
- PostGIS schema, append-only migrations 001 and 002, NCR boundary, spatial index, audited moderation decisions, optimistic place versions, idempotent contribution requests, rate limits, and role checks.
- Internal `/admin` console covering queue, private case context and evidence, manual cases, decision actions, history, and conflict reload.
- Isolated `iyosi_demo` database with four explicitly fictional markers and a local search fixture for iOS development. It never seeds the normal API.
- Geoapify autocomplete adapter selected for a pilot, with the key kept server-side, Philippines filter, NCR point validation, bounded response, safe failure, and required attribution links in iOS. A local GeoJSON adapter remains for the synthetic demo.
- Non-root read-only pilot API image, Compose deployment template, CI suite, health checks, privacy-safe request and provider-failure logs, queue/DB gauges, cleanup, backup and restore scripts, and operations runbook.

## Verification

| Check | Result |
| --- | --- |
| Full Python contract, integration, migration, admin, geocoder, and observability suite | **33 passed** against a marked dedicated PostGIS test database. |
| Admin JavaScript behavior and syntax | Passed, including a Pacific-time verification-date regression. |
| OpenAPI | Checked-in JSON matches runtime schema. |
| Live moderation demo | Admin account sign-in, manual case, queue/detail context, stale-version `409`, audited decision, and public read passed with fictional data. |
| iOS | Simulator build passed; installed app displayed all four fictional pins on an iPhone 18 Pro simulator. |
| Pilot image and recovery | Non-root image started; `/health` and `/admin` returned 200; queue gauge ran; a custom-format dump restored and passed checks in a disposable database. |
| Local query baseline | 5,000 synthetic NCR places: small and broad viewport DB query p95 of 1.34 ms and 2.75 ms respectively. Hosted HTTPS latency is unmeasured. |

The dedicated integration fixture refuses a database without a `_test` name and guard marker before destructive setup. The synthetic seeder requires both the `iyosi_demo` database and `IYOSI_DEMO_SEED=1`. See [test map](BACKEND_TEST_MAP.md), [performance record](PERFORMANCE.md), and [operations runbook](OPERATIONS.md) for repeatable commands and limits.

## Deployment recommendation

For a disposable, no-cost online development demo, **Render Free API + Neon Free PostGIS** is the simplest fit for this Docker image and PostgreSQL schema. Render supplies HTTPS but sleeps after idle time and may suspend high outbound DB traffic. Its own Free Postgres expires after 30 days, so use Neon for the database. Neon supports PostGIS and currently advertises 100 CU-hours and 0.5 GB per Free project. Keep synthetic data only and expect cold starts. See [Render Free limits](https://render.com/docs/free), [Neon Free terms](https://neon.com/blog/neon-backend-is-ga), and [Neon PostGIS](https://neon.com/docs/extensions/postgis).

For a **real private pilot with user accounts**, choose a host and backup destination that meet the [operations runbook](OPERATIONS.md). Do not treat a sleeping free service or a provider snapshot as a verified off-host backup. The local Compose pilot template is the deployable baseline; no host or paid service has been provisioned.

## Remaining release gates

1. Review actual NCR places and evidence, name a moderator, and publish real records through the audited workflow. The user explicitly chose fictional development data for this delivery.
2. Provision the host, HTTPS domain/proxy, Geoapify project key, secret storage, off-host encrypted backups, alert destination, and cleanup/restore schedule. Run an actual reachable-device HTTPS journey and measure edge latency there.
3. Approve a private-pilot response target, retention/deletion policy, privacy contact and notice, and operator access. Public launch separately needs age assurance, account recovery, provider/legal review, and independent security review.

These are environment, content, and policy gates. The backend implementation sprints are closed; no additional backend coding sprint is scheduled by this record. New defects discovered during hosted acceptance should become focused tickets with the same branch and test gates.

## Repository handoff

The API and iOS changes live in separate repositories. Use short-lived ticket branches, keep `main` stable, merge the API contract before the client change, and retain append-only migrations. Local integration occurred on `integrate/backend-v1`; the corresponding iOS attribution change is `feat/IOS-009-geocoder-attribution`. Each change was verified before integration, with Jason Fricano as commit author. Remote publication is separate from this local delivery.

# iYosi

**An informational map of designated and community-reported smoking areas in Metro Manila.** This repository contains the shared API for separate Android and iOS pilot clients.

iYosi helps adults find current information while respecting smoke-free rules and the people sharing public spaces. It makes designated areas, community reports, and corrections visible so people can make informed choices and help keep the metro clean and its air clear.

The map distinguishes **verified designated smoking areas**, **designated areas at establishments**, **community-reported outdoor spots**, and **establishment claims that have not been verified**. A report that people smoke somewhere is never displayed as permission to smoke there. Each place can have a precise public-access pin, access notes, recent confirmations, separate star ratings and written reviews, and a route to report bad information.

## Vision

Help adults find current, clearly labeled information about where smoking is permitted or reported in the metro, while giving businesses and communities a way to correct the record. Useful information should be easy to find, easy to question, and quick to update.

Read the [product brief](docs/PRODUCT_BRIEF.md) for the full story, experience, release scope, and naming ideas. The [Codex API handoff](docs/API_HANDOFF.md) links the conceptual architecture, v1 feature specification, and API resource model for the next development step. [Launch notes](docs/LAUNCH_NOTES.md) cover moderation, privacy, legal review, and future business options.

The [backend v1 delivery record](docs/BACKEND_V1_DELIVERY.md) summarizes what is implemented and verified, with remaining hosted-pilot gates. The [implementation plan](docs/BACKEND_EXECUTIVE_PLAN.md), [sprint backlog](docs/BACKEND_SPRINT_PLAN.md), and [test map](docs/BACKEND_TEST_MAP.md) retain the decision trail.

The [operations runbook](docs/OPERATIONS.md) covers the immutable pilot image, CI, daily cleanup, backup/restore drills, and hosting decisions.
The [shared-host contract](docs/SHARED_HOST_CONTRACT.md) describes the ARM64 one-shot migration and private PostGIS integration candidate for the coordinated Oracle/VM assessment.

## Current state

This repository contains the FastAPI v1 server, PostGIS migration, NCR boundary seed, generated [OpenAPI contract](docs/openapi.json), an internal [moderation console](docs/ADMIN_OPERATIONS.md), and contract/integration tests. The Android pilot client and SwiftUI iOS client live in separate repositories. The API is platform neutral.

## Local API

Copy `.env.example` to `.env`, replace `IYOSI_SECRET` with the output of `openssl rand -hex 32`, then start Compose:

```sh
cp .env.example .env
docker compose up -d --build
curl http://localhost:8000/health
```

Compose applies SQL migrations and seeds the committed NCR boundary on first start. The API documentation is at `http://localhost:8000/docs`; machine-readable OpenAPI is at `http://localhost:8000/openapi.json` or [docs/openapi.json](docs/openapi.json). The database remains private to Compose. Set a server-side `GEOAPIFY_API_KEY` for hosted address autocomplete, or `GEOCODER_URL` for a compatible GeoJSON test endpoint; see [address search adapter](docs/GEOCODER.md).

For iOS development with populated but fictional records and working local address suggestions, start the [isolated demo stack](docs/DEMO_DATA.md) on port 8001. It uses a separate database and never seeds the normal pilot API.

Create an adult account through `/v1/auth/register` and promote a trusted operator account with `docker compose exec workspace python scripts/grant_admin.py EMAIL`. Do this only in a private pilot environment. All moderation decisions then go through the API so they are audited.

The October 2026 API review, its decisions, open items and dev-mode test steps are in [docs/API_REVIEW_2026_10.md](docs/API_REVIEW_2026_10.md).

Operators can sign in to the [moderation console](docs/ADMIN_OPERATIONS.md) at `http://localhost:8000/admin` for local development. It supports the queue, private evidence review, all decision actions, and version-conflict recovery.

## Tests

The Python suite runs with Python 3.12 and dependencies in `requirements.txt`:

```sh
PYTHONPATH=. python -m pytest -q tests/test_contract.py tests/test_geocoder.py tests/test_admin_ui.py tests/test_observability.py
```

The PostGIS integration test needs a dedicated test database. With Compose running:

```sh
docker compose exec db psql -U iyosi -d postgres -c 'CREATE DATABASE iyosi_test;'
docker compose exec db psql -U iyosi -d iyosi_test -c "CREATE TABLE iyosi_integration_test_guard (purpose text PRIMARY KEY); INSERT INTO iyosi_integration_test_guard VALUES ('iyosi dedicated integration tests');"
docker compose exec -T -e TEST_DATABASE_URL=postgresql://iyosi:local-development-only@db:5432/iyosi_test workspace sh -c 'PYTHONPATH=. python -m pytest -q tests'
node --check admin/assets/admin.js
node tests/test_admin_ui.js
```

Set `TEST_DATABASE_URL` to an empty dedicated database whose name ends in `_test` and create its marker before running the suite. The fixture checks both before it truncates tables. Re-generate OpenAPI with `PYTHONPATH=. python scripts/export_openapi.py`. Schedule `docker compose exec workspace python scripts/cleanup.py` daily to remove expired idempotency and rate-limit metadata. The local Compose stack has been started and `/health` verified on the development Mac; the normal database contains no published places until an administrator publishes reviewed submissions.

## Repositories and ownership

The API, iOS app, and Android app are organized as three independent project roots intended for separate Git repositories. The API contract in [docs/openapi.json](docs/openapi.json) is shared by the clients; they do not share source code or a Git history. For local development, clone the repositories as sibling `api/`, `ios/`, and `android/` folders inside an `iYosi/` workspace folder.

The original project code and documentation are released under the [MIT License](LICENSE). Copyright © 2026 Jason Fricano. The committed boundary data has [separate attribution and license terms](THIRD_PARTY_NOTICES.md).

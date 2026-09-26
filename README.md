# iYosi

**An informational map of designated and community-reported smoking areas in Metro Manila.** This repository contains the shared API for separate Android and iOS pilot clients.

iYosi helps adults find current information while respecting smoke-free rules and the people sharing public spaces. It makes designated areas, community reports, and corrections visible so people can make informed choices and help keep the metro clean and its air clear.

The map distinguishes **verified designated smoking areas**, **designated areas at establishments**, **community-reported outdoor spots**, and **establishment claims that have not been verified**. A report that people smoke somewhere is never displayed as permission to smoke there. Each place can have a precise public-access pin, access notes, recent confirmations, separate star ratings and written reviews, and a route to report bad information.

## Vision

Help adults find current, clearly labeled information about where smoking is permitted or reported in the metro, while giving businesses and communities a way to correct the record. Useful information should be easy to find, easy to question, and quick to update.

Read the [product brief](docs/PRODUCT_BRIEF.md) for the full story, experience, release scope, and naming ideas. The [Codex API handoff](docs/API_HANDOFF.md) links the conceptual architecture, v1 feature specification, and API resource model for the next development step. [Launch notes](docs/LAUNCH_NOTES.md) cover moderation, privacy, legal review, and future business options.

## Current state

This repository contains the FastAPI v1 server, PostGIS migration, NCR boundary seed, generated [OpenAPI contract](docs/openapi.json), and contract/integration tests. The Android pilot client and SwiftUI iOS client live in separate repositories. The admin web UI is not yet implemented. The API is platform neutral.

## Local API

Copy `.env.example` to `.env`, replace `IYOSI_SECRET` with the output of `openssl rand -hex 32`, then start Compose:

```sh
cp .env.example .env
docker compose up -d --build
curl http://localhost:8000/health
```

Compose applies SQL migrations and seeds the committed NCR boundary on first start. The API documentation is at `http://localhost:8000/docs`; machine-readable OpenAPI is at `http://localhost:8000/openapi.json` or [docs/openapi.json](docs/openapi.json). The database remains private to Compose. `GEOCODER_URL` is optional and must point to a compatible GeoJSON feature-search endpoint before `/v1/address-suggestions` works; see [API resource model](docs/API_RESOURCE_MODEL.md).

Create an adult account through `/v1/auth/register` and promote a trusted operator account with `docker compose exec workspace python scripts/grant_admin.py EMAIL`. Do this only in a private pilot environment. All moderation decisions then go through the API so they are audited.

## Tests

The local contract suite runs with Python 3.12 and dependencies in `requirements.txt`:

```sh
PYTHONPATH=. python -m pytest -q tests/test_contract.py
```

The PostGIS integration test needs a dedicated test database. With Compose running:

```sh
docker compose exec db psql -U iyosi -d postgres -c 'CREATE DATABASE iyosi_test;'
docker compose exec db psql -U iyosi -d iyosi_test -c "CREATE TABLE iyosi_integration_test_guard (purpose text PRIMARY KEY); INSERT INTO iyosi_integration_test_guard VALUES ('iyosi dedicated integration tests');"
docker compose exec -e TEST_DATABASE_URL=postgresql://iyosi:local-development-only@db:5432/iyosi_test workspace sh -c 'PYTHONPATH=. python -m pytest -q tests/test_integration.py'
```

Set `TEST_DATABASE_URL` to an empty dedicated database whose name ends in `_test` and create its marker before running the suite. The fixture checks both before it truncates tables. Re-generate OpenAPI with `PYTHONPATH=. python scripts/export_openapi.py`. Schedule `docker compose exec workspace python scripts/cleanup.py` daily to remove expired idempotency and rate-limit metadata. The local Compose stack has been started and `/health` verified on the development Mac; the database contains no published places until an administrator publishes reviewed submissions.

## Repositories and ownership

The API, iOS app, and Android app are organized as three independent project roots intended for separate Git repositories. The API contract in [docs/openapi.json](docs/openapi.json) is shared by the clients; they do not share source code or a Git history. For local development, clone the repositories as sibling `api/`, `ios/`, and `android/` folders inside an `iYosi/` workspace folder.

Copyright © 2026 Orca Solutions. All rights reserved. The original project code and documentation are [proprietary](LICENSE.md), even when this repository is publicly visible. The committed boundary data has [separate attribution and license terms](THIRD_PARTY_NOTICES.md).

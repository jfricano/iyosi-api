# Backend test map

**Baseline:** 2026-09-26. This maps the [v1 feature spec](FEATURE_SPEC_V1.md) to evidence in the API repository. Client behavior needs a separate iOS walkthrough against populated data.

| Feature | Backend evidence today | Next verification |
| --- | --- | --- |
| F01 Map viewport | `test_viewport_and_cursor_bounds`; empty collection before publication in the PostGIS journey | Published pins, pagination, viewport edges, and spatial query plan with NCR-sized data |
| F02 Kind/status filters | `/v1/places` contract and response model | Filter combinations, prohibited opt-in, hidden/closed exclusion in PostGIS |
| F03 Address search | Endpoint and provider adapter exist | Configured provider, NCR filtering, timeout and malformed response behavior |
| F04 Near me | Nearby endpoint exists; foreground permission belongs to iOS | Nearby radius, bounds, and no server-side location history; iOS denial journey |
| F05 Place detail | `test_place_output_keeps_signals_separate`; published detail and verification in PostGIS journey | Closed/merged detail and populated iOS detail screen |
| F06 Place proposal | Strict schema test; create, publication, and merge PostGIS journeys | Correction, outside-NCR and duplicate rejection, access-point rules |
| F07 Confirmation | `still_there` and separate freshness in PostGIS journey | `changed`/`gone` cases, rate limit, hidden observation |
| F08 Review | One review and separate rating in PostGIS journey | Edit/delete, one-per-account, hidden aggregate and pagination |
| F09 Report | Endpoint exists | Place/review report cases, priority, privacy and admin resolution |
| F10 Admin moderation | Publish, verify evidence, non-admin rejection, and merge in PostGIS journeys | Full action/case matrix, version conflicts, audit and rollback checks |
| F11 Account/deletion | Registration in PostGIS journey; `/v1/me` and deletion route exist | Disabled account, deletion case and private/public data handling |
| F12 Adult access | `test_adult_gate_validation_and_error_shape` | iOS prompt; public-launch age method remains a decision |

## Sprint 0 evidence

- `PYTHONPATH=. python -m pytest -q tests/test_contract.py`: **9 passed**.
- Marked, dedicated PostGIS database upgraded from migration 001: `PYTHONPATH=. python -m pytest -q tests`: **11 passed** after migration 002. This includes publication and merge of create submissions.
- Fresh dedicated PostGIS database with migrations 001 and 002: both integration journeys passed. The fixture refused an unmarked database before touching its tables.
- Local Compose API `/health`: `{"status":"ok"}`. Pilot database currently has zero published places.
- `test_checked_in_openapi_matches_runtime` passes, so the committed OpenAPI matches the running FastAPI schema.

The highest-priority missing evidence is populated-map behavior, the remaining moderation actions, and an iOS walkthrough. The [sprint plan](BACKEND_SPRINT_PLAN.md) orders these alongside data sourcing and operator work.

## B-008 auth and abuse evidence

- A dedicated marked PostGIS database passed the full 26-test suite. Concurrent rate-limit requests admitted exactly the configured limit; simultaneous deletion requests returned one pending case; simultaneous idempotent submissions returned one result.
- Tests cover token expiry and tampering, disabled-account rejection, idempotency and rate-bucket expiry, duplicate-registration throttling, active-only operator promotion, cleanup retention, and generic request-ID-tagged server errors.
- Deletion approval pseudonymizes email and disables login while retaining contributions and audit links under the current private-pilot behavior. A final retention and erasure policy remains a release decision.

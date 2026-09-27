# Backend test map

**Final implementation snapshot:** 2026-09-26. The initial gap map and Sprint 0/B-008 evidence below are historical checkpoints. See the [v1 delivery record](BACKEND_V1_DELIVERY.md) for release gates.

## Final requirement evidence

| Feature | Verification |
| --- | --- |
| F01–F02 map, viewport, filters | Bounded cursor and viewport contract tests; PostGIS spatial/status/hidden/prohibited cases; 5,000-place benchmark; four synthetic pins visible in iOS simulator. |
| F03 address search | Geoapify request and normalization tests, local demo provider, malformed/outside-NCR/timeout tests; iOS builds with conditional provider attribution. Live hosted Geoapify key remains a deployment gate. |
| F04 near me | Bounded nearby endpoint and no server-side location history. iOS permission denial remains device acceptance work. |
| F05 detail | Published, closed, merged, verification, rating, access, and privacy behavior covered in contract/PostGIS tests; populated iOS map smoke passed. |
| F06 proposals | Strict input, pending publication, correction, duplicates, NCR boundary, merge, and idempotency/concurrency covered in PostGIS tests. |
| F07–F09 confirmations, reviews, reports | Still/changed/gone, review upsert and hidden aggregate, place/review reports, moderation queue and privacy covered in PostGIS tests. |
| F10 moderation | Admin role, full decision cases, version conflict, audit and immutable history in PostGIS tests; live admin queue/detail/decision journey and console JavaScript checks passed. |
| F11 accounts and deletion | Token expiry/tamper, disabled account, concurrent deletion, admin bootstrap, retention behavior and cleanup covered in tests. Final erasure policy is a release gate. |
| F12 adult access | Registration self-attestation validation tested; public-launch age assurance remains a policy gate. |

The merged suite passed **33 Python tests** against a marked dedicated PostGIS database. Admin JavaScript checks, runtime OpenAPI comparison, pilot-image health/admin checks, and a disposable backup/restore drill also passed. The iOS app built and displayed the four fictional map pins in the simulator. Hosted HTTPS, a real provider key, real reviewed places, and a complete physical-device client walkthrough remain release gates.

## Historical Sprint 0 gap map

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

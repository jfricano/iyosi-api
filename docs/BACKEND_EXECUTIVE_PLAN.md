# iYosi backend implementation plan

**Baseline:** 2026-09-26
**Credited author and decision owner:** Jason Fricano
**Delivery companion:** [Backend sprint plan](BACKEND_SPRINT_PLAN.md)

**Implementation outcome:** The backend v1 code, admin console, synthetic iOS development stack, provider adapter, CI, and pilot operations template are complete locally. See the [v1 delivery record](BACKEND_V1_DELIVERY.md) for evidence and remaining hosted/content/policy gates. The “starting point” and “immediate order” below are the original baseline retained for traceability.

## Direction

Continue the existing FastAPI/PostGIS modular monolith and `/v1` OpenAPI contract. The API owns all writes; an internal admin web client will use its moderation endpoints. Build a useful **private NCR pilot** first, then address the additional operating, privacy, legal, and age-access requirements for a public release. This is an execution plan for an existing backend, not a new design or a hiring plan.

“Executive,” “scrum master,” “backend,” “QA,” and “operations” describe **virtual team responsibilities** carried out by the author with agent assistance. They are not proposed employees or additional credited authors. Keep one integrated sprint goal; delegate bounded, independent tasks in parallel when that helps. The author reviews the result and owns product decisions. Consult outside specialists where independent legal, privacy, or security review is needed.

## Starting point

The repository has the [resource model](API_RESOURCE_MODEL.md), [feature spec](FEATURE_SPEC_V1.md), generated [OpenAPI](openapi.json), FastAPI routes, a PostGIS migration and NCR boundary, Compose, admin APIs, and iOS calls to `/v1`. Local Compose and `/health` work. A live PostGIS integration test initially exposed a create-submission constraint mismatch; a new migration fixes it and that integration journey now passes. Keep the test in the release gate so the defect cannot quietly return.

The pilot database still has **zero published places**. The admin web UI is absent, and address suggestions return `503` until a geocoder is configured. Automated database coverage is two integration tests for publication, merge, and basic signal separation; the wider moderation matrix remains untested. The repository has no CI, hosted environment, backup/restore procedure, or monitoring. Some older docs still describe iOS as future work even though the client now exists.

## Solo delivery model

| Responsibility | How it is covered |
| --- | --- |
| Product and moderation decisions | Author chooses initial place sources, evidence threshold, status policy, and acceptance criteria; records each decision. |
| Executive and scrum coordination | Agents maintain the goals, backlog, sprint review, dependencies, and scope; author accepts priorities. |
| API, database, and admin UI | Author and agents implement bounded vertical slices; parallel work uses separate files or clearly owned interfaces. |
| QA and release | Agents run contract, PostGIS, and client journeys and review each other's work; author accepts gate evidence. |
| Operations | Author decides hosting; agents prepare TLS, secrets, backup, alerts, and runbooks for review before a hosted pilot. |
| External review | Qualified legal/privacy and security consultation at public-release gates; advice is a dependency, not assumed standing staff. |

Plan one primary sprint goal with at most one small secondary task. Agent work can run in parallel where tasks are independent, but integration and gate acceptance stay with the author. If a dependency such as provider selection or place evidence blocks a slice, switch to the next ready item and record the block. No calendar date is promised for public launch.

## Goal sequence and gates

| Gate | Deliverable and exit evidence |
| --- | --- |
| **G0 — Reproducible baseline** | Compose startup and `/health`; checked-in migration applies to a clean database; contract and live PostGIS integration tests pass; OpenAPI matches runtime; highest-priority backlog and decisions are recorded. The corrected publication journey must remain covered. |
| **G1 — Useful place data** | A small, sourced and reviewed NCR dataset is loaded through the moderated workflow or a controlled audited import. Viewport and detail responses show it correctly; duplicate handling and hidden/closed/prohibited behavior are checked. A repeatable update and correction path exists. |
| **G2 — Moderation operation** | Internal admin UI can review each case source and execute the supported decisions, including merge, status correction, verification evidence, review handling, and deletion request. Authorization, version conflict, audit record, and private-evidence behavior are tested. |
| **G3 — Client-ready pilot** | Geocoder choice is documented and configured, or a deliberately reduced search scope is accepted for a private test. iOS flows in the feature spec work against populated data; Android contract compatibility is checked. Representative NCR fixture data meets a stated viewport response target. |
| **G4 — Hosted private pilot** | HTTPS, secrets, migrations, health/alerts, scheduled cleanup, backup and successful restore, incident/rollback steps, and moderator access are demonstrated in the chosen private environment. |
| **G5 — Public-release approval** | Published privacy notice/contact, retention and deletion procedure, account recovery and adult-access decisions, staffed moderation process, legal review of status language, independent security review, and release/rollback rehearsal are complete. |

Use a **one-week Sprint 0** to close G0, then **two-week goal-based sprints** as the default review rhythm. Adjust the length if the solo capacity or external dependencies make a shorter or longer interval more useful. The [sprint plan](BACKEND_SPRINT_PLAN.md) holds the ordered stories and sprint demonstrations; gates above are outcomes, not promises that each fits one sprint.

## Immediate order of work

1. Preserve the now-passing publication integration test, add it to a repeatable check, and document the migration path for existing databases.
2. Source and review a small real NCR place set; publish it and prove the iOS map/detail flow against those records.
3. Build the smallest usable admin queue and decision screen, expanding action coverage through actual moderation cases.
4. Select/configure the geocoder and test search, errors, and limits with the iOS client.
5. Add broader authorization, state-transition, concurrency, migration, and performance tests where each closes a concrete release risk.
6. Deploy the private pilot only after backup/restore and operations checks; pursue G5 separately.

## Decisions to record before they harden in code

- Which sources and evidence qualify a place for publication or `verified_designated`, and who reviews them?
- Which geocoder meets NCR coverage, terms, latency, and cost needs?
- Where will the private pilot run, where will backups live, and who receives alerts?
- What realistic map density and response target define acceptable pilot performance?
- What retention, deletion, account recovery, and adult-access mechanisms are required for public use? Obtain specialist input for the legal/privacy parts.

## Definition of done

A backend slice is done when the API and database behavior work together, any migration works on a clean and existing database, authorization and important failure paths are verified, OpenAPI and human docs agree, and the affected iOS or admin journey is demonstrated with realistic data. An operations slice also needs a runbook and a recovery check. A place-data slice needs a recorded source and moderation decision. Close a gate only after its evidence is recorded in the sprint review.

Ads, payments, live enforcement tracking, and automated legal-status decisions remain outside this backend plan.

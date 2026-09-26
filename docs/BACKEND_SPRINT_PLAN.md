# Backend delivery sprint plan

**Planning baseline:** 2026-09-26. **Scope:** shared iYosi API, PostGIS data, moderation operations, address search, iOS integration, and private-pilot service operations. **Status:** working delivery plan; estimates are forecasts, not commitments. The user is the sole credited author; executive, scrum, engineering, and QA roles here organize agent work and do not imply hired staff or additional authors.

## Starting point and target

The v1 contract is already described in [API resource model](API_RESOURCE_MODEL.md) and exported as [OpenAPI](openapi.json). FastAPI routes, migrations `001_initial.sql` and `002_resolved_create_submission_place.sql`, the NCR boundary seed, Compose, and a Swift API client exist. Compose and `/health` have been verified live, but the pilot database has zero published places. Contract tests cover schema and a few invariants. The first live PostGIS integration run exposed a create-submission publication constraint mismatch; migration 002 fixed it, and the integration journey now passes. The iOS app builds. Address suggestions return `503` until `GEOCODER_URL` is configured. Admin decisions have API endpoints but no operator interface. The current tests do not establish that the full moderation matrix, migration upgrades, geocoder behavior, privacy boundaries, or restore procedure work end to end.

The delivery target is a **private NCR pilot with a named moderation and service response owner** in which a visitor can browse useful reviewed places, a contributor can submit and correct information, a moderator can handle every case type with an audit trail, and the service can be restored and monitored. Public launch is a separate release gate because age assurance, account recovery, privacy retention, provider terms, and local legal review still need decisions.

## Working roles and capacity

| Virtual role | Responsibility |
| --- | --- |
| Executive lead | Keep scope, dependencies, and release gates clear; bring decisions to the user. |
| Scrum master | Maintain the ordered backlog, one active implementation ticket, and concise progress notes. |
| Backend/API and data engineering | Implement API, PostGIS, migrations, moderation rules, geocoder, and operations. Use parallel agents only for independent bounded work. |
| Admin UI and iOS integration | Build the operator surface and check the real client journeys when their backend dependencies are ready. |
| QA/security review | Run meaningful integration checks and review risky auth, privacy, migration, and deployment changes. |
| Product/moderation decisions | The user or a delegated human operator approves real place evidence, provider choices, and pilot policy. |

These roles organize work by one credited author with agent assistance; they are not a four-person staffing requirement. A private pilot still needs a real person accountable for reports and service incidents. Keep estimates within the available agent and user-review capacity.

## Cadence and working rules

- **Sprint 0:** one week to establish an executable baseline and a ready backlog. Later sprints use two-week review windows, with the number of sprints adjusted to actual progress. This is a sequence, not a release-date promise.
- Keep **one implementation ticket in progress**. A separate read-only review or planning task may run alongside it. Pull the next ticket after the active one meets its acceptance check. Interrupt for blocking data, privacy, or security defects.
- At the start of each sprint, choose one main outcome and a small optional follow-up. At the end, demonstrate the working behavior and record completed, blocked, and next. No daily meeting, formal ceremony, or velocity accounting is required.
- Track each ticket as **ready → in progress → verified → done**. A story is done only when code/docs, a relevant automated test or repeatable verification, OpenAPI/client impact review, and an affected client journey check are complete. Keep brief evidence (test output, fixture provenance, screenshot, restore result) with the ticket.
- Re-estimate from completed work. If work spills over, preserve the acceptance check and move the ticket forward; do not mark an incomplete journey done. Request review when it adds material value for a risky migration, authentication/privacy change, real-place evidence, or deployment decision.
- **Testing is a hard gate every sprint.** Run focused contract tests for changed API behavior and the dedicated PostGIS integration journey for backend/DB changes. When a sprint affects the client or public data, run the applicable iOS journey against a populated API. Attach the command/result or device evidence to the ticket. A backend story cannot be marked done from a document or code diff alone; a failed applicable test keeps it open.

### Branch and merge policy

- Keep `main` stable. Start one short-lived branch per ticket from current `main`, named `fix/B-001-create-publication`, `feat/B-006-admin-queue`, or `docs/B-002-traceability`. Avoid a long-running sprint branch.
- Make focused commits that explain the change and ticket. Merge after relevant tests pass. Use a pull request when the diff, risk, or review benefits from one; a second reviewer is optional for routine solo work and valuable for auth, privacy, migration, and deployment changes. Avoid direct development commits on `main`.
- Treat applied database migrations as append-only. Add a new numbered migration for later schema changes; test both a fresh database and upgrade from the previous schema before merging. Document data backfills and rollback/restore steps for any risky migration.
- Keep API, iOS, and any admin or Android repository changes in separate coordinated branches. Link related changes, merge the API contract first when compatible, and run client acceptance against the merged contract. The sibling checkouts do not share Git history.

## Prioritized backlog and sprint forecast

Sizing: **S** ≈ up to 2 focused workdays, **M** ≈ 3–5, **L** ≈ more than a week and should be split into smaller verified slices. These are planning bands, not elapsed-time promises. Dependencies are explicit so independent agent reviews can proceed while one implementation ticket stays active.

| Ticket | Priority / size | Forecast | Work lane | Acceptance evidence |
| --- | --- | --- | --- | --- |
| B-001 Local stack and dedicated test DB | P0 / S, partly done | 0 | API/data + QA | Compose and `/health` work; migration 002 fixes create publication and the PostGIS journey passes. Confirm fresh and upgraded DB paths, ensure the destructive test fixture cannot target pilot data, and record commands/results. |
| B-002 Baseline and traceability | P0 / S | 0 | Scrum + QA | Contract suite and checked-in OpenAPI generation pass; F01–F12 mapped to backend tests, client tests, or an explicit release gate; observed gaps become tickets. |
| B-003 Reviewed seed-data workflow | P0 / M | 1 | Product decision + data | A small, provenance-recorded NCR fixture set is proposed and approved through audited admin actions; iOS map and detail return nonempty published data; no invented verification or private evidence is exposed. Pilot seed data needs human evidence review. |
| B-004 Migration and spatial regression | P0 / M | 1–2 | Data + QA | Fresh install and upgrade from migration 001 both pass; boundary edge, outside-NCR, bbox limits, nearby radius, hidden/closed/prohibited, pagination, duplicate 50 m, and index-backed query behavior are tested. |
| B-005 Moderation decision matrix | P0 / L, split | 2–3 | API + QA | Integration tests exercise every supported case source and action, authorization, evidence requirements, version conflicts, transaction rollback, and audit old/new state; public reads reflect decisions without private fields. Split by submission/place, content report, and deletion cases. |
| B-006 Admin workflow | P0 / L, split | 3–4 | Admin UI + API | Operator can sign in, triage by priority, inspect private evidence, publish/reject/merge submissions, handle place/review/confirmation/report/deletion cases, and see decision history; the UI shows errors and version conflicts. Start with queue/publication, then add other actions. |
| B-007 Geocoder provider and adapter | P0 / M | 5 | Product decision + API | Provider selection and terms/cost are recorded; configured search returns normalized NCR suggestions; malformed, outside-NCR, timeout, and provider-down results are handled; no key leaks to clients or logs. |
| B-008 Auth, abuse, and deletion hardening | P0 / L, split | 5–6 | API + security review | Rate/idempotency concurrency and expiry behavior, disabled accounts, admin bootstrap/recovery, deletion request handling, retention and error logging are tested against an agreed private-pilot policy. Public-launch recovery/age checks remain gated. |
| B-009 iOS contract acceptance | P0 / M | 6 | iOS + QA | On simulator and at least one reachable HTTPS device environment, browse without GPS; search; open detail; register/sign in; submit/track/correct; confirm, review, report; admin resolution changes public state. Capture request IDs for failures. |
| B-010 Performance and observability | P0 / M | 7 | Data + operations | Realistic NCR fixture volume and target device viewport patterns are agreed; p95 latency, DB query plans, error rates, queue age, and provider failures are measured against documented pilot SLOs; indexes or queries are changed where needed. |
| B-011 Private-pilot hosting and recovery | P0 / L, split | 7–8 | Operations + data | TLS endpoint, secrets, least-privilege access, migration rollout, scheduled cleanup, off-host backups, tested restore, health/alerts, and rollback runbook work in the chosen pilot environment. No public traffic before release review. |
| B-012 Pilot release evidence and handoff | P0 / M | 8 | QA + executive | End-to-end regression and moderation rehearsal pass; a response owner is named; provider settings, seed provenance, test results, restore drill, security/privacy review, and known limitations are in one release checklist. |
| B-013 Public-launch readiness | P1 / L+, conditional | Later | Executive + external specialist review as needed | Age assurance, account recovery/email, retention/deletion policy, Philippine legal/privacy review, provider/license terms, capacity, incident response, and production hosting are decided, implemented, and independently reviewed before public availability. |

### Sprint outcomes and dependencies

| Sprint | Goal and demonstration | Exit gate |
| --- | --- | --- |
| **0 — executable baseline** (1 week) | Confirm the fixed PostGIS journey on a dedicated database, check migration 002 upgrade/fresh paths and test isolation, then map test gaps. | B-001 and B-002 complete. The publication journey already passes; preserve that gate. |
| **1 — useful data** (2 weeks) | B-003; take a small B-004 spatial slice if ready. | Reviewed places appear in iOS viewport/detail and pending records do not. If evidence is unavailable, use synthetic development fixtures only and keep the pilot data gate open. |
| **2 — spatial and submission rules** (2 weeks) | Finish B-004; begin B-005 submission/place cases. | Migration/spatial regression passes; core admin decisions have audited DB tests. |
| **3 — moderation matrix** (2 weeks) | Finish B-005 in small case-type slices; start B-006 queue/publication view if capacity remains. | Every case source has a tested decision path, permission check, and public privacy check. |
| **4 — operator workflow** (2 weeks) | Finish B-006 in UI slices. | A moderator can handle the queue without manual SQL and see conflicts/history. |
| **5 — search and account hardening** (2 weeks) | B-007, then the highest-risk B-008 slice. | NCR search works through the selected provider; auth/abuse work is measured and prioritized. |
| **6 — client acceptance** (2 weeks) | Finish B-008 and B-009. | Full iOS/API contributor and moderation journey passes with populated data. |
| **7 — service operations** (2 weeks) | B-010 and initial B-011 slices. | Pilot query target and service signals are measured; hosting/recovery work is underway. |
| **8 — private-pilot decision** (2 weeks, extend if needed) | Finish B-011 and B-012. | Private-pilot gate passes with backup/restore, TLS, alerts, response ownership, and no high-severity defect. |
| **Later — public readiness** (conditional) | Implement decisions from legal, privacy, age, recovery, and operating review. | Public-launch gate B-013 passes separately. |

## Sprint 0 ready tickets

1. **B-001a — Verify the current integration baseline (partly complete).** Compose and `/health` work; migration 002 has repaired publication and the PostGIS journey passes. Confirm the result on both a fresh dedicated test DB and a DB upgraded from migration 001. Record the exact command and result.
2. **B-001b — Protect test isolation.** Ensure the integration fixture cannot truncate development or pilot data if pointed at the wrong URL. Run the dedicated integration test again. **Done:** the guard rejects a non-test target and the test database journey passes.
3. **B-002a — Contract/OpenAPI baseline.** Run `tests/test_contract.py` and compare generated OpenAPI with the checked-in copy. **Done:** drift is zero or is captured as a ticket.
4. **B-002b — Requirement-to-test map.** List each backend part of F01–F12 and its current test or missing evidence; mark client-only and release-decision items. **Done:** gaps are sorted into B-004–B-013 or new tickets.

After Sprint 0, B-003 is the next implementation ticket. Real pilot seed publication requires reviewed evidence; synthetic data can support development immediately.

## Definition of release gates

**Backend gate:** all P0 API/DB/admin stories have passing focused contract and dedicated PostGIS evidence; OpenAPI matches runtime; migrations are repeatable; integration tests cover decisions and privacy boundaries; approved sample data is visible to iOS and applicable iOS journeys pass; no unresolved P0/P1 defects.

**Private-pilot gate:** backend gate plus real-device HTTPS journey, provider agreement/configuration, a named moderation response owner and queue target, documented data provenance, measured pilot SLOs, alert route, backup and successful restore, rollback rehearsal, privacy notice/contact, and the user's release decision. Where a policy or legal review is pending, the pilot audience and controls are explicitly restricted.

**Public-launch gate:** separate executive approval after B-013 and formal legal/privacy/security review. Do not infer public readiness from passing private-pilot tests.

## Risks and decisions to manage each sprint

| Risk or dependency | Decision owner | Decision point / response |
| --- | --- | --- |
| No reviewed real places to show | User/product decision | Supply evidence and approve seed records for Sprint 1; use synthetic fixtures only in development. |
| Geocoder unavailable, unsuitable terms, or cost | User/provider decision | Select a provider before B-007; preserve `503` degraded state until configuration works. |
| Admin queue grows faster than response capacity | User/operations decision | Name a response owner and queue-age target before pilot; instrument age during B-010. |
| Boundary-edge and legal-status disputes | User with local legal review if needed | Keep ambiguous pins unverified; resolve geometry/policy before affected records are published. |
| Auth, retention, age assurance, and recovery are pilot defaults | User with specialist review as needed | Set pilot limits before hosting; make public-launch decisions in B-013. |
| API and iOS change at different speeds | API/iOS work lanes | Review OpenAPI diffs on each change; run populated-data client journeys during B-009 and before release. |

The scrum role updates this plan after each sprint review with completed ticket IDs, test evidence, remaining blockers, and the next forecast. The user remains the sole credited author and makes release-scope decisions.

## Sprint 0 progress (2026-09-26)

- B-001 publication and test-isolation changes are committed on `fix/B-001-create-publication` (`553b28b`). The local pilot database has migration 002 applied. The fixture rejects an unmarked database before truncation. The marked upgraded database runs the full suite with **11 passing tests**, and a fresh database passed both integration journeys.
- B-002 evidence is recorded in [Backend test map](BACKEND_TEST_MAP.md). The checked-in OpenAPI comparison passes.
- Both branches remain separate from `main` pending review/merge. B-003 is next: prepare development data, then source and review real pilot places before publishing them.

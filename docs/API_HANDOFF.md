# iYosi → Codex API handoff

This handoff originally defined the v1 API for an Android-first NCR pilot, with the same contract usable by an iOS client. The API is implemented in this repository's `api/` Python package, with migrations and generated OpenAPI. The Android and iOS pilot clients are maintained in separate Git repositories. This handoff remains the design reading order and invariant checklist.

## Read in this order

1. [Product brief](PRODUCT_BRIEF.md): origin story, audience, four place types, and product promise.
2. [Conceptual architecture](CONCEPTUAL_ARCHITECTURE.md) — **Work → Codex review**: system boundaries, data flows, deployment path, and architecture decisions.
3. [V1 requirements and feature specification](FEATURE_SPEC_V1.md) — **Work → Codex review**: actors, functional requirements, acceptance journeys, and release scope.
4. [API philosophy and resource model](API_RESOURCE_MODEL.md) — **Work + Codex**: resources, endpoint proposal, invariants, and open contract decisions.
5. [Launch notes](LAUNCH_NOTES.md): moderation, privacy, legal sources, and later business considerations.

## Non-negotiable product invariants

- Place kind, advisory status, confirmation, and rating are distinct concepts.
- User contributions cannot set or imply `verified_designated`; an admin records evidence before verification.
- Browsing works without GPS permission. The service does not store a user's location trail.
- New place proposals enter moderation before public publication in v1.
- Reports and admin actions are auditable; reporter and contributor identities are not public.
- The API remains independent of Android/iOS UI choices and of the map/geocoder vendor.

## Proposed first coding slice

1. Add a FastAPI application, health endpoint, configuration, migrations, and an automated schema check to the existing Compose environment.
2. Model NCR boundary, published places, pending submissions, accounts, moderation cases, and decisions in PostgreSQL/PostGIS.
3. Implement bounded public place reads with fixture data and generated OpenAPI, then verify spatial filtering and status visibility.
4. Add authentication/adult-access decision, contributions, moderation, confirmations, reviews, and reports in that order.

Codex review outcomes and chosen defaults are recorded in the linked documents. The generated contract is [OpenAPI](openapi.json).

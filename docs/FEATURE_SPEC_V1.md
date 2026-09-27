# V1 requirements and feature specification

**Handoff lane:** Work → Codex review  
**Release:** Android pilot in the National Capital Region, backed by an API reusable by iOS.

**2026-09-26 implementation update:** A SwiftUI iOS client and the shared backend v1 now exist. The original Android-first release wording and deferred-iOS line below are historical scope notes. Current backend evidence and remaining hosted-pilot gates are in the [backend v1 delivery record](BACKEND_V1_DELIVERY.md).

## Product rule

The app maps **reported places**, with clear status and freshness. It never promises that a user will be allowed to smoke at a pin. A community observation, star rating, or venue claim does not establish legal approval. The four place kinds and independent statuses are defined in [Conceptual architecture](CONCEPTUAL_ARCHITECTURE.md).

## Actors

| Actor | Abilities |
| --- | --- |
| Adult visitor | Browse, search, filter, view place detail, use optional “near me” |
| Signed-in adult contributor | Visitor actions plus propose places, confirm, review, and report |
| Admin | Review proposals and reports, verify evidence, correct/merge/hide places, moderate reviews, inspect audit history |

## Functional requirements

| ID | Requirement | Acceptance condition |
| --- | --- | --- |
| F01 | Map starts in NCR and loads published pins for the visible area. | Pan/zoom replaces the result set; zoomed-out pins cluster; pins use distinct shapes and colors for the four kinds. |
| F02 | Kind and advisory-status filters are independent and togglable. | Turning a kind off removes only that kind; “verified designated” cannot be confused with “community reported.” |
| F03 | Search accepts an address or landmark. | Selecting a result moves the map there; browsing remains usable if location permission is denied. |
| F04 | “Near me” uses foreground location only after an explicit tap. | The app asks once when needed, handles denial, and sends no background location updates. |
| F05 | Place detail presents identity, pin/entrance, access notes, kind, status, evidence-review date where applicable, last confirmation, stars, review count, and warnings. | A user can distinguish evidence review from community freshness before opening directions. |
| F06 | A contributor can propose a place with type, name/landmark, precise area pin, optional public-entrance pin, access notes, and basis for the claim. | Outside-NCR and invalid coordinates fail; nearby possible duplicates are shown; submission remains pending until admin decision. |
| F07 | A contributor can confirm `still_there`, `changed`, or `gone`, with observation time and optional access-note correction. | Confirmation appears separately from ratings; `changed`/`gone` creates review work; no confirmation automatically verifies legality. |
| F08 | A contributor can give 1–5 stars and optional written comments. | One active review per account per place; editing updates that review; hidden reviews are excluded from displayed aggregates. |
| F09 | A contributor can report a place or review for wrong status, closure, privacy, harassment, spam, or other policy reason. | A report receives an acknowledgement and enters an admin queue without revealing the reporter publicly. |
| F10 | Admin can publish, reject, merge, dispute, mark prohibited/closed, verify, hide, or correct a place; hide or restore reviews; resolve reports. | Every action records actor, time, target, reason, old state, and new state. Verification requires evidence and review date. |
| F11 | Contributor has an account summary and deletion request path. | Public content never exposes auth identity; deletion request is acknowledged and queued for policy-compliant handling. |
| F12 | App presents an adult-access prompt and privacy notice before normal use. | Underage selection stops entry; age assurance for public launch remains a review item. |

## Business rules

- All v1 place proposals require admin review before publication. This is the initial moderation policy, even for informal spots.
- `verified_designated` requires an admin decision with recorded evidence and timestamp. A vote count or rating cannot set it.
- `prohibited` is a warning status; do not present it as a recommended destination. `closed` and `hidden` do not appear in normal map results.
- A confirmation answers whether the place and access route still exist. A review rates the experience. They are stored and shown separately.
- Access notes may describe public entry, floor, gate, and hours. They may not contain private-person details, trespass directions, or instructions to avoid enforcement.
- New place proposals warn about likely duplicates before final submission; admins can merge duplicates and preserve useful contribution history.

## Key acceptance journeys

1. **Find a verified area:** Search an NCR landmark, filter to verified designated areas, open a pin, see evidence-review and recent-confirmation dates, then open directions to the public access point.
2. **No GPS permission:** Deny location permission, type an address, pan the map, and inspect place details without loss of core functionality.
3. **Contribute an informal spot:** Select the outdoor category, move the pin, see duplicate candidates, submit access notes, and receive a pending-submission acknowledgement. The pin is not public until reviewed.
4. **Separate signals:** Confirm a place is still there without leaving stars; later rate it without creating a new confirmation. Neither action changes the advisory status.
5. **Correct a bad pin:** Report a closed or inaccurately labeled place; admin sees the report, records a decision, and the public map reflects the new status without exposing the reporter.
6. **Moderation boundary:** Attempt to submit `verified_designated` through a client request; the server ignores/rejects that field and leaves verification to admins.

## Nonfunctional requirements

- The API is versioned at `/v1`, uses HTTPS in deployed environments, validates all input server-side, and produces an OpenAPI contract for both mobile platforms.
- Bound viewport queries and pagination so a single client cannot download the full place database in one call. Use a spatial index and test map response time with realistic NCR fixture data before pilot.
- Rate-limit anonymous search and contribution endpoints; audit admin changes; keep user and admin authorization separate.
- Show loading, empty, offline/error, stale, disputed, and removed states in the Android client.
- Support screen readers; do not rely on color alone for type/status; keep controls usable at common text sizes.
- Collect only needed account and deliberately submitted place coordinates. Do not store a per-user location trail or address-search history.
- Store times in UTC and show locally appropriate time in the client. Present last confirmation and evidence-review dates independently.

## Explicitly deferred

iOS app UI, enforcement/security-presence markers, live location tracking, ads, payments, photo uploads, social feed, automated legal-status decisions, and production self-hosting. The API must remain platform neutral for iOS.

## Codex review checklist

- Are the actor permissions and approval boundary implementable without an accidental public write path?
- Are F01–F12 testable from API and Android behavior?
- Does the moderation queue cover changed/gone confirmations and duplicate merges, not only reports?
- Which requirements depend on provider, age-assurance, or legal decisions still open in [Launch notes](LAUNCH_NOTES.md)?

## API review outcome (2026-09-25)

F01–F02 are supported by bounded viewport reads and independent kind/status filters; pin shapes, colors, clustering, and the starting camera belong to Android. F03 is supported by a configurable geocoder adapter and needs a provider setting to work. F04 is a client permission flow; the API stores no device-location history. F05–F11 have API resources and a generated OpenAPI contract. F12 is enforced for contributors by adult self-attestation at registration; the visitor prompt and privacy notice are Android work. The API returns explicit `503` if the NCR boundary or geocoder is unavailable, and distinct `closed`, `prohibited`, `disputed`, and merged-place states.

Changed/gone confirmations, access-note suggestions, submissions, reports, and deletion requests all create moderation cases. Place corrections can change kind, pin, entrance, and access notes; publication resets the advisory assessment to `community_reported` unless an admin supplies fresh verification evidence. Public confirmations are short anonymous observations; reviews and ratings remain separate. Admin actions require reasons and write an audit decision in the same transaction. The test suite covers contract invariants locally and a full PostGIS moderation journey when `TEST_DATABASE_URL` is provided.

Before an Android pilot, select a tile and geocoder provider, seed real reviewed places, build the Android and admin clients, and run the integration suite against Compose. Before public launch, decide age assurance and account recovery, staff moderation, review local law and privacy documents, test realistic NCR response times, and complete TLS, backups, and monitoring.

## Android implementation update (2026-09-25)

The separate Android pilot client implements visitor and contributor journeys F01–F09 and F11–F12 against this contract. F10 is assigned to the separate admin interface. The map defaults to OpenStreetMap raster tiles with configurable build properties; address search still needs `GEOCODER_URL`. Android build and device testing remain pending on a host with JDK 17, Android SDK 35, and Gradle network access. The provider, age assurance, privacy, moderation, and deployment decisions above remain pilot or launch gates as applicable.

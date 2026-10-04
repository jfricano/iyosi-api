# API philosophy and resource model

**Handoff lane:** Work + Codex  
**Status:** Implemented v1 contract in `api/`; generated schema in `docs/openapi.json`.

## Philosophy

1. **One shared contract.** Android ships first; iOS should use the same `/v1` resources and OpenAPI schema without platform-specific fields.
2. **Evidence and experience are different signals.** Place kind, advisory status, confirmation history, and review score are separate fields with separate write permissions.
3. **Public records are curated.** Users create submissions, not public places directly. An admin decision publishes, verifies, merges, or rejects.
4. **Reads are map-efficient.** A viewport request returns compact pins; detail and reviews load separately. Address search is not a place search.
5. **Writes are accountable.** Server-derived account IDs, validation, rate limits, idempotency for retryable POSTs, and append-only admin audit events are part of v1.
6. **Privacy is structural.** Public responses omit account identifiers, reporter information, private evidence, and moderation notes. The API does not retain a user's device-location trail.

## Resource boundaries

| Resource | Public meaning | Owner of changes |
| --- | --- | --- |
| `place` | Published location and current assessment | Admin or approved moderation action |
| `place_submission` | Proposed new pin or correction awaiting review | Contributor creates; admin resolves |
| `confirmation` | Time-stamped observation of existence/access | Contributor creates; admin may hide abusive content |
| `review` | One account's stars and optional comment | Contributor creates/edits own; admin moderates |
| `report` | Complaint about a place or review | Contributor creates; admin resolves |
| `moderation_case` | Work item raised by submission, report, or changed/gone confirmation | Server creates; admin handles |
| `moderation_decision` | Append-only record of an admin action | Admin creates through authorized API |
| `account` | Minimal identity and contribution ownership | Authentication system and account owner |

`access_notes` belong to a place, not a separate public resource. A report about them targets the place with reason `access_notes`. The address-search adapter returns provider results; it does not create iYosi places.

## Place representation

Use opaque string IDs and ISO 8601 UTC timestamps. Store spatial data as WGS84 points. A public detail response should include:

```json
{
  "id": "plc_example",
  "name": "Example area",
  "kind": "venue_designated",
  "advisory_status": "verified_designated",
  "location": { "lat": 14.5547, "lon": 121.0244 },
  "access_point": { "lat": 14.5548, "lon": 121.0245 },
  "address_label": "Example address",
  "access_notes": "Use the public entrance and follow the posted signs.",
  "verification": { "reviewed_at": "2026-09-20T10:00:00Z", "public_source": "Posted venue designation" },
  "last_confirmed_at": "2026-09-22T08:00:00Z",
  "rating": { "average": 3.8, "count": 24 },
  "updated_at": "2026-09-22T08:00:00Z"
}
```

This is synthetic sample data. `verification` is null unless an admin recorded supporting evidence. `last_confirmed_at` says when someone saw the place, not when its legal status was reviewed. The public response does not include `created_by`, reporter IDs, or internal evidence URLs.

## Implemented endpoints

| Method and path | Purpose | Access |
| --- | --- | --- |
| `GET /v1/places?bbox=w,s,e,n&kind=...&advisory_status=...&cursor=...` | Published map summaries in a bounded viewport | Visitor |
| `GET /v1/places/{place_id}` | Published place detail, including warning or closure state | Visitor |
| `GET /v1/places/{place_id}/reviews?cursor=...` | Visible review list, newest first | Visitor |
| `GET /v1/places/{place_id}/confirmations?cursor=...` | Recent non-identifying observations, newest `observed_at` first | Visitor |
| `GET /v1/address-suggestions?q=...` | NCR address/landmark suggestions | Visitor, throttled |
| `GET /v1/places/nearby?lat=...&lon=...&radius_m=...` | Nearby published places and duplicate candidates | Visitor, throttled |
| `POST /v1/place-submissions` | Propose a new place or correction | Contributor |
| `GET /v1/me/place-submissions` | Track own proposals and decisions | Contributor |
| `POST /v1/places/{place_id}/confirmations` | Append an observation | Contributor |
| `GET /v1/places/{place_id}/reviews/me` | Own review, including one a moderator hid; `404` when none | Contributor |
| `PUT /v1/places/{place_id}/reviews/me` | Create or replace own review | Contributor |
| `DELETE /v1/places/{place_id}/reviews/me` | Remove own review from public display | Contributor |
| `POST /v1/reports` | Report a place or review | Contributor |
| `GET /v1/me` | Minimal account summary | Contributor |
| `POST /v1/me/deletion-requests` | Request account/data deletion | Contributor |
| `GET /v1/admin/moderation-cases?state=...` | Review queue | Admin |
| `GET /v1/admin/moderation-cases/{case_id}` | Case detail and private evidence | Admin |
| `POST /v1/admin/moderation-cases/{case_id}/decisions` | Apply a decision and append audit event | Admin |

Authentication uses `POST /v1/auth/register` and `POST /v1/auth/token`. Admins can open a manual place case with `POST /v1/admin/moderation-cases?place_id=...`; `/health` checks the database and NCR seed. Public reads are anonymous while Android presents the adult-access prompt. Public-launch age assurance remains a separate decision.

The admin case detail includes a `context` object with the current place and, for review reports, the reported review. The place includes its current `version` so the operator can send `expected_version` for changes. This object and the case's private source and decision snapshots are available only to admin accounts. The internal operator UI is documented in [Admin operations](ADMIN_OPERATIONS.md).

## Request rules

- `place_submission` has an `intent` of `create` or `correct`. A correction includes `place_id`; a new place does not. Requests carry a proposed kind, name, point, optional access point, access notes, and basis/evidence text or public URL. The server sets pending state and rejects any client attempt to set advisory status or verification.
- New place coordinates must be inside the selected NCR boundary. A duplicate search returns nearby candidates before submission; the server may also return a `409` likely-duplicate response with candidate IDs.
- `confirmation` accepts `still_there`, `changed`, or `gone`, an observed time, and optional proposed access-note change. It is append-only. A changed/gone observation opens a moderation case.
- `review` uses integer stars from 1 to 5 and bounded plain-text body. `PUT .../reviews/me` is idempotent for the same payload. One active review per account and place is enforced in storage.
- `report` targets a place or review, with reason and optional detail. The server creates a moderation case and returns a generic acknowledgement. Reporter identity is admin-only.
- Admin decisions require a reason. A `verify_designated` action additionally requires evidence type, public source summary, and reviewed-at time. The decision and resulting state change occur in one database transaction.

## Collection and error conventions

- `/v1` is the version boundary. JSON uses `snake_case`; timestamps are UTC; IDs are opaque and stable.
- Map endpoints require a bounded `bbox` in `west,south,east,north` order; the server caps viewport span, radius, result count, and page size. Use opaque cursors and a stable sort. Never expose raw SQL or provider keys.
- `GET /places` defaults to published, non-closed places. `prohibited` warning pins are opt-in through an explicit filter or `include_prohibited=true`. Hidden/rejected submissions are never in public collections.
- A closed place may return a minimal detail with `closed` status and no directions; a hidden or rejected record returns `404`. A merged place may return its canonical replacement ID.
- Use consistent errors with `code`, user-safe `message`, optional field errors, and `request_id`. Suggested statuses: `400` malformed query, `401` unauthenticated, `403` forbidden, `404` unavailable, `409` duplicate/conflict, `422` valid JSON with invalid field values, `429` rate limit.
- Retryable POSTs accept an `Idempotency-Key`, especially submissions, confirmations, and reports, so a poor mobile connection does not create duplicates.
- Admin place updates and corrections use an `expected_version` precondition to avoid overwriting another decision.

## Questions resolved in the settled contract below

1. Exact authentication and adult-access flow, including anonymous reads and account recovery.
2. Whether `place_submission` corrections can cover changes to type and access point, and how conflicting proposals are merged.
3. Whether public confirmations should show only aggregate counts or a short anonymized list.
4. Default treatment of `prohibited` warning pins and closed direct links.
5. Limits for viewport size, page size, note/review length, confirmation frequency, and idempotency-key lifetime.
6. Concrete error schema, OpenAPI names, and migration plan for the proposed resource model.


## Settled v1 contract (2026-09-25)

- **Authentication:** `POST /v1/auth/register` takes email, password (12–128 characters), and `adult_attested: true`; `POST /v1/auth/token` returns a 24-hour bearer token. The server derives account IDs from that token. Reads are anonymous. Disabled accounts lose access immediately. Public-launch age assurance, password recovery, and email delivery remain operational decisions.
- **Submissions:** Both create and correct requests can propose kind, area pin, entrance pin, name, address label, access notes, and venue inside/outside. All proposals remain pending. The server rejects client status or verification fields. Admin publication of a correction re-assesses status; verification needs fresh evidence. Nearby published places within 50 m produce a `409` with candidate IDs. A merged submission records its canonical place. A merged published place retains its history internally and exposes `merged_into` on a direct link.
- **Confirmations and ratings:** The public confirmation page lists recent observations without account IDs or access-note suggestions. A confirmation uses `still_there`, `changed`, or `gone`, and one account can confirm a place once per 24 hours. Only `still_there` observations update `last_confirmed_at`; changed/gone suggestions create cases. One review per account/place is stored; hidden and deleted reviews do not affect the aggregate. Neither resource writes advisory status.
- **Collection defaults:** Viewports are at most 0.5° per side; 50 items default and 100 maximum. Nearby radius is 50–1000 m, at most 50 items. The default map omits `closed` and `prohibited`; callers may explicitly request prohibited warning pins. Closed direct links return detail without an entrance or access note. `directions_allowed` is false for closed, prohibited, or merged places. `freshness` is `fresh` only when a non-hidden `still_there` confirmation is at most 90 days old; it never implies verification. Hidden places are `404`. Cursors are opaque. Map lists use stable ID ordering; reviews and confirmations page newest first by timestamp, then ID.
- **Write bounds:** Names 2–120 characters; address labels 240; access notes 500; basis/evidence 1000; review body 1000. Observations may be at most five minutes in the future or 30 days old. Submissions are capped at 10/day, reports at 10/day, reviews at 20/day, anonymous search at 30/hour, nearby queries at 60/hour, registration at 5/hour, and login attempts at 10/15 minutes. Idempotency keys of 8–128 characters are required for submission, confirmation, and report POSTs; stored results replay for 24 hours.
- **Errors and concurrency:** Error bodies use `code`, `message`, `request_id`, and optional `field_errors`. Input validation is `422`; malformed bbox/cursor is `400`. Admin place mutations require `expected_version`; a mismatch returns `409`. Case resolution, state mutation, and append-only audit decision commit together. `GET /health` checks both database migration and boundary presence.
- **Schema and migrations:** `migrations/001_initial.sql` creates PostGIS-backed resources and spatial indexes. `scripts/migrate.py` records applied versions. `scripts/load_boundary.py` loads a reviewed GeoJSON NCR geometry; Compose seeds the committed geoBoundaries polygon only if none is present. `docs/openapi.json` is generated by FastAPI from route schemas and can be regenerated with `PYTHONPATH=. python scripts/export_openapi.py`.

### Admin case actions

`publish`, `reject`, and `merge` apply to submissions. A manual case can be opened for a place. Place cases support `verify_designated`, `set_status`, `correct_place`, `hide_place`, `restore_place`, and `merge_place`. Review reports support `hide_review` and `restore_review`. Confirmation cases support `hide_confirmation`. `resolve` closes a case without altering content. An approved deletion request disables the account and pseudonymizes its email while retaining an internal audit ID. Every decision records reason, actor, target, time, and old/new state.

For the private pilot, concurrent deletion requests for one account return the same pending case. Approval immediately invalidates existing tokens and blocks password sign-in. The current approval retains contributions and the internal audit link; erasure or retention of those records requires the operator's documented policy before wider availability. Duplicate registration attempts count toward the per-IP registration limit. Rate counters are atomic under concurrent requests; idempotency records expire after 24 hours, and `scripts/cleanup.py` removes expired idempotency and rate metadata. Authentication and `/health` return `503` when the signing secret is missing or shorter than 32 characters. Unexpected server failures return a generic response with a request ID; logs contain the ID, path, and error class without request bodies or exception text.

### Response details

The detail and list OpenAPI models are `Place`, `PlaceSummary`, `PlacePage`, `ReviewPage`, and `ConfirmationPage`. `verification` is null unless the current status is `verified_designated`. No public response includes contributor/reporter identity or private evidence. The address adapter accepts a configured GeoJSON feature-search endpoint and returns normalized NCR suggestions; its `503` response is deliberate when no provider is configured.

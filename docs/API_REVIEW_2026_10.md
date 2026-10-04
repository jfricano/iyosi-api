# API review, October 2026

This review covered `api/`, the migrations, runtime scripts and compose files at `71d7af6`. It was coordinated with the Android review (iyosi-android PR #1) and the iOS review (iyosi-ios PR #2). Both apps already matched the API contract. No critical security issue was found: SQL is parameterized, tokens are HMAC-signed and compared in constant time, passwords use scrypt, proxy trust is pinned to one ingress address, and moderation decisions are append-only.

## What changed

| Area | Change | Client impact |
|---|---|---|
| Own review | New `GET /v1/places/{place_id}/reviews/me` returns the caller's review, or `404 not_found` when there is none. It still returns a review that a moderator hid, so the author can edit or delete it. | Both apps now use it to prefill the review form and to show "Delete my review". |
| List order | Reviews list newest first by `created_at`. Confirmations list newest first by `observed_at`. Before this change both were sorted by random ID. The cursor is still opaque but has a new format. | None. A cursor issued before deploy returns `400 invalid_cursor` once. |
| Observation time | `observed_at` gets 10 minutes of slack at the 30-day lower bound. A timestamp without a time zone gets its own message. | None. |
| Token | Responses include `expires_at` (UTC). | None. Both apps ignore unknown fields. |
| Login | Email and password have the same maximum lengths as registration (254 and 128). | None. |
| Connections | `core.db()` borrows from a `psycopg_pool` pool instead of opening a new connection each time. The pool holds up to 10 connections (`IYOSI_DB_POOL_MAX`). If none frees up within 10 seconds the request gets `503 database_busy`. | None. The apps show server messages as they are. |
| Corrections | Publishing a correction applies the proposed name, kind and pin. Optional fields the contributor left blank keep their current value. The place keeps its status and verification evidence unless the moderator picks a status, the kind stops being designated, or the pin moves more than 50 m. Corrections onto merged or hidden places are refused. The admin console defaults correction publishes to "Keep current status". | None. |
| Account deletion | Approving a deletion also removes the person's reviews, which drops their ratings, and blanks the free text in their submissions, confirmation suggestions and report details. Published places stay. The decision records how many items were removed. | Both apps' privacy and deletion text should say what is removed. |

## Decisions (jason, 4 October 2026)

- **Rate limits stay per IP** for now. Few users are expected at first. Mobile carriers in the Philippines share one IP across many people, so revisit this before a wider launch: key signed-in calls on the account and keep a higher per-IP backstop.
- **Corrections keep untouched fields and verification**, as described above.
- **Account deletion removes the person's own words** but keeps published places.
- **Database connections are pooled.**
- **Earlier moderation decision records stay append-only.** They can still contain text written before an account was deleted. Removing that text would mean removing the append-only protection.

## Open items

| Item | Notes |
|---|---|
| Production API host | Both apps need the real HTTPS address before release. This is a project decision. |
| Privacy text | Both apps should describe what account deletion removes. |
| Duplicate override | A new place within 50 m of a published one is always `409 likely_duplicate`. An override would need a new request field and a "submit anyway" option in both apps. Not planned. |
| Pin pydantic | It arrives through FastAPI unpinned, so validation message wording can change on rebuild. Clients show `field_errors` messages as they are and never parse them. |
| Token revocation, password reset | Not available. Tokens last 24 hours. Password reset would need new account screens in both apps. |
| Account enumeration | Login is faster for an unknown email, and registration returns `409 email_exists`. Acceptable for a private pilot. |
| Confirmation race | Two simultaneous confirmations from one person with different idempotency keys can both pass the once-a-day check. Low impact. |
| Cleanup schedule | `scripts/cleanup.py` must run daily from the host's scheduler. |

## Testing in dev mode

The automated suite (`PYTHONPATH=. python -m pytest -q tests`, see the README) covers every change above against PostGIS. These steps check the same behaviour on a running local stack.

`requirements.txt` gained `psycopg-pool`, so rebuild the images first.

```sh
docker compose up -d --build
curl -s http://localhost:8000/health        # {"status":"ok"}
```

Create two accounts. The second becomes an admin.

```sh
API=http://localhost:8000
reg() { curl -s -X POST $API/v1/auth/register -H 'Content-Type: application/json' \
  -d "{\"email\":\"$1\",\"password\":\"long dev password\",\"adult_attested\":true}"; }
reg person@example.com     # response includes access_token and expires_at
reg admin@example.com
docker compose exec workspace python scripts/grant_admin.py admin@example.com
login() { curl -s -X POST $API/v1/auth/token -H 'Content-Type: application/json' \
  -d "{\"email\":\"$1\",\"password\":\"long dev password\"}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])'; }
P=$(login person@example.com); A=$(login admin@example.com)
```

Propose a place and publish it from the admin console at `http://localhost:8000/admin` (sign in as admin@example.com, choose the case, Publish). Or use curl:

```sh
curl -s -X POST $API/v1/place-submissions -H "Authorization: Bearer $P" -H 'Idempotency-Key: dev-create-1' \
  -H 'Content-Type: application/json' -d '{"intent":"create","name":"Dev test area","kind":"public_designated",
  "location":{"lat":14.6,"lon":121.0},"access_notes":"Side entrance","basis":"Dev mode test record"}'
CASE=$(curl -s "$API/v1/admin/moderation-cases" -H "Authorization: Bearer $A" | python3 -c 'import json,sys;print(json.load(sys.stdin)["items"][0]["id"])')
curl -s -X POST $API/v1/admin/moderation-cases/$CASE/decisions -H "Authorization: Bearer $A" \
  -H 'Content-Type: application/json' -d '{"action":"publish","reason":"Dev mode check"}'
PLACE=$(curl -s "$API/v1/me/place-submissions" -H "Authorization: Bearer $P" | python3 -c 'import json,sys;print(json.load(sys.stdin)["items"][0]["place_id"])')
```

Own review:

```sh
curl -s -o /dev/null -w '%{http_code}\n' $API/v1/places/$PLACE/reviews/me -H "Authorization: Bearer $P"   # 404
curl -s -X PUT $API/v1/places/$PLACE/reviews/me -H "Authorization: Bearer $P" -H 'Content-Type: application/json' -d '{"stars":4,"body":"Clear sign"}'
curl -s $API/v1/places/$PLACE/reviews/me -H "Authorization: Bearer $P"                                     # the review
```

Observation slack and newest-first order:

```sh
OLD=$(python3 -c 'from datetime import datetime,timedelta,timezone;print((datetime.now(timezone.utc)-timedelta(days=30,minutes=2)).isoformat())')
curl -s -X POST $API/v1/places/$PLACE/confirmations -H "Authorization: Bearer $A" -H 'Idempotency-Key: dev-conf-1' \
  -H 'Content-Type: application/json' -d "{\"observation\":\"still_there\",\"observed_at\":\"$OLD\"}"           # 201, not 422
curl -s "$API/v1/places/$PLACE/confirmations"                                                               # newest observed_at first
```

Correction keeps untouched fields: propose a correction with only a new name, publish it in the console with "Keep current status" selected, then confirm that `access_notes` is still "Side entrance".

```sh
curl -s -X POST $API/v1/place-submissions -H "Authorization: Bearer $P" -H 'Idempotency-Key: dev-fix-1' \
  -H 'Content-Type: application/json' -d "{\"intent\":\"correct\",\"place_id\":\"$PLACE\",\"name\":\"Dev test area renamed\",
  \"kind\":\"public_designated\",\"location\":{\"lat\":14.6,\"lon\":121.0},\"basis\":\"Sign shows a new name\"}"
# Publish the new case in /admin, then:
curl -s $API/v1/places/$PLACE      # new name, access_notes unchanged
```

Account deletion: the person requests deletion, an admin approves it in the console, and then the review is gone and the rating count is 0.

```sh
curl -s -X POST $API/v1/me/deletion-requests -H "Authorization: Bearer $P"
# Approve the deletion case in /admin, then:
curl -s $API/v1/places/$PLACE      # rating.count is 0
curl -s -o /dev/null -w '%{http_code}\n' $API/v1/me -H "Authorization: Bearer $P"   # 401
```

Finally, point the iOS Simulator or Android emulator at `http://localhost:8000` (`http://10.0.2.2:8000` from the Android emulator). Check that the review form prefills, that "Delete my review" appears only when you have a review, and that confirmations list newest first.

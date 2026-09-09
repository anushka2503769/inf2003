# API contract v1 — onboarding, profile and skills

Status: implementation target for the first milestone. Only `GET /api/health` exists
today. The routes below are agreed working conventions for frontend mocks and backend
implementation, not a claim that the endpoints are already available.

Scope: Google sign-in → create/read profile → edit name → select/remove confirmed skills.
Resume upload remains in the product MVP but is a later integration. This milestone
requires only SQL; it does not require MongoDB or an LLM call.

## Shared conventions

- Paths start with `/api`; frontend uses relative URLs through the development proxy.
- JSON field names are `snake_case` in both requests and responses. Internal Python and
  TypeScript variable names may differ.
- JSON bodies use `Content-Type: application/json`. UUIDs are strings, skill IDs are
  positive integers within PostgreSQL's integer range, timestamps are UTC RFC 3339
  strings ending in `Z`. `null`, an absent field and an empty array are different.
- Every route below requires `Authorization: Bearer <Supabase access token>`.
  The existing health route is public and keeps its existing response.
- Python verifies the token against the configured Supabase project, including expiry
  and issuer/audience. Merely decoding a JWT is not verification. Derive `user_id` from
  the verified subject. Never accept a client-selected user ID for these operations.
- The server-only database credential can bypass RLS. Each query involving personal
  data must use the verified user ID. Never send database secrets to the frontend.
- Reject unexpected JSON body fields, including `user_id`, with 422. Reject wrong
  types instead of silently coercing them. GET/PUT/DELETE routes below accept no body.
- Successful personal responses should use `Cache-Control: no-store`.

## Routes at a glance

| Method and path | Purpose | Success |
|---|---|---|
| POST /api/me | Create profile if absent; otherwise return the existing profile | 201 new / 200 existing |
| GET /api/me | Read the signed-in student's profile and confirmed skills | 200 |
| PATCH /api/me | Change the student's display name | 200 |
| GET /api/skills?q=py&limit=20 | Search the shared skill dictionary | 200 |
| PUT /api/me/skills/{skill_id} | Ensure the student has this confirmed skill | 204 |
| DELETE /api/me/skills/{skill_id} | Ensure this skill link is removed | 204 |

## Profile response

POST, GET and PATCH `/api/me` return the same shape with no extra `data` wrapper:

```json
{
  "user_id": "11111111-1111-4111-8111-111111111111",
  "full_name": "Zhihao",
  "created_at": "2026-09-09T08:00:00Z",
  "updated_at": "2026-09-09T08:00:00Z",
  "skills": [
    { "skill_id": 1, "name": "Python" },
    { "skill_id": 2, "name": "SQL" }
  ]
}
```

`skills` is always an array, including `[]` for a new student. Each skill has exactly
`skill_id` (integer) and `name` (string). Return skills ordered by lowercase name, then
skill ID as a tie-breaker. Names come from SQL's canonical skill dictionary.

Example IDs, timestamps and names are synthetic; real IDs are assigned by the databases.

## POST /api/me — first-login onboarding

Request:

```json
{ "full_name": "Zhihao" }
```

`full_name` is required, must be a string and is trimmed before validation/storage.
After trimming it must contain 1–100 characters. The frontend can prefill Google's
display name, but the student can edit it. If Google provides no name, ask for one;
do not store an empty name or infer one from an email address.

Python inserts `public.users` using the verified token subject, not a new random UUID.
The existing Supabase Auth account must satisfy the `auth.users` foreign key. SQL creates
the timestamps. The endpoint does not create an Auth account or perform Google OAuth.

- New profile: return 201 and the profile with `skills: []`.
- Existing profile: return 200 and its stored values. Do not overwrite the name, skills
  or timestamps with the onboarding request. Use PATCH for an intentional name change.
- Handle simultaneous calls atomically using the primary-key conflict, then read the
  existing row. Do not implement a race-prone check-then-insert without conflict handling.
- Retrying a valid request after a lost response must not create duplicate profiles.

## GET /api/me — read profile

No body. Return 200 with the profile response. Return 404 `PROFILE_NOT_FOUND` if the
authenticated account has not completed profile creation. GET must not create records.

## PATCH /api/me — edit display name

Request:

```json
{ "full_name": "Zhi Hao" }
```

The only editable field is `full_name`, with the same validation as POST. An empty
object is invalid. Return 200 with the updated profile. Update `updated_at` only if the
stored name changes; preserve `created_at`. Return 404 `PROFILE_NOT_FOUND` if absent.
This changes our application display name, not the student's Google account name.

## GET /api/skills — choose from the shared dictionary

Query parameters:

| Parameter | Type | Default | Rules |
|---|---|---|---|
| q | String | Empty string | Trim; maximum 100 characters; case-insensitive literal substring match |
| limit | Integer | 20 | 1–100 |

Empty `q` lists the first skills alphabetically. `%` and `_` in input are literal
characters, not SQL wildcard operators. Use bound parameters and escape LIKE wildcards
if implementing this with ILIKE. Reject unknown query parameters with 422 to catch typos.

Response (200):

```json
{
  "items": [{ "skill_id": 1, "name": "Python" }],
  "has_more": false
}
```

No matches returns `{"items":[],"has_more":false}`. Sort by lowercase name then skill ID.
`has_more` is true if more than `limit` matches exist; fetch one extra result to determine
it. The initial UI asks the student to narrow the search rather than offering pagination.
This authenticated shared lookup works even before a profile exists.

For this milestone, manual skill addition means selecting an existing dictionary entry.
There is no public endpoint for creating or renaming canonical skills. The backend pair
must seed a small agreed dictionary first. Free-text suggestions and extraction-driven
dictionary expansion are later work; an unknown skill must not be silently created.

## PUT /api/me/skills/{skill_id} — add a confirmed skill

Example: `PUT /api/me/skills/1`, no JSON body.

- Require an existing profile; otherwise 404 `PROFILE_NOT_FOUND`.
- Require the skill to exist in `skills`; otherwise 404 `SKILL_NOT_FOUND`.
- Insert the `(user_id, skill_id)` link. A link that already exists is a successful no-op.
- Return 204 with no response body for both cases. Do not return or parse JSON on 204.

## DELETE /api/me/skills/{skill_id} — remove a confirmed skill

Example: `DELETE /api/me/skills/1`, no JSON body.

- Require an existing profile; otherwise 404 `PROFILE_NOT_FOUND`.
- Delete only this student's link. Never delete the dictionary entry in `skills`.
- An absent link (including an unknown positive skill ID) is already the desired state:
  return 204 with no response body. Repeated removal is safe.

For PUT and DELETE, a non-integer/nonpositive/out-of-range path ID returns 422. When a
link actually changes, update `users.updated_at` in the same SQL transaction. Repeated
no-ops preserve it. Never replace the whole skill set from a stale browser snapshot.
The frontend should serialize changes to the same skill and re-read GET /api/me after
a successful operation. Multiple devices have no conflict-detection guarantee in v1;
the last operation applied by the server determines membership. Do not replay old
profile-skill requests offline. Swipe batching is a separate future contract.

## Error contract

All application-generated errors for these planned routes use this shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Check the submitted fields.",
    "fields": [
      { "field": "full_name", "message": "Enter a name between 1 and 100 characters." }
    ]
  }
}
```

`error.code` and `message` are strings; `fields` is always an array (empty for non-field
errors). Each field entry contains string `field` and `message`. Use `body` for a
malformed JSON body, otherwise the exact body/query/path field name. Frontend logic
branches on `code`, not the human-readable message. Never echo tokens, SQL, credentials
or raw exception text. Network/proxy failures may have no JSON response; show a generic
connection error in that case.

| HTTP status | code | Frontend behaviour |
|---|---|---|
| 401 | UNAUTHORIZED | Refresh the session once via Supabase Auth and retry once; if still unauthorized, request sign-in |
| 404 | PROFILE_NOT_FOUND | Start onboarding rather than showing an empty existing profile |
| 404 | SKILL_NOT_FOUND | Refresh the skill search; explain the selection is no longer available |
| 422 | VALIDATION_ERROR | Show field feedback; preserve unsaved input |
| 503 | SERVICE_UNAVAILABLE | Preserve input and offer retry; never treat the write as confirmed |
| 500 | INTERNAL_ERROR | Show a generic failure; record details only in protected backend logs |

Authenticate before returning personal-resource existence errors. Token expiry/invalidity
is 401; a verification service outage is 503, not evidence that the student is signed out.
401 responses include `WWW-Authenticate: Bearer`. The backend must translate FastAPI's
default validation/HTTP exceptions into this contract for these routes. The existing
health endpoint and unrelated routes are outside this new error-contract scope.

## Frontend sequence and parallel work

1. Use Supabase Auth for Google sign-in and session management. There is no custom
   `/api/login` or `/api/google/callback` endpoint in this milestone.
2. With the access token, call GET /api/me. On 404 PROFILE_NOT_FOUND, show a name field
   and submit POST /api/me. On 200, show the existing profile without recreating it.
3. Search the skill dictionary, select/remove skills, and show confirmed membership.
4. On logout/account change, clear the previous user's profile and pending UI operations;
   never reuse their data for another session.

Frontend mocks must return these exact shapes and simulate 401, missing profile,
validation errors, empty results and service failures, not only the happy path.
Backend implementation must publish these same paths/shapes in FastAPI's OpenAPI docs.
Do not create placeholder routes returning fake success in the actual API.

The frontend and backend pairs can work in parallel from this file. Coordinate changes
to paths, fields or behaviour through Zhihao's review and update this document in the
same PR. This file defines the target until the implemented OpenAPI contract is verified.

## Acceptance checks for the first integrated milestone

- A new Google user creates one profile; a returning user sees existing edits and skills.
- Concurrent/retried onboarding does not duplicate or reset a profile.
- Invalid tokens fail, and forged user_id fields are rejected. Account A never accesses B's data.
- Blank/oversized names, unknown body fields and invalid query/path values return the error shape.
- Skill search is case-insensitive, bounded and literal; empty results render correctly.
- Repeated additions/removals are safe, confirmed skills survive reload and canonical
  skill entries remain intact after removal.
- Failure states keep unsaved input and do not display a failed change as persisted.
- Both pairs run the real flow against the Python API before calling the milestone complete.

# API contract v2

Status: **25 October 2026.** §1–§5 and §9 describe routes that are **implemented** on `dev`
(5dedfcb); §5 additions, §6, §7 and §8 are **to build** (marked *new*) under the work
packages in [PRD.md](PRD.md). FastAPI's OpenAPI output (`/docs`) is the final word for
implemented routes; when a PR changes a shape it updates this file in the same PR.

## 1. Conventions

- Paths start with `/api`. The frontend uses relative URLs through the Vite dev proxy
  (`/api` → `http://127.0.0.1:8000`).
- JSON fields are `snake_case`. UUIDs are lowercase strings, skill IDs positive 32-bit
  integers, timestamps ISO 8601 UTC.
- Every route except `GET /api/health` requires `Authorization: Bearer <Supabase access token>`.
  The backend verifies it (`backend/app/auth.py`) and derives `user_id` from the verified
  subject. No request may name the acting user; any `user_id` in a body is ignored.
- **Admin** routes additionally require the caller's id to be in `BACKEND_ADMIN_USER_IDS`.
- Unknown JSON body fields are ignored (pydantic default). Unknown **query** parameters on
  `GET /api/skills` are rejected with 422; new routes do the same.
- Pagination on new list routes: `limit` (default 20, max 50) and `offset` (default 0, max 10,000).

## 2. Errors

Every application error uses one envelope (`backend/app/errors.py`):

```json
{ "error": { "code": "not_found", "message": "Profile not found.", "details": { "resource": "profile" } } }
```

`details` is optional. The frontend branches on `code` (and `details.resource` for 404s),
never on `message`.

| HTTP | code | Meaning / frontend behaviour |
|---|---|---|
| 401 | `unauthenticated` | Refresh the Supabase session once and retry once; then send to sign-in |
| 403 | `forbidden` | Not an admin |
| 404 | `not_found` | `details.resource` ∈ `profile`, `skill`, `job`, `resume`. `profile` → start onboarding |
| 409 | `conflict` | Operation disabled (e.g. job/duplicate deletion) |
| 422 | `validation_failed` | `details.field` names the first bad field; keep the user's input |
| 503 | `service_unavailable` | Database unavailable or busy; keep input, offer retry, never show as saved |
| 500 | `internal_error` | Generic failure |

## 3. Health

`GET /api/health` (public) → `200 {"status": "ok", "service": "…"}`.

## 4. Profile and confirmed skills (implemented)

Types:

```ts
Profile    = { user_id: string, full_name: string, created_at: string, updated_at: string }
Skill      = { skill_id: number, name: string }
MeResponse = { profile: Profile, skills: Skill[], onboarding_complete: boolean }
```

`skills` is always an array, ordered by lowercase name then id.

| Route | Body / query | Success | Errors |
|---|---|---|---|
| `GET /api/me` | – | 200 `MeResponse` | 404 `profile` |
| `POST /api/me` | `{ "full_name": string }` | 200 `MeResponse` (creates if absent; an existing profile is returned unchanged — idempotent) | 422 |
| `PATCH /api/me` | `{ "full_name"?: string }` (empty body → 422) | 200 `Profile`; `updated_at` moves only if the name changed | 404 `profile`, 422 |
| `GET /api/skills?q=&limit=20` | `q` ≤ 100 chars, literal case-insensitive substring; `limit` 1–100 | 200 `{ items: Skill[], has_more: boolean }` | 422 |
| `PUT /api/me/skills/{skill_id}` | – | 204 (idempotent) | 404 `profile` / `skill`, 422 |
| `DELETE /api/me/skills/{skill_id}` | – | 204 (idempotent, unknown id is fine) | 404 `profile`, 422 |

`full_name`: whitespace collapsed and trimmed, 1–80 characters, no control characters.

## 5. Resume

Types:

```ts
ExtractedData = { skills: string[], education: object[], experience: object[], projects: object[] }
ResumeResponse = {
  resume_id: string, user_id: string, file_name: string, uploaded_at: string,
  extracted_data: ExtractedData,
  suggested_skills: Skill[]          // new (WP-6)
}
```

| Route | Body | Success | Errors |
|---|---|---|---|
| `POST /api/resumes/upload` | multipart `file` (PDF or DOCX, ≤ 5 MB) | 200 `ResumeResponse`; replaces the caller's current resume | 404 `profile` (*new: checked before extraction*), 413, 415, 422 |
| `GET /api/me/resume` *new* | – | 200 `ResumeResponse` | 404 `resume` |
| `GET /api/resumes/{resume_id}` | – | 200 (caller's own only) | 404 |
| `DELETE /api/resumes/{resume_id}` | – | 200 `{ resume_id, deleted: true }` | 404 |
| `GET /api/resumes/user/{user_id}` | must equal caller | 200 list | 404 |
| `GET /api/resumes/stats?top_n=10` | admin | 200 `{ total_resumes, top_skills: [{skill, count}] }` | 403 |

`suggested_skills` (*new*): extracted skill names mapped to dictionary entries
(case-insensitive exact name), excluding skills the caller has already confirmed, ordered
by name. Names that are not in the dictionary are dropped. Suggestions are never saved
automatically; the client confirms them with `PUT /api/me/skills/{id}`.

## 6. Tracker *(new — WP-2)*

```ts
TrackerStatus = 'NOT_INTERESTED' | 'SAVED' | 'APPLIED' | 'INTERVIEW' | 'REJECTED' | 'OFFER'
JobSummary = {
  job_id: string, title: string, company_name: string, location: string | null,
  job_type: 'FULL_TIME' | 'PART_TIME' | 'INTERNSHIP' | null,
  work_arrangement: 'ONSITE' | 'HYBRID' | 'REMOTE' | null,
  application_url: string, source: string, source_posted_at: string | null, is_active: boolean
}
TrackerItem = { job: JobSummary, status: TrackerStatus, created_at: string, updated_at: string }
```

### `PUT /api/me/jobs/{job_id}`

Body `{ "status": TrackerStatus }`. Creates or updates the caller's decision for the job.

- 200 `TrackerItem`. Repeating the same status is a no-op that still returns 200
  (`updated_at` unchanged).
- Creating a new row requires an **active** job → otherwise 404 `job`. Updating an existing
  row is allowed even if the job has since become inactive.
- 404 `profile` if no profile; 422 for a bad UUID or status.

### `GET /api/me/jobs?status=SAVED&status=APPLIED&limit=20&offset=0`

`status` is repeatable; absent = all statuses. Ordered by `updated_at` desc then `job_id`.
200 `{ items: TrackerItem[], total: number }`.

### `GET /api/me/jobs/summary`

200 `{ counts: Record<TrackerStatus, number>, total: number }` — every status present, zeros included.

### `DELETE /api/me/jobs/{job_id}`

Removes the caller's decision (undo; the job can reappear in Discover). 204, idempotent.
404 `profile` if no profile.

## 7. Discover *(new — WP-3)*

### `GET /api/discover`

| Query | Type | Rule |
|---|---|---|
| `job_type` | enum | optional, one of the `job_type` values |
| `work_arrangement` | enum | optional |
| `location` | string ≤ 100 | optional, literal case-insensitive substring |
| `q` | string ≤ 100 | optional, literal substring of title or company |
| `limit` | int | 1–50, default 20 |
| `offset` | int | 0–10,000, default 0 |

Returns active jobs that the caller has **no** tracker row for, ranked by skill coverage.

```ts
SkillRequirement = { skill_id: number, name: string, requirement_type: 'REQUIRED' | 'PREFERRED' }
JobMatch = {
  required_total: number, required_matched: number,
  preferred_total: number, preferred_matched: number,
  coverage: number | null,             // required_matched / required_total, 0..1; null if required_total = 0
  matched_skills: SkillRequirement[],  // REQUIRED first, then by name
  missing_skills: SkillRequirement[]   // REQUIRED first, then by name
}
DiscoverItem = { job: JobSummary, match: JobMatch, rank: number }
DiscoverResponse = { items: DiscoverItem[], has_more: boolean }
```

Order: `coverage` desc (nulls last), `preferred_matched` desc, `source_posted_at` desc
(nulls last), `job_id`. `rank` is SQL `RANK()` over that order (ties share a rank).
`has_more` is computed by fetching `limit + 1`.

Errors: 404 `profile`; 422 for invalid filters or unknown query params.

## 8. Skill gap *(new — WP-4)*

### `GET /api/skill-gap/roles`

200 `{ items: [{ role_category: string, job_count: number }] }` — only active, ready jobs,
sorted by `job_count` desc then name. `"Unclassified"` is included if present.

### `GET /api/me/skill-gap?role_category=Software%20Engineering&limit=30`

`role_category` required (≤ 100 chars, exact match); `limit` 1–100, default 30.

```ts
SkillGapRow = {
  skill_id: number, name: string,
  job_count: number,          // postings in the sample that mention it (once per job)
  frequency: number,          // job_count / sample_size, 0..1
  required_count: number, preferred_count: number,   // sum = job_count
  max_minimum_years: number | null, years_mentions: number,
  user_has: boolean
}
SkillGapResponse = {
  role_category: string, sample_size: number,
  skills: SkillGapRow[],      // job_count desc, then skill_id
  summary: { top_n: number, user_has_in_top_n: number }   // top_n = min(10, skills.length)
}
```

Unknown or empty role → 200 with `sample_size: 0`, `skills: []`. Errors: 404 `profile`, 422.

## 9. Jobs and admin pipeline (implemented)

See [job-pipeline.md](job-pipeline.md) for the cross-database rules. All take the job pipeline
advisory lock (shared for reads, exclusive for writes after WP-0).

| Route | Who | Notes |
|---|---|---|
| `GET /api/jobs?skip&limit&role_category&industry` | user | Ready + active documents; `{total_count, returned_count, skip, limit, jobs[]}` |
| `GET /api/jobs/search?title&limit` | user | `$text` search, regex fallback |
| `GET /api/jobs/stats` | user | counts by role, industry, source |
| `GET /api/jobs/{job_id}` | user | ready + active only |
| `POST /api/jobs/external/fetch-multi` | admin | `{sources[], limit_per_source, total_limit}`; WP-5 adds `summary {requested, inserted, updated, rejected, errors[]}` |
| `POST /api/jobs/ingest` | admin | `{job_id, raw_jd}` for an existing SQL job |
| `POST /api/jobs/{job_id}/extract-skills` | admin | re-extract one job |
| `POST /api/jobs/extract-skills/batch` | admin | re-extract all |
| `GET /api/jobs/duplicates` | admin | read-only preview |
| `DELETE /api/jobs/duplicates`, `DELETE /api/jobs/{job_id}` | admin | always 409 (disabled) |
| `GET /api/reports/skill-profile` | user | union of caller's skills and required skills of active jobs |

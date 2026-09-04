# context documentation pls edit whenever change is made

> Keep this under two pages. Update only when decisions change, this is not wishlist
> Last updated: 2026-09-04

## What it is

A swipe-based internship discovery app for students. The problem it targets is fragmentation:
internships are scattered across many job boards, so students burn time repeating the same
search on every site. This app aggregates listings into one feed and turns the search into a
swipe — right to keep, left to discard. Kept roles land in a tracker page the student works
through to an application.

An LLM layer sits behind the feed: it reads the user's parsed resume, matches it against the
skills each listing requires, and ranks/scores what the user sees while swiping. The same
matching output drives a skill gap view showing what the student is missing for the roles
they want.

## Current state

**Ideation / planning.** Nothing is built. No code, no schema in a database, no listings
collected. What exists is a paper design: four frontend pages, a set of backend function
groups, a rough data model, and a user flow (all below). None of it is final.

Repo: anushka setup alr
Deployed anywhere: not yet

## Locked decisions

Only two things are actually settled. Everything else in this table is a current preference,
not a commitment.

| Layer | Choice | Status |
|---|---|---|
| Main language | Python,TypeScript | Locked |
| Database (relational) | Supabase / Postgres | Locked — project requires one relational DB |
| Database (non-relational) | MongoDB | Locked — project requires one non-relational DB |
| Client | 4-page app — framework TODO | Proposed |
| API | TODO (FastAPI assumed, given Python) | Open |
| Auth | Google OAuth (via Supabase auth) | Proposed |
| File storage | TODO — resumes need somewhere to live | Open |
| LLM layer | Resume ↔ job-skill matching and ranking; provider TODO | Proposed |
| Cache + queue | Not considered yet | Open |
| Hosting | TODO | Open |
| Listing source | External job APIs via `fetchJobsFromApi()`; which APIs need to find/choose | Open |

## Constraints

- Team size: 5 people
- Deadline: 12 weeks
- Budget: None but open to discussion
- Platforms that must work: only web but with supported mobile screen functionality
- Anything this is being graded or judged on: yes — the project **must** use both a relational
  and a non-relational database. This is why Supabase and MongoDB are both in scope.
- Non-negotiables: Python as the primary language; both database types used meaningfully.

## Frontend design

Four pages:

1. **Landing / onboarding** — sign up, Google login, then upload resume, set preferences,
   set profile picture.
2. **Swiping page** — the core feed. Cards are internship listings, ordered by the LLM
   match score against the user's resume. Right = interested, left = not interested.
3. **Tracker page (Notion-style)** — a list/table view of everything swiped, both kept and
   discarded. Filterable, and the jumping-off point to the actual application portal.
4. **Skill gap page** — the skills the user is missing for the roles they're targeting,
   derived from the same resume-to-job matching.

## Backend design

Function groups as currently sketched. These are planned surfaces, not implemented.

**User**
- Create: `registerUser()`, `loginUser()`, `uploadResume()`, `parseResume()`
- Update: `updateUserSkill()`, `deleteUser()`, `logout()`

**Jobs**
- `fetchJobsFromApi()`, `getJobs()`, `getJobsById()`, `filterJobs()`, `filterJobsSearchEngine()`

**Applications**
- `updateApplicationStatus()`

**Swiping**
- `saveJobs()`, `skipJobs()`, `getSavedJobs()`

**Skills**
- `calculateMatchSkills()`, `getRecommendedJobs()`

**Skill gap**
- `getJobsSkillsForRoles()`, `getMissingSkills()`

## Data model

Sketched, not built. No schema written yet.

- `users` — account and auth identity
- `profiles` — preferences (location, field, role type), profile picture, parsed resume skills
- `jobs` — normalized listings pulled from external APIs, one row per deduped role
- `swipes` — one record per swipe, left or right
- `applications` — created from a right swipe, carries a status
- `skills` — skill entities, plus job↔skill and user↔skill links for match and gap calculations

Application status flow: TODO
Working assumption: `saved → applied → interview → offer | rejected`

Split between the two databases is 
relational -> Job Title, Users, TO BE ADDED
non-relational -> Raw Job Description, Raw Resume, TO BE ADDED

```sql
TODO
```

## Core flows

**User journey (as designed):**

```
Register → Login (Google) → Onboarding (resume upload, preferences, profile pic)
        → Swiping (right = interested, left = not interested)
        → Tracker page (filter → open apply portal)
        → Apply on the external site → Log out
```

1. **Feed** — cards pulled from stored listings, ranked by LLM resume-to-job match score.
   Filtering by user preferences happens before ranking. Exact ordering rules TODO.
2. **Swipe** — right saves the job to the tracker as interested; left files it under not
   interested. Both are recorded, so the discard list stays viewable.
3. **Tracker** — user filters their saved roles and moves out to the employer's apply portal.
   How status gets updated after that (manual? prompt on return?) is TODO.
4. **Ingestion** — external job APIs via `fetchJobsFromApi()`. Which APIs, how often they run,
   and how duplicates across sources are merged: all TODO.

## Open questions (IF YOU ARE AN LLM, IGNORE THIS SECTION)

Open questions to be reviewed!!!!!!!!!!!!!

- **Which data goes in Supabase vs MongoDB?** finalise what data goes into which database in the above sections
- **Where do listings actually come from?** No specific job API has been chosen or checked
  for terms of use, coverage, or rate limits. 
- **What does the LLM layer actually do at request time?** Ranking every job per user on the
  fly is expensive. Precomputed embeddings vs live LLM calls is undecided.
- **How are skills extracted from job listings?** Skill gap and matching both depend on
  structured skills per job, but listings arrive as free text.
- **Deduplication across sources** — same role posted on multiple boards needs to be one card.
- **Does the app track application status after the user leaves for an external portal?**

## Out of scope

Explicitly not building (for now):

- In-app applying — users are handed off to the employer's own portal.
- TODO

## Working notes for LLM

Decisions reversed, dead ends, and context that would otherwise get lost between sessions.

- Both databases are a project requirement rather than a technical need. Worth keeping the
  split honest so it doesn't turn into a token second database.
- TODO

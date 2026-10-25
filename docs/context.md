# Project context

Updated 25 October 2026. Scope and work packages: [PRD.md](PRD.md). Contracts:
[API.md](API.md). Schema: [erd.md](erd.md). Setup: [README.md](README.md).

Jobless Simulator (INF2003 Group 77) helps students discover internships and entry-level
jobs that match their confirmed skills, track decisions and applications, and see the
skill gap for a target role. The proposal was approved without changes ("good to go ahead
with implementation"). Final submission: 29 November 2026, 11:30 PM.

Stack: React/Vite/TypeScript frontend; Python 3.14 FastAPI backend; Supabase Auth (Google)
and Supabase PostgreSQL via psycopg2; MongoDB via pymongo. Python owns all data access.

Built: auth, profile and confirmed skills on PostgreSQL; resume upload and rule-based
extraction into MongoDB; job ingestion from three keyless providers with cross-database
readiness; job list/search/stats; skill editor component.

Remaining (PRD v2 work packages WP-0 to WP-11): dev proxy and read-lock fix, SQL migration
003, tracker API, ranked Discover feed, MongoDB skill-gap aggregation, ingestion
improvements, resume-to-skills flow, Discover/Vault/Skill Gap screens, benchmark, user manual.

Extraction is rule-based (no LLM) by decision for this build. Matching uses stored skill
links; scores are skill coverage, never hiring probability.

Owners: Zhihao (integration, review, WP-0/WP-10), Jason (PostgreSQL, tracker, Discover
API), Jiaxin (MongoDB, skill gap, ingestion), Nasya (Discover UI, app shell), Anushka
(resume/skills UI, Vault, Skill Gap UI).

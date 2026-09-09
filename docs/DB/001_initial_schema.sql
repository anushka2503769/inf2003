-- Jobless Simulator: provisional MVP PostgreSQL skeleton for Supabase.
-- Apply once in a fresh development project using the Supabase SQL Editor.
-- Requires Supabase's existing auth.users table and standard database roles.
-- This is a bootstrap script, not an upgrade/reset script. Existing tables cause
-- an error and the transaction rolls back; do not drop tables to rerun it.

BEGIN;

CREATE TABLE public.users (
    user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE RESTRICT,
    full_name text NOT NULL CHECK (length(btrim(full_name)) > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.skills (
    skill_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (length(btrim(name)) > 0 AND name = btrim(name))
);

-- Python and python cannot become separate canonical skills.
-- Synonyms (e.g. Postgres/PostgreSQL) still require application normalization.
CREATE UNIQUE INDEX skills_name_unique ON public.skills (lower(name));

CREATE TABLE public.jobs (
    job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source text NOT NULL CHECK (length(btrim(source)) > 0),
    external_job_id text NOT NULL CHECK (length(btrim(external_job_id)) > 0),
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    company_name text NOT NULL CHECK (length(btrim(company_name)) > 0),
    location text,
    job_type text CHECK (job_type IN ('FULL_TIME', 'PART_TIME', 'INTERNSHIP')),
    work_arrangement text CHECK (work_arrangement IN ('ONSITE', 'HYBRID', 'REMOTE')),
    application_url text NOT NULL CHECK (length(btrim(application_url)) > 0),
    source_posted_at timestamptz,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT jobs_source_external_id_unique UNIQUE (source, external_job_id)
);

CREATE TABLE public.user_skills (
    user_id uuid NOT NULL REFERENCES public.users (user_id) ON DELETE RESTRICT,
    skill_id integer NOT NULL REFERENCES public.skills (skill_id) ON DELETE RESTRICT,
    PRIMARY KEY (user_id, skill_id)
);

CREATE TABLE public.job_skills (
    job_id uuid NOT NULL REFERENCES public.jobs (job_id) ON DELETE RESTRICT,
    skill_id integer NOT NULL REFERENCES public.skills (skill_id) ON DELETE RESTRICT,
    requirement_type text NOT NULL CHECK (requirement_type IN ('REQUIRED', 'PREFERRED')),
    PRIMARY KEY (job_id, skill_id)
);

CREATE TABLE public.user_jobs (
    user_id uuid NOT NULL REFERENCES public.users (user_id) ON DELETE RESTRICT,
    job_id uuid NOT NULL REFERENCES public.jobs (job_id) ON DELETE RESTRICT,
    status text NOT NULL CHECK (
        status IN ('NOT_INTERESTED', 'SAVED', 'APPLIED', 'INTERVIEW', 'REJECTED', 'OFFER')
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, job_id)
);

-- The first column of each composite primary key is already indexed.
-- Index the other FK for reverse lookups and checks on referenced rows.
CREATE INDEX user_skills_skill_id_idx ON public.user_skills (skill_id);
CREATE INDEX job_skills_skill_id_idx ON public.job_skills (skill_id);
CREATE INDEX user_jobs_job_id_idx ON public.user_jobs (job_id);

-- Application data is accessed through Python, not directly by browser clients.
-- No client RLS policies are created: anon/authenticated cannot access these tables.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_jobs ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE
    public.users, public.skills, public.jobs,
    public.user_skills, public.job_skills, public.user_jobs
FROM PUBLIC, anon, authenticated;

REVOKE ALL PRIVILEGES ON SEQUENCE public.skills_skill_id_seq
FROM PUBLIC, anon, authenticated;

-- Baseline for trusted backend access using a Supabase secret key.
-- service_role bypasses RLS: Python MUST verify the login token and enforce
-- ownership itself. Never trust a user_id supplied by a browser request.
GRANT USAGE ON SCHEMA public TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    public.users, public.skills, public.jobs,
    public.user_skills, public.job_skills, public.user_jobs
TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.skills_skill_id_seq TO service_role;

-- Python must maintain updated_at when changing users/user_jobs and last_seen_at
-- when refreshing jobs. DEFAULT now() applies on INSERT only; no triggers yet.
-- Google sign-in creates auth.users. The future Python onboarding route must
-- explicitly create public.users with the verified account ID and a display name.

COMMIT;

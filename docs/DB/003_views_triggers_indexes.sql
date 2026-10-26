-- Jobless Simulator: migration 003 - views, triggers and indexes.
-- Apply after 001 (not 002) in the Supabase SQL Editor. Adds database objects
-- only; no table or column changes. Like 001 this is not an upgrade script:
-- if any object already exists the statement fails and the transaction rolls
-- back; do not drop objects to rerun it.

BEGIN;

-- 1. Keep updated_at honest. The trigger fires only when a row really changes,
-- so a no-op UPDATE (same values) leaves updated_at alone.
CREATE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_set_updated_at
BEFORE UPDATE ON public.users
FOR EACH ROW
WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER user_jobs_set_updated_at
BEFORE UPDATE ON public.user_jobs
FOR EACH ROW
WHEN (OLD.* IS DISTINCT FROM NEW.*)
EXECUTE FUNCTION public.set_updated_at();

-- 2. Non-standard integrity constraint: a NEW tracker row must point at an
-- active job. A CHECK cannot read another table, so a trigger does it. Only
-- INSERT is guarded: rows for jobs that are deactivated later stay valid and
-- can still be updated.
CREATE FUNCTION public.user_jobs_require_active_job()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    -- PostgreSQL fires BEFORE INSERT row triggers before it detects an
    -- ON CONFLICT, so an upsert (INSERT ... ON CONFLICT DO UPDATE) on an
    -- existing tracker row would be rejected here even though it becomes an
    -- UPDATE. If the (user_id, job_id) row already exists, let it through:
    -- either it turns into the allowed update, or the primary key rejects it.
    -- A genuinely new row for an inactive job still fails. Two concurrent first
    -- inserts for an inactive job both fail (neither row exists). Known,
    -- accepted race: a concurrent DELETE plus upsert could slip a row in; this
    -- is documented rather than solved with locking.
    IF EXISTS (
        SELECT 1 FROM public.user_jobs
        WHERE user_id = NEW.user_id AND job_id = NEW.job_id
    ) THEN
        RETURN NEW;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.jobs
        WHERE job_id = NEW.job_id AND is_active
    ) THEN
        RAISE EXCEPTION 'job % is not active and cannot be added to a tracker', NEW.job_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER user_jobs_requires_active_job
BEFORE INSERT ON public.user_jobs
FOR EACH ROW
EXECUTE FUNCTION public.user_jobs_require_active_job();

-- 3. Requirement counts per active job (jobs with no skill rows are absent).
CREATE VIEW public.v_job_requirement_counts AS
SELECT
    js.job_id,
    COUNT(*) FILTER (WHERE js.requirement_type = 'REQUIRED') AS required_total,
    COUNT(*) FILTER (WHERE js.requirement_type = 'PREFERRED') AS preferred_total
FROM public.job_skills AS js
JOIN public.jobs AS j ON j.job_id = js.job_id
WHERE j.is_active
GROUP BY js.job_id;

-- 4. Tracker size per user and status (statuses with no rows are absent).
CREATE VIEW public.v_user_tracker_summary AS
SELECT
    user_id,
    status,
    COUNT(*) AS job_count
FROM public.user_jobs
GROUP BY user_id, status;

-- 5. Indexes for Discover filters, Discover ordering and tracker tabs.
CREATE INDEX jobs_active_type_arrangement_idx
    ON public.jobs (job_type, work_arrangement)
    WHERE is_active;

CREATE INDEX jobs_active_posted_at_idx
    ON public.jobs (source_posted_at DESC)
    WHERE is_active;

CREATE INDEX user_jobs_user_status_idx
    ON public.user_jobs (user_id, status);

-- 6. Same access model as 001: browser roles get nothing, the trusted Python
-- backend (service_role) can read the views.
REVOKE ALL PRIVILEGES ON TABLE
    public.v_job_requirement_counts, public.v_user_tracker_summary
FROM PUBLIC, anon, authenticated;

GRANT SELECT ON TABLE
    public.v_job_requirement_counts, public.v_user_tracker_summary
TO service_role;

COMMIT;

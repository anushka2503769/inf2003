import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { routes } from '../../app/routes'
import { Badge, RequirementLabel } from '../../components/Badge'
import { Button, buttonClass } from '../../components/Button'
import { EmptyState, Notice, Spinner } from '../../components/Feedback'
import { Icon } from '../../components/Icon'
import { Meter } from '../../components/Meter'
import { JOB_TYPES, WORK_ARRANGEMENTS, type JobType, type WorkArrangement } from '../../types/api'
import type { DiscoverClientError } from './realClient'
import { discoverClient, type DiscoverClient } from './client'
import type { DiscoverDecision, DiscoverFilters, DiscoverItem, SkillRequirement } from './types'
import './discover.css'

const PAGE_SIZE = 20

type FeedEntry = { item: DiscoverItem; failedDecision?: DiscoverDecision }

function filtersFromParams(params: URLSearchParams): DiscoverFilters {
  const filters: DiscoverFilters = {}
  const jobType = params.get('job_type')
  const arrangement = params.get('work_arrangement')
  if (JOB_TYPES.includes(jobType as JobType)) filters.job_type = jobType as JobType
  if (WORK_ARRANGEMENTS.includes(arrangement as WorkArrangement)) filters.work_arrangement = arrangement as WorkArrangement
  const location = params.get('location')?.trim()
  const q = params.get('q')?.trim()
  if (location) filters.location = location
  if (q) filters.q = q
  return filters
}

function messageFor(error: unknown): string {
  const coded = error as Partial<DiscoverClientError> | null
  if (coded?.code === 'validation_failed') return 'Those filters are not valid. Shorten the location or keyword (100 characters at most) and apply again.'
  if (coded?.code === 'network_error') return 'Cannot reach the server. Check your connection, then try again.'
  if (coded?.code === 'service_unavailable' || (coded?.status ?? 0) >= 500) return 'The server had a problem loading jobs. Try again in a moment.'
  return 'Could not load jobs. Try again.'
}

function isProfileMissing(error: unknown): boolean {
  const coded = error as Partial<DiscoverClientError> | null
  return coded?.code === 'not_found' && coded.details?.resource === 'profile'
}

function isJobGone(error: unknown): boolean {
  const coded = error as Partial<DiscoverClientError> | null
  return coded?.code === 'not_found' && coded.details?.resource === 'job'
}

function isHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value)
}

// Below this width the shell switches to the mobile layout and filters move into a sheet.
const MOBILE_QUERY = '(max-width: 767.98px)'

function isMobileViewport(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(MOBILE_QUERY).matches
}

const JOB_TYPE_LABEL: Record<JobType, string> = { FULL_TIME: 'Full time', PART_TIME: 'Part time', INTERNSHIP: 'Internship' }
const ARRANGEMENT_LABEL: Record<WorkArrangement, string> = { ONSITE: 'On-site', HYBRID: 'Hybrid', REMOTE: 'Remote' }

const POSTED_FORMAT = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })

function bySkillPriority(a: SkillRequirement, b: SkillRequirement): number {
  return Number(a.requirement_type !== 'REQUIRED') - Number(b.requirement_type !== 'REQUIRED') || a.name.localeCompare(b.name)
}

function filterKey(filters: DiscoverFilters): string {
  return JSON.stringify([filters.job_type ?? '', filters.work_arrangement ?? '', filters.location?.trim() ?? '', filters.q?.trim() ?? ''])
}

function filterSummary(filters: DiscoverFilters): string {
  return [
    filters.job_type && JOB_TYPE_LABEL[filters.job_type],
    filters.work_arrangement && ARRANGEMENT_LABEL[filters.work_arrangement],
    filters.location,
    filters.q && `“${filters.q}”`,
  ].filter(Boolean).join(' · ')
}

/** "You have" gets a plain check, "Missing" a plain dash: markers, not checkboxes. */
function SkillList({ skills, have, label }: { skills: SkillRequirement[]; have: boolean; label: string }) {
  if (skills.length === 0) return <p className="t-meta">{have ? 'No matched skills' : 'No missing skills'}</p>
  return (
    <ul className="dskills" aria-label={label}>
      {[...skills].sort(bySkillPriority).map(skill => (
        <li key={skill.skill_id} className={have ? 'dskills__item' : 'dskills__item dskills__item--missing'}>
          {have
            ? <Icon name="check" className="dskills__mark dskills__mark--have" />
            : <span className="dskills__mark dskills__mark--missing" aria-hidden="true" />}
          <span className="dskills__name">{skill.name}</span>
          <RequirementLabel required={skill.requirement_type === 'REQUIRED'} />
        </li>
      ))}
    </ul>
  )
}

/** Inline failure with one recovery button; the button can carry data-retry for focus. */
function FailureLine({ children, actionLabel, onAction, disabled, retry }: {
  children: ReactNode
  actionLabel: string
  onAction: () => void
  disabled?: boolean
  retry?: boolean
}) {
  return (
    <div className="inline-error" role="alert">
      <Icon name="warning-circle" />
      <span className="inline-error__text">{children}</span>
      <Button variant="secondary" icon="arrow-clockwise" disabled={disabled} onClick={onAction} data-retry={retry || undefined}>{actionLabel}</Button>
    </div>
  )
}

function JobCard({ entry, onDecision, pending, onRetry, first }: {
  entry: FeedEntry
  first: boolean
  onDecision: (id: string, status: DiscoverDecision) => void
  pending: boolean
  onRetry: (entry: FeedEntry) => void
}) {
  const { job } = entry.item
  const { match } = entry.item
  const posted = job.source_posted_at ? `Posted ${POSTED_FORMAT.format(new Date(job.source_posted_at))}` : 'Posting date not provided'
  const postingLink = isHttpUrl(job.application_url)
    ? <a className="link" href={job.application_url} target="_blank" rel="noopener noreferrer">Open posting<Icon name="arrow-square-out" /></a>
    : null
  return (
    <article className="card dcard" aria-label={`${job.title} at ${job.company_name}`}>
      <header className="dcard__head">
        <p className="dcard__meta t-meta">
          <span>Match rank {entry.item.rank}</span>
          <span className="dot-sep" aria-hidden="true">·</span>
          <span>{posted}</span>
        </p>
        <h2 className="t-title dcard__title">{job.title}</h2>
        <p className="dcard__company">
          {job.company_name} <span className="dot-sep" aria-hidden="true">·</span> {job.location ?? 'Location not provided'}
        </p>
        <div className="dcard__tags">
          {(job.job_type || job.work_arrangement) && (
            <ul className="dcard__badges" aria-label="Job details">
              {job.job_type && <li><Badge>{JOB_TYPE_LABEL[job.job_type]}</Badge></li>}
              {job.work_arrangement && <li><Badge>{ARRANGEMENT_LABEL[job.work_arrangement]}</Badge></li>}
            </ul>
          )}
          {postingLink}
        </div>
      </header>
      <section className="dcard__match" aria-label="Skill match">
        {match.coverage === null ? (
          <>
            <h3 className="dcard__match-title">Skill match</h3>
            <Notice tone="info">
              <strong>No skill requirements were extracted for this job.</strong>{' '}
              <span className="muted">We could not read a skills list from this posting{postingLink ? ', so open the posting to judge for yourself.' : '.'}</span>
            </Notice>
          </>
        ) : (
          <>
            <div className="dcard__match-head">
              <h3 className="dcard__match-title">You have {match.required_matched} of {match.required_total} required skills</h3>
              {match.preferred_total > 0 && <span className="t-meta mono">{match.preferred_matched} of {match.preferred_total} preferred</span>}
            </div>
            {match.required_total > 0 && (
              <Meter value={match.required_matched} total={match.required_total} label={`Required skill coverage: ${match.required_matched} of ${match.required_total}`} />
            )}
            <div className="dcard__skills">
              <div className="dcard__skill-col">
                <h4 className="t-label">You have</h4>
                <SkillList skills={match.matched_skills} have label="Matched skills" />
              </div>
              <div className="dcard__skill-col">
                <h4 className="t-label">Missing</h4>
                <SkillList skills={match.missing_skills} have={false} label="Missing skills" />
              </div>
            </div>
          </>
        )}
      </section>
      {entry.failedDecision && (
        <div className="dcard__error">
          <FailureLine actionLabel="Retry" onAction={() => onRetry(entry)} retry>
            <span className="dcard__error-long">
              <strong>{entry.failedDecision === 'SAVED' ? `Couldn’t save “${job.title}”.` : `Couldn’t mark “${job.title}” as not interested.`}</strong>{' '}
              Your decision was not recorded, and the card stays here.
            </span>
            <span className="dcard__error-short">
              <strong>{entry.failedDecision === 'SAVED' ? 'Couldn’t save.' : 'Couldn’t record that.'}</strong> Not recorded yet.
            </span>
          </FailureLine>
        </div>
      )}
      <div className="dcard__decide">
        <Button className="dcard__pass" variant="secondary" kbdLeft="←" icon="x" disabled={pending} onClick={() => onDecision(job.job_id, 'NOT_INTERESTED')} aria-label={`Not interested in ${job.title}`} aria-keyshortcuts={first ? 'ArrowLeft' : undefined}>Not interested</Button>
        <span className="dcard__hint t-meta">Decide with the arrow keys</span>
        <Button className="dcard__save" variant="primary" icon="bookmark-simple" kbd="→" data-primary disabled={pending} onClick={() => onDecision(job.job_id, 'SAVED')} aria-label={`Save ${job.title}`} aria-keyshortcuts={first ? 'ArrowRight' : undefined}>Save</Button>
      </div>
    </article>
  )
}

/** Shape of a job card while the first page loads. */
function SkeletonCard() {
  return (
    <div className="card dcard">
      <div className="dcard__head" aria-hidden="true">
        <span className="skel dskel dskel--meta" />
        <span className="skel dskel dskel--title" />
        <span className="skel dskel dskel--line" />
        <span className="dcard__tags"><span className="skel dskel dskel--badge" /><span className="skel dskel dskel--badge dskel--badge-short" /></span>
      </div>
      <div className="dcard__match" aria-hidden="true">
        <span className="skel dskel dskel--head" />
        <span className="meter">{Array.from({ length: 5 }, (_, index) => <span key={index} className="skel dskel dskel--cell" />)}</span>
        <span className="skel dskel dskel--line" style={{ width: '60%' }} />
        <span className="skel dskel dskel--line" style={{ width: '52%' }} />
        <span className="skel dskel dskel--line" style={{ width: '57%' }} />
      </div>
      <div className="dcard__decide">
        <p className="toast-line t-meta" role="status"><Spinner size="sm" />Ranking postings against your skills</p>
      </div>
    </div>
  )
}

export function DiscoverFeed({ client = discoverClient, onProfileMissing }: {
  client?: DiscoverClient
  onProfileMissing?: () => void | Promise<void>
}) {
  const [searchParams, setSearchParams] = useSearchParams()
  const queryString = searchParams.toString()
  const committed = useMemo(() => filtersFromParams(new URLSearchParams(queryString)), [queryString])
  const [draft, setDraft] = useState<DiscoverFilters>(committed)
  const [entries, setEntries] = useState<FeedEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [nextError, setNextError] = useState<string | null>(null)
  const [loadingNext, setLoadingNext] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [pendingIds, setPendingIds] = useState<Set<string>>(() => new Set())
  const [notice, setNotice] = useState<string | null>(null)
  const [profileMissing, setProfileMissing] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)
  const sheetId = useId()
  const sheetRef = useRef<HTMLDivElement>(null)
  const filtersButtonRef = useRef<HTMLButtonElement>(null)
  const cardsRef = useRef<HTMLDivElement>(null)
  const refocus = useRef(false)
  const requestId = useRef(0)
  const loadedCount = useRef(0)
  const decidedCount = useRef(0)
  const seenIds = useRef(new Set<string>())
  const loadingPage = useRef(false)
  const pageRequestId = useRef(0)
  const entriesRef = useRef(entries)
  entriesRef.current = entries

  useEffect(() => setDraft(committed), [queryString]) // submitted URL is the source of truth

  // A profile reload failure must never mask the state we already set, nor become an unhandled rejection.
  const notifyProfileMissing = useCallback(async () => {
    try { await onProfileMissing?.() } catch { /* the load/decision error is already shown */ }
  }, [onProfileMissing])

  // After a card is removed or restored, keep keyboard focus inside the feed.
  useEffect(() => {
    if (!refocus.current) return
    refocus.current = false
    const active = document.activeElement
    if (active && active !== document.body && !cardsRef.current?.contains(active)) return
    const target = cardsRef.current?.querySelector<HTMLElement>('[data-retry]') ?? cardsRef.current?.querySelector<HTMLElement>('[data-primary]:not(:disabled)')
    target?.focus()
  }, [entries])

  const loadFirst = useCallback(async () => {
    const id = ++requestId.current
    pageRequestId.current += 1
    loadedCount.current = 0
    decidedCount.current = 0
    seenIds.current = new Set()
    setEntries([])
    setLoading(true)
    setLoadError(null)
    setNextError(null)
    setNotice(null)
    setProfileMissing(false)
    setLoadingNext(false)
    loadingPage.current = false
    setPendingIds(new Set())
    setHasMore(false)
    try {
      const response = await client.list(committed, 0, PAGE_SIZE)
      if (id !== requestId.current) return
      const unique = response.items.filter(item => !seenIds.current.has(item.job.job_id))
      unique.forEach(item => seenIds.current.add(item.job.job_id))
      loadedCount.current = unique.length
      setEntries(unique.map(item => ({ item })))
      setHasMore(response.has_more)
    } catch (error) {
      if (id !== requestId.current) return
      setLoadError(messageFor(error))
      if (isProfileMissing(error)) {
        setProfileMissing(true)
        await notifyProfileMissing()
      }
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [client, committed, notifyProfileMissing])

  useEffect(() => {
    void loadFirst()
    return () => { requestId.current += 1 }
  }, [loadFirst])

  const loadNext = useCallback(async () => {
    if (loadingPage.current || !hasMore || loading || pendingIds.size > 0) return
    loadingPage.current = true
    setLoadingNext(true)
    setNextError(null)
    const id = requestId.current
    const pageId = ++pageRequestId.current
    const offset = Math.max(0, loadedCount.current - decidedCount.current)
    try {
      const response = await client.list(committed, offset, PAGE_SIZE)
      if (id !== requestId.current || pageId !== pageRequestId.current) return
      const unique = response.items.filter(item => !seenIds.current.has(item.job.job_id))
      unique.forEach(item => seenIds.current.add(item.job.job_id))
      loadedCount.current += unique.length
      setEntries(current => [...current, ...unique.map(item => ({ item }))])
      // A non-advancing page cannot be retried safely with offset pagination.
      setHasMore(response.has_more && unique.length > 0)
    } catch (error) {
      if (id === requestId.current && pageId === pageRequestId.current) {
        setNextError(messageFor(error))
        if (isProfileMissing(error)) await notifyProfileMissing()
      }
    } finally {
      if (pageId === pageRequestId.current) {
        loadingPage.current = false
        if (id === requestId.current) setLoadingNext(false)
      }
    }
  }, [client, committed, hasMore, loading, notifyProfileMissing, pendingIds])

  useEffect(() => {
    if (!loading && !loadError && !nextError && entries.length <= 3 && hasMore && pendingIds.size === 0) void loadNext()
  }, [entries.length, hasMore, loadError, loading, loadNext, nextError, pendingIds.size])

  const decide = useCallback(async (id: string, status: DiscoverDecision) => {
    const current = entriesRef.current
    const index = current.findIndex(entry => entry.item.job.job_id === id)
    if (index < 0) return
    const entry = current[index]
    const generation = requestId.current
    if (loadingPage.current) {
      pageRequestId.current += 1 // Discard a prefetch sent before this PUT changed the feed.
      loadingPage.current = false
      setLoadingNext(false)
    }
    setPendingIds(ids => new Set(ids).add(id))
    setNotice(null)
    refocus.current = true
    setEntries(rows => rows.filter(row => row.item.job.job_id !== id))
    try {
      await client.decide(id, status)
      if (generation === requestId.current) decidedCount.current += 1
    } catch (error) {
      if (generation !== requestId.current) return
      if (isJobGone(error)) {
        // Permanent failure: the job is no longer listed server-side, so retrying cannot succeed.
        decidedCount.current += 1
        setNotice('This job is no longer available.')
      } else {
        refocus.current = true
        setEntries(rows => {
          if (rows.some(row => row.item.job.job_id === id)) return rows
          const restored = [...rows]
          restored.splice(Math.min(index, restored.length), 0, { item: entry.item, failedDecision: status })
          return restored
        })
        if (isProfileMissing(error)) await notifyProfileMissing()
      }
    } finally {
      if (generation === requestId.current) setPendingIds(ids => { const next = new Set(ids); next.delete(id); return next })
    }
  }, [client, notifyProfileMissing])

  // Filters and reloads are blocked while decisions are in flight so a failed PUT can never be dropped silently.
  const busyDeciding = pendingIds.size > 0

  const closeSheet = useCallback(() => {
    setSheetOpen(false)
    filtersButtonRef.current?.focus()
  }, [])

  const submitFilters = (event: FormEvent) => {
    event.preventDefault()
    if (busyDeciding) return
    const params = new URLSearchParams()
    Object.entries(draft).forEach(([key, value]) => { if (value?.trim()) params.set(key, value.trim()) })
    setSearchParams(params)
    if (sheetOpen) closeSheet()
  }

  const onKeyDown = useCallback((event: globalThis.KeyboardEvent) => {
    const target = event.target as HTMLElement
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.repeat || target.isContentEditable || target.closest('input, textarea, select')) return
    // The arrow keys belong to the filter sheet while it is open.
    if (sheetOpen) return
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    const first = entriesRef.current[0]
    if (!first) return
    event.preventDefault()
    void decide(first.item.job.job_id, event.key === 'ArrowLeft' ? 'NOT_INTERESTED' : 'SAVED')
  }, [decide, sheetOpen])

  useEffect(() => {
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onKeyDown])

  // Mobile filter sheet: focus moves in, Tab stays in, Escape closes; widening to desktop closes it.
  useEffect(() => {
    if (!sheetOpen) return
    document.getElementById('discover-keyword')?.focus()
    const onSheetKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeSheet()
        return
      }
      if (event.key !== 'Tab' || !sheetRef.current) return
      const focusable = [...sheetRef.current.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, a[href]')]
        .filter(element => element.offsetParent !== null)
      if (focusable.length === 0) return
      const firstControl = focusable[0]
      const lastControl = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === firstControl) {
        event.preventDefault()
        lastControl.focus()
      } else if (!event.shiftKey && document.activeElement === lastControl) {
        event.preventDefault()
        firstControl.focus()
      }
    }
    document.addEventListener('keydown', onSheetKey)
    const query = typeof window.matchMedia === 'function' ? window.matchMedia(MOBILE_QUERY) : null
    const onWiden = () => { if (query && !query.matches) setSheetOpen(false) }
    query?.addEventListener('change', onWiden)
    // The page behind the sheet must not scroll while it is open.
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onSheetKey)
      query?.removeEventListener('change', onWiden)
      document.body.style.overflow = previousOverflow
    }
  }, [sheetOpen, closeSheet])

  const changeFilters = () => {
    // Opening the filter controls must not change the submitted URL or fetch new results.
    if (isMobileViewport()) setSheetOpen(true)
    else document.getElementById('discover-job-type')?.focus()
  }

  const checkAgain = () => { if (!busyDeciding) void loadFirst() }

  if (profileMissing && !loading) {
    return (
      <div className="discover discover-redirect" role="region" aria-label="Discover jobs">
        <div className="discover-redirect__body" role="status">
          <Spinner />
          <h1 className="t-title-sm">Let’s set up your profile first.</h1>
          <p className="t-body muted">Discover needs your name before it can rank anything. Taking you to the first step.</p>
        </div>
        <Link className={buttonClass({ variant: 'secondary' })} to={routes.welcome}>Go now<Icon name="arrow-right" /></Link>
      </div>
    )
  }

  const filtered = filterKey(committed) !== filterKey({})
  const dirty = filterKey(draft) !== filterKey(committed)
  const summary = filterSummary(committed)
  const plus = hasMore ? '+' : ''
  const meta = loading
    ? { long: 'Loading', short: 'Loading' }
    : loadError
      ? null
      : entries.length === 0
        ? { long: filtered ? '0 left for these filters' : '0 left', short: '0 left' }
        : {
            long: `${entries.length}${plus} ${entries.length === 1 && !hasMore ? 'posting' : 'postings'} ranked for you`,
            short: `${entries.length}${plus} ranked`,
          }
  const current = entries[0]

  return (
    <div className="discover" role="region" aria-label="Discover jobs">
      <header className="page-head discover__head">
        <div className="discover__head-row">
          <h1 className="page-head__title">Discover</h1>
          {meta && <span className="t-meta mono">{meta.long}</span>}
        </div>
        <p className="page-head__lede">Postings ranked by how many of their required skills you already have.</p>
      </header>
      <div className="discover__bar">
        <Button ref={filtersButtonRef} size="lg" icon="sliders-horizontal" aria-haspopup="dialog" aria-expanded={sheetOpen} aria-controls={sheetId} onClick={() => setSheetOpen(true)}>
          Filters
        </Button>
        {meta && <span className="t-meta mono">{meta.short}</span>}
      </div>
      {sheetOpen && <div className="discover-scrim" aria-hidden="true" onClick={closeSheet} />}
      <div
        id={sheetId}
        ref={sheetRef}
        className={sheetOpen ? 'discover-filters is-open' : 'discover-filters'}
        role={sheetOpen ? 'dialog' : undefined}
        aria-modal={sheetOpen || undefined}
        aria-labelledby={sheetOpen ? `${sheetId}-title` : undefined}
      >
        <div className="discover-filters__head">
          <span className="discover-filters__grab" aria-hidden="true" />
          <h2 id={`${sheetId}-title`} className="t-heading">Filters</h2>
          <Button variant="ghost" size="lg" iconOnly icon="x" aria-label="Close filters" onClick={closeSheet} />
        </div>
        <form className="discover-filters__form" role="search" aria-label="Filter jobs" onSubmit={submitFilters}>
          <div className="field discover-filters__q">
            <label className="field__label" htmlFor="discover-keyword">Keyword</label>
            <div className="field__control">
              <Icon name="magnifying-glass" />
              <input id="discover-keyword" className="field__input" maxLength={100} enterKeyHint="search" placeholder="Search job titles or companies" value={draft.q ?? ''} onChange={event => setDraft(value => ({ ...value, q: event.target.value || undefined }))} />
            </div>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="discover-job-type">Job type</label>
            <select id="discover-job-type" className="field__input" value={draft.job_type ?? ''} onChange={event => setDraft(value => ({ ...value, job_type: (event.target.value || undefined) as JobType | undefined }))}>
              <option value="">Any type</option>{JOB_TYPES.map(value => <option key={value} value={value}>{JOB_TYPE_LABEL[value]}</option>)}
            </select>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="discover-arrangement">Work arrangement</label>
            <select id="discover-arrangement" className="field__input" value={draft.work_arrangement ?? ''} onChange={event => setDraft(value => ({ ...value, work_arrangement: (event.target.value || undefined) as WorkArrangement | undefined }))}>
              <option value="">Any arrangement</option>{WORK_ARRANGEMENTS.map(value => <option key={value} value={value}>{ARRANGEMENT_LABEL[value]}</option>)}
            </select>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="discover-location">Location</label>
            <input id="discover-location" className="field__input" maxLength={100} placeholder="e.g. Jurong" value={draft.location ?? ''} onChange={event => setDraft(value => ({ ...value, location: event.target.value || undefined }))} />
          </div>
          <div className="discover-filters__actions">
            <Button className="discover-filters__clear" size="lg" onClick={() => setDraft({})}>Clear</Button>
            <Button type="submit" variant={dirty ? 'primary' : 'secondary'} disabled={busyDeciding}>Apply filters</Button>
          </div>
        </form>
        {dirty && <p className="discover-filters__dirty">Changes apply when you press Apply filters or Enter.</p>}
      </div>
      {loading && <SkeletonCard />}
      {!loading && loadError && <FailureLine actionLabel="Try again" disabled={busyDeciding} onAction={checkAgain}>{loadError}</FailureLine>}
      {!loading && !loadError && entries.length === 0 && !hasMore && !loadingNext && !busyDeciding && (
        <section className="card discover-empty" aria-live="polite">
          <EmptyState
            icon="check"
            title="You’ve seen everything that matches."
            actions={<>
              <Button variant="primary" icon="sliders-horizontal" onClick={changeFilters}>Change filters</Button>
              <Button icon="arrow-clockwise" onClick={checkAgain}>Check again</Button>
            </>}
          >
            {summary
              ? <>There is nothing left for <strong>{summary}</strong> that you have not decided on. Loosen a filter, or check again after the next job refresh.</>
              : 'There is nothing left that you have not decided on. Check again after the next job refresh.'}
          </EmptyState>
        </section>
      )}
      {!loading && !loadError && entries.length === 0 && busyDeciding && <p role="status" className="discover__status toast-line t-meta"><Spinner size="sm" />Saving your decision…</p>}
      {notice && <div role="status"><Notice tone="info">{notice}</Notice></div>}
      {!loadError && current && <div className="discover__cards" ref={cardsRef}>
        {/* One posting at a time; the rest of the loaded queue waits behind it. */}
        <JobCard first key={current.item.job.job_id} entry={current} pending={pendingIds.has(current.item.job.job_id)} onDecision={(id, status) => void decide(id, status)} onRetry={retry => void decide(retry.item.job.job_id, retry.failedDecision ?? 'SAVED')} />
      </div>}
      {loadingNext && entries.length === 0 && <p className="discover__status toast-line t-meta" role="status"><Spinner size="sm" />Loading more jobs…</p>}
      {nextError && <FailureLine actionLabel="Try loading more" onAction={() => void loadNext()}>{nextError}</FailureLine>}
    </div>
  )
}

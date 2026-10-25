import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'

import { JOB_TYPES, WORK_ARRANGEMENTS, type JobType, type WorkArrangement } from '../../types/api'
import type { DiscoverClientError } from './realClient'
import { discoverClient, type DiscoverClient } from './client'
import type { DiscoverDecision, DiscoverFilters, DiscoverItem } from './types'
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
  if (coded?.code === 'network_error') return 'Cannot reach the server. Check your connection, then try again.'
  if (coded?.code === 'service_unavailable' || (coded?.status ?? 0) >= 500) return 'The server had a problem loading jobs. Try again in a moment.'
  return 'Could not load jobs. Try again.'
}

function isProfileMissing(error: unknown): boolean {
  const coded = error as Partial<DiscoverClientError> | null
  return coded?.code === 'not_found' && coded.details?.resource === 'profile'
}

function JobCard({ entry, onDecision, pending, onRetry }: {
  entry: FeedEntry
  onDecision: (id: string, status: DiscoverDecision) => void
  pending: boolean
  onRetry: (entry: FeedEntry) => void
}) {
  const { job } = entry.item
  const { match } = entry.item
  const posted = job.source_posted_at
    ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(job.source_posted_at))
    : 'Date not provided'
  const coveragePercent = match.coverage === null ? undefined : Math.round(match.coverage * 100)
  return (
    <article className="discover-card" aria-label={`${job.title} at ${job.company_name}`}>
      <header className="discover-card__header">
        <div>
          <h2 className="heading-2">{job.title}</h2>
          <p className="discover-card__company">{job.company_name}</p>
        </div>
        <p className="note">Posted {posted}</p>
      </header>
      <p className="discover-card__location">{job.location ?? 'Location not provided'}</p>
      <ul className="discover-card__badges" aria-label="Job details">
        {job.job_type && <li>{job.job_type.replace('_', ' ')}</li>}
        {job.work_arrangement && <li>{job.work_arrangement}</li>}
      </ul>
      {match.coverage === null ? (
        <p className="discover-card__coverage-note">No skill requirements were extracted for this job.</p>
      ) : (
        <div className="discover-card__coverage">
          <div className="discover-card__coverage-label">
            <span>You have {match.required_matched} of {match.required_total} required skills</span>
            <span>{coveragePercent}%</span>
          </div>
          <div className="discover-card__track" role="progressbar" aria-label="Required skill coverage" aria-valuemin={0} aria-valuemax={100} aria-valuenow={coveragePercent}>
            <span style={{ width: `${coveragePercent}%` }} />
          </div>
        </div>
      )}
      <div className="discover-card__skills">
        <div>
          <h3 className="heading-3">Matched skills</h3>
          {match.matched_skills.length ? <ul aria-label="Matched skills">{[...match.matched_skills].sort((a, b) => Number(a.requirement_type !== 'REQUIRED') - Number(b.requirement_type !== 'REQUIRED') || a.name.localeCompare(b.name)).map(skill => <li key={skill.skill_id}>{skill.name}</li>)}</ul> : <p className="note">No matched skills</p>}
        </div>
        <div>
          <h3 className="heading-3">Missing skills</h3>
          {match.missing_skills.length ? <ul aria-label="Missing skills">{[...match.missing_skills].sort((a, b) => Number(a.requirement_type !== 'REQUIRED') - Number(b.requirement_type !== 'REQUIRED') || a.name.localeCompare(b.name)).map(skill => <li key={skill.skill_id}>{skill.name}{skill.requirement_type === 'REQUIRED' ? ' · Required' : ' · Preferred'}</li>)}</ul> : <p className="note">No missing skills</p>}
        </div>
      </div>
      <div className="discover-card__actions">
        <button className="button button--quiet" type="button" disabled={pending} onClick={() => onDecision(job.job_id, 'NOT_INTERESTED')} aria-label="Not interested">← Not interested</button>
        <div className="actions">
          <a className="button button--quiet" href={job.application_url} target="_blank" rel="noopener noreferrer">Open posting</a>
          <button className="button button--primary" type="button" disabled={pending} onClick={() => onDecision(job.job_id, 'SAVED')} aria-label="Save">Save →</button>
        </div>
      </div>
      {entry.failedDecision && <p className="discover-card__retry" role="alert"><button type="button" className="button button--quiet" onClick={() => onRetry(entry)}>Not saved — retry</button></p>}
    </article>
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
  const requestId = useRef(0)
  const loadedCount = useRef(0)
  const decidedCount = useRef(0)
  const seenIds = useRef(new Set<string>())
  const loadingPage = useRef(false)
  const pageRequestId = useRef(0)
  const entriesRef = useRef(entries)
  entriesRef.current = entries

  useEffect(() => setDraft(committed), [queryString]) // submitted URL is the source of truth

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
      if (isProfileMissing(error)) await onProfileMissing?.()
      setLoadError(messageFor(error))
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [client, committed])

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
        if (isProfileMissing(error)) await onProfileMissing?.()
        setNextError(messageFor(error))
      }
    } finally {
      if (pageId === pageRequestId.current) {
        loadingPage.current = false
        if (id === requestId.current) setLoadingNext(false)
      }
    }
  }, [client, committed, hasMore, loading, onProfileMissing, pendingIds])

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
    setEntries(rows => rows.filter(row => row.item.job.job_id !== id))
    try {
      await client.decide(id, status)
      if (generation === requestId.current) decidedCount.current += 1
    } catch (error) {
      if (generation !== requestId.current) return
      if (isProfileMissing(error)) await onProfileMissing?.()
      setEntries(rows => {
        if (rows.some(row => row.item.job.job_id === id)) return rows
        const restored = [...rows]
        restored.splice(Math.min(index, restored.length), 0, { item: entry.item, failedDecision: status })
        return restored
      })
    } finally {
      if (generation === requestId.current) setPendingIds(ids => { const next = new Set(ids); next.delete(id); return next })
    }
  }, [client, onProfileMissing])

  const submitFilters = (event: FormEvent) => {
    event.preventDefault()
    const params = new URLSearchParams()
    Object.entries(draft).forEach(([key, value]) => { if (value?.trim()) params.set(key, value.trim()) })
    setSearchParams(params)
  }

  const onKeyDown = useCallback((event: globalThis.KeyboardEvent) => {
    const target = event.target as HTMLElement
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.repeat || target.isContentEditable || target.closest('input, textarea, select')) return
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    const first = entriesRef.current[0]
    if (!first) return
    event.preventDefault()
    void decide(first.item.job.job_id, event.key === 'ArrowLeft' ? 'NOT_INTERESTED' : 'SAVED')
  }, [decide])

  useEffect(() => {
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onKeyDown])

  const changeFilters = () => {
    // Opening the filter controls must not change the submitted URL or fetch new results.
    document.getElementById('discover-job-type')?.focus()
  }

  const checkAgain = () => { void loadFirst() }

  return (
    <div className="discover" role="region" aria-label="Discover jobs">
      <header className="discover__intro">
        <p className="eyebrow">Job listings</p>
        <h1 className="heading-1">Discover</h1>
        <p className="lede">Explore postings by skill coverage, based on the skills you have confirmed.</p>
      </header>
      <form className="discover-filters" onSubmit={submitFilters}>
        <label className="field"><span className="field__label">Job type</span>
          <select id="discover-job-type" className="field__input" aria-label="Job type" value={draft.job_type ?? ''} onChange={event => setDraft(value => ({ ...value, job_type: (event.target.value || undefined) as JobType | undefined }))}>
            <option value="">Any type</option>{JOB_TYPES.map(value => <option key={value} value={value}>{value.replace('_', ' ')}</option>)}
          </select>
        </label>
        <label className="field"><span className="field__label">Work arrangement</span>
          <select className="field__input" aria-label="Work arrangement" value={draft.work_arrangement ?? ''} onChange={event => setDraft(value => ({ ...value, work_arrangement: (event.target.value || undefined) as WorkArrangement | undefined }))}>
            <option value="">Any arrangement</option>{WORK_ARRANGEMENTS.map(value => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label className="field"><span className="field__label">Location</span>
          <input className="field__input" aria-label="Location" value={draft.location ?? ''} onChange={event => setDraft(value => ({ ...value, location: event.target.value || undefined }))} />
        </label>
        <label className="field"><span className="field__label">Keyword</span>
          <input className="field__input" aria-label="Keyword" value={draft.q ?? ''} onChange={event => setDraft(value => ({ ...value, q: event.target.value || undefined }))} />
        </label>
        <button className="button button--primary" type="submit">Apply filters</button>
      </form>
      {loading && <p role="status" className="note">Loading jobs…</p>}
      {!loading && loadError && <div className="discover__error" role="alert"><p>{loadError}</p><button className="button" type="button" onClick={checkAgain}>Try again</button></div>}
      {!loading && !loadError && entries.length === 0 && !hasMore && !loadingNext && (
        <section className="discover__empty" aria-live="polite"><h2 className="heading-2">No more jobs for these filters</h2><div className="actions"><button className="button button--quiet" type="button" onClick={changeFilters}>Change filters</button><button className="button button--primary" type="button" onClick={checkAgain}>Check again</button></div></section>
      )}
      {!loadError && entries.length > 0 && <div className="discover__cards">{entries.map(entry => (
        <JobCard key={entry.item.job.job_id} entry={entry} pending={pendingIds.has(entry.item.job.job_id)} onDecision={(id, status) => void decide(id, status)} onRetry={retry => void decide(retry.item.job.job_id, retry.failedDecision ?? 'SAVED')} />
      ))}</div>}
      {loadingNext && <p className="note" role="status">Loading more jobs…</p>}
      {nextError && <div className="discover__error" role="alert"><p>{nextError}</p><button className="button" type="button" onClick={() => void loadNext()}>Try loading more</button></div>}
    </div>
  )
}

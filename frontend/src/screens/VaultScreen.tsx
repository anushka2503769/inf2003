import { useCallback, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

import { toDisplayMessage } from '../lib/api-client'
import { trackerClient } from '../features/tracker/defaultClient'
import type { TrackerClient } from '../features/tracker/client'
import { TRACKER_STATUSES } from '../features/tracker/types'
import type { TrackerItem, TrackerStatus, TrackerSummary } from '../features/tracker/types'
import '../features/tracker/vault-screen.css'

const PAGE_SIZE = 20

const STATUS_LABELS: Record<TrackerStatus, string> = {
  NOT_INTERESTED: 'Not interested',
  SAVED: 'Saved',
  APPLIED: 'Applied',
  INTERVIEW: 'Interview',
  REJECTED: 'Rejected',
  OFFER: 'Offer',
}

function formatUpdated(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return new Intl.DateTimeFormat('en-SG', { day: 'numeric', month: 'short', year: 'numeric' }).format(date)
}

function postingUrl(value: string): string | null {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}

interface VaultScreenProps {
  client?: TrackerClient
}

export function VaultScreen({ client = trackerClient }: VaultScreenProps) {
  const [status, setStatus] = useState<TrackerStatus>('SAVED')
  const [page, setPage] = useState(0)
  const [summary, setSummary] = useState<TrackerSummary | null>(null)
  const [rows, setRows] = useState<TrackerItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [actionError, setActionError] = useState('')
  const [refreshError, setRefreshError] = useState('')
  const [pendingJobId, setPendingJobId] = useState<string | null>(null)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const listRequest = useRef(0)
  const summaryRequest = useRef(0)
  const cancelButton = useRef<HTMLButtonElement | null>(null)
  const removeButtons = useRef(new Map<string, HTMLButtonElement>())
  const lastConfirmation = useRef<string | null>(null)
  const tabButtons = useRef<Partial<Record<TrackerStatus, HTMLButtonElement | null>>>({})

  const loadList = useCallback(async (afterWrite = false): Promise<boolean> => {
    const requestId = ++listRequest.current
    setLoading(true)
    setListError('')
    try {
      const result = await client.list(status, PAGE_SIZE, page * PAGE_SIZE)
      if (requestId !== listRequest.current) return true
      setRows(result.items)
      setTotal(result.total)
      return true
    } catch (cause) {
      if (requestId !== listRequest.current) return true
      setRows([])
      setTotal(0)
      if (!afterWrite) setListError(toDisplayMessage(cause))
      return false
    } finally {
      if (requestId === listRequest.current) setLoading(false)
    }
  }, [client, page, status])

  const loadSummary = useCallback(async (): Promise<boolean> => {
    const requestId = ++summaryRequest.current
    try {
      const result = await client.summary()
      if (requestId === summaryRequest.current) setSummary(result)
      return true
    } catch (cause) {
      if (requestId === summaryRequest.current) setRefreshError(toDisplayMessage(cause))
      return false
    }
  }, [client])

  useEffect(() => {
    void loadList()
    return () => { listRequest.current += 1 }
  }, [loadList])

  useEffect(() => {
    void loadSummary()
    return () => { summaryRequest.current += 1 }
  }, [loadSummary])

  useEffect(() => {
    if (confirmingId) cancelButton.current?.focus()
    else if (lastConfirmation.current) removeButtons.current.get(lastConfirmation.current)?.focus()
    lastConfirmation.current = confirmingId
  }, [confirmingId])

  function adjustCount(from: TrackerStatus, to?: TrackerStatus) {
    setSummary(previous => {
      if (!previous) return previous
      const counts = { ...previous.counts, [from]: Math.max(0, previous.counts[from] - 1) }
      if (to) counts[to] += 1
      return { ...previous, counts }
    })
  }

  async function changeStatus(row: TrackerItem, nextStatus: TrackerStatus) {
    if (row.status === nextStatus || pendingJobId !== null) return
    setPendingJobId(row.job.job_id)
    setActionError('')
    setRefreshError('')
    const previousStatus = row.status
    setRows(current => current.map(item => item.job.job_id === row.job.job_id ? { ...item, status: nextStatus } : item))
    setTotal(current => Math.max(0, current - 1))
    adjustCount(previousStatus, nextStatus)
    try {
      const saved = await client.update(row.job.job_id, nextStatus)
      setRows(current => current.flatMap(item => item.job.job_id !== row.job.job_id
        ? [item]
        : status === saved.status ? [saved] : []))
      const lastItemOnPage = page > 0 && total - 1 <= page * PAGE_SIZE
      if (lastItemOnPage) setPage(current => current - 1)
      const refreshed = await Promise.all([
        loadSummary(),
        lastItemOnPage ? Promise.resolve(true) : loadList(true),
      ])
      if (refreshed.some(ok => !ok)) {
        setRefreshError('Status saved, but the view could not be refreshed. Reload to see the latest data.')
      }
    } catch (cause) {
      setRows(current => current.map(item => item.job.job_id === row.job.job_id ? row : item))
      setTotal(current => current + 1)
      adjustCount(nextStatus, previousStatus)
      setActionError(toDisplayMessage(cause))
    } finally {
      setPendingJobId(null)
    }
  }

  async function removeRow(row: TrackerItem) {
    if (pendingJobId !== null) return
    setPendingJobId(row.job.job_id)
    setActionError('')
    setRefreshError('')
    try {
      await client.remove(row.job.job_id)
      setRows(current => current.filter(item => item.job.job_id !== row.job.job_id))
      setTotal(current => Math.max(0, current - 1))
      adjustCount(row.status)
      setConfirmingId(null)
      const lastItemOnPage = page > 0 && total - 1 <= page * PAGE_SIZE
      if (lastItemOnPage) setPage(current => current - 1)
      else {
        const refreshed = await Promise.all([loadSummary(), loadList(true)])
        if (refreshed.some(ok => !ok)) {
          setRefreshError('Job removed, but the view could not be refreshed. Reload to see the latest data.')
        }
      }
    } catch (cause) {
      setActionError(toDisplayMessage(cause))
    } finally {
      setPendingJobId(null)
    }
  }

  function onTabsKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const current = TRACKER_STATUSES.indexOf(status)
    const delta = event.key === 'ArrowRight' ? 1 : -1
    const next = TRACKER_STATUSES[(current + delta + TRACKER_STATUSES.length) % TRACKER_STATUSES.length]
    setStatus(next)
    setPage(0)
    setActionError('')
    tabButtons.current[next]?.focus()
  }

  const visibleRows = rows.filter(row => row.status === status)
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const activeTabId = `vault-tab-${status.toLowerCase()}`

  return (
    <section className="vault stack" aria-labelledby="vault-title">
      <header className="vault__header">
        <div>
          <p className="step-count">YOUR TRACKER</p>
          <h1 id="vault-title" className="heading-1">Vault</h1>
        </div>
        <p className="note">Track each decision and what happens after you apply.</p>
      </header>

      <div className="vault__tabs" role="tablist" aria-label="Tracker status" onKeyDown={onTabsKeyDown}>
        {TRACKER_STATUSES.map(tabStatus => {
          const tabId = `vault-tab-${tabStatus.toLowerCase()}`
          return (
            <button
              aria-controls="vault-panel"
              aria-selected={status === tabStatus}
              className={status === tabStatus ? 'vault__tab vault__tab--active' : 'vault__tab'}
              disabled={pendingJobId !== null}
              id={tabId}
              key={tabStatus}
              onClick={() => { setStatus(tabStatus); setPage(0); setActionError('') }}
              ref={element => { tabButtons.current[tabStatus] = element }}
              role="tab"
              tabIndex={status === tabStatus ? 0 : -1}
              type="button"
            >
              {STATUS_LABELS[tabStatus]} <span>{summary?.counts[tabStatus] ?? 0}</span>
            </button>
          )
        })}
      </div>

      {actionError && <p className="vault__error" role="alert">{actionError}</p>}
      {refreshError && <p className="vault__notice" role="status">{refreshError}</p>}
      {listError && <p className="vault__error" role="alert">{listError}</p>}

      <div id="vault-panel" role="tabpanel" aria-labelledby={activeTabId} tabIndex={0}>
        {loading ? (
          <p className="note" role="status">Loading {STATUS_LABELS[status].toLowerCase()} jobs…</p>
        ) : listError ? null : visibleRows.length === 0 ? (
          <div className="vault__empty">
            <h2 className="heading-2">No jobs in {STATUS_LABELS[status]} yet.</h2>
            <p className="prose">Jobs you track with this status will show up here.</p>
          </div>
        ) : (
          <ul className="vault__list" aria-label={`${STATUS_LABELS[status]} jobs`}>
            {visibleRows.map(row => {
              const href = postingUrl(row.job.application_url)
              return (
                <li className="vault__row" key={row.job.job_id}>
                  <div className="vault__details">
                    <h2 className="heading-3">{row.job.title}</h2>
                    <p>{row.job.company_name}{row.job.location ? ` · ${row.job.location}` : ''}</p>
                    {!row.job.is_active && <span className="vault__inactive">No longer listed</span>}
                    <p className="note">Updated <time dateTime={row.updated_at}>{formatUpdated(row.updated_at)}</time></p>
                  </div>
                  <div className="vault__actions">
                    <label className="vault__status-label">
                      Status
                      <select
                        aria-label={`Status for ${row.job.title}`}
                        disabled={pendingJobId !== null}
                        onChange={event => void changeStatus(row, event.currentTarget.value as TrackerStatus)}
                        value={row.status}
                      >
                        {TRACKER_STATUSES.map(option => <option key={option} value={option}>{STATUS_LABELS[option]}</option>)}
                      </select>
                    </label>
                    {href && <a href={href} rel="noopener noreferrer" target="_blank">Open posting</a>}
                    {confirmingId === row.job.job_id ? (
                      <div className="vault__confirm" role="group" aria-label={`Confirm removal of ${row.job.title}`} onKeyDown={event => {
                        if (event.key === 'Escape') setConfirmingId(null)
                      }}>
                        <span>Remove this job from your vault?</span>
                        <button className="button button--quiet" disabled={pendingJobId !== null} onClick={() => setConfirmingId(null)} ref={cancelButton} type="button">Cancel</button>
                        <button className="button button--quiet" disabled={pendingJobId !== null} onClick={() => void removeRow(row)} type="button">Remove</button>
                      </div>
                    ) : (
                      <button
                        className="button button--quiet"
                        disabled={pendingJobId !== null}
                        onClick={() => setConfirmingId(row.job.job_id)}
                        ref={element => { if (element) removeButtons.current.set(row.job.job_id, element); else removeButtons.current.delete(row.job.job_id) }}
                        type="button"
                      >Remove</button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}

        {total > PAGE_SIZE && (
          <nav className="vault__pagination" aria-label="Tracker pages">
            <button className="button button--quiet" disabled={page === 0 || loading || pendingJobId !== null} onClick={() => setPage(current => current - 1)} type="button">Previous page</button>
            <span className="note">Page {page + 1} of {pageCount}</span>
            <button className="button button--quiet" disabled={page + 1 >= pageCount || loading || pendingJobId !== null} onClick={() => setPage(current => current + 1)} type="button">Next page</button>
          </nav>
        )}
      </div>
    </section>
  )
}

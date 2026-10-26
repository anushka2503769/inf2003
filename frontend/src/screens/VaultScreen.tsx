import { useCallback, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

import { Badge } from '../components/Badge'
import { Button, buttonClass } from '../components/Button'
import { EmptyState, InlineError, Notice, Spinner } from '../components/Feedback'
import { Icon } from '../components/Icon'
import { Select } from '../components/Select'
import { toDisplayMessage } from '../lib/api-client'
import { trackerClient } from '../features/tracker/defaultClient'
import type { TrackerClient } from '../features/tracker/client'
import type { TrackerItem, TrackerStatus, TrackerSummary } from '../features/tracker/types'
import { useIsMobile } from '../features/tracker/useIsMobile'
import '../features/tracker/vault-screen.css'

const PAGE_SIZE = 20

/** Display order: the application pipeline first, "Not interested" last. */
const STATUS_ORDER: readonly TrackerStatus[] = ['SAVED', 'APPLIED', 'INTERVIEW', 'OFFER', 'REJECTED', 'NOT_INTERESTED']

const STATUS_LABELS: Record<TrackerStatus, string> = {
  NOT_INTERESTED: 'Not interested',
  SAVED: 'Saved',
  APPLIED: 'Applied',
  INTERVIEW: 'Interview',
  REJECTED: 'Rejected',
  OFFER: 'Offer',
}

const EMPTY_BODY: Record<TrackerStatus, string> = {
  SAVED: 'Postings you save in Discover land here.',
  APPLIED: 'When you apply to a saved posting, move it here.',
  INTERVIEW: 'Move a posting here once an interview is booked.',
  OFFER: 'When one lands, move it here from Interview. On the bright side, there is nothing to decline either.',
  REJECTED: 'Postings that said no end up here. None so far.',
  NOT_INTERESTED: 'Postings you pass on in Discover land here.',
}

interface ActionError {
  /** What failed, in bold ("Couldn't move ..."). */
  headline?: string
  /** The display message from the API error. */
  message: string
  /** Row to tint while the error is shown. */
  jobId?: string
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
  const [actionError, setActionError] = useState<ActionError | null>(null)
  const [refreshError, setRefreshError] = useState('')
  const [pendingJobId, setPendingJobId] = useState<string | null>(null)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const listRequest = useRef(0)
  const summaryRequest = useRef(0)
  const cancelButton = useRef<HTMLButtonElement | null>(null)
  const removeButtons = useRef(new Map<string, HTMLButtonElement>())
  const lastConfirmation = useRef<string | null>(null)
  const tabButtons = useRef<Partial<Record<TrackerStatus, HTMLButtonElement | null>>>({})
  const mobile = useIsMobile()

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
    setActionError(null)
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
      setActionError({
        headline: `Couldn't move “${row.job.title}” to ${STATUS_LABELS[nextStatus]}. It is back in ${STATUS_LABELS[previousStatus]}.`,
        message: toDisplayMessage(cause),
        jobId: row.job.job_id,
      })
    } finally {
      setPendingJobId(null)
    }
  }

  async function removeRow(row: TrackerItem) {
    if (pendingJobId !== null) return
    setPendingJobId(row.job.job_id)
    setActionError(null)
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
      setActionError({ headline: `Couldn't remove “${row.job.title}”.`, message: toDisplayMessage(cause) })
    } finally {
      setPendingJobId(null)
    }
  }


  function selectStatus(next: TrackerStatus) {
    setStatus(next)
    setPage(0)
    setActionError(null)
  }

  function onTabsKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const current = STATUS_ORDER.indexOf(status)
    const delta = event.key === 'ArrowRight' ? 1 : -1
    const next = STATUS_ORDER[(current + delta + STATUS_ORDER.length) % STATUS_ORDER.length]
    selectStatus(next)
    tabButtons.current[next]?.focus()
  }

  const visibleRows = rows.filter(row => row.status === status)
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const activeTabId = `vault-tab-${status.toLowerCase()}`
  const rangeStart = total === 0 ? 0 : page * PAGE_SIZE + 1
  const rangeEnd = Math.min(total, (page + 1) * PAGE_SIZE)
  const statusLabel = STATUS_LABELS[status]

  return (
    <section className="vault" aria-labelledby="vault-title">
      <header className="vault__head">
        <h1 id="vault-title" className="t-title vault__title-page">Vault</h1>
        <p className="t-body muted vault__lede">Every posting you decided on, sorted by most recently updated.</p>
      </header>

      {/* Mobile: one labelled dropdown replaces the six tabs. Exactly one of the two is exposed. */}
      <div className="vault__show" hidden={!mobile}>
        <Select
          label="Show"
          value={status}
          onChange={value => selectStatus(value as TrackerStatus)}
          options={STATUS_ORDER.map(option => ({
            value: option,
            label: `${STATUS_LABELS[option]} (${summary?.counts[option] ?? 0})`,
          }))}
          size="lg"
          disabled={pendingJobId !== null}
        />
      </div>

      <div className="tabs vault__tabs" role="tablist" aria-label="Tracker status" onKeyDown={onTabsKeyDown} hidden={mobile}>
        {STATUS_ORDER.map(tabStatus => {
          const tabId = `vault-tab-${tabStatus.toLowerCase()}`
          return (
            <button
              aria-controls="vault-panel"
              aria-selected={status === tabStatus}
              className="tab"
              disabled={pendingJobId !== null}
              id={tabId}
              key={tabStatus}
              onClick={() => selectStatus(tabStatus)}
              ref={element => { tabButtons.current[tabStatus] = element }}
              role="tab"
              tabIndex={status === tabStatus ? 0 : -1}
              type="button"
            >
              {STATUS_LABELS[tabStatus]} <span className="tab__count">{summary?.counts[tabStatus] ?? 0}</span>
            </button>
          )
        })}
      </div>

      {actionError && (
        <InlineError>
          {actionError.headline ? <><strong>{actionError.headline}</strong>{' '}</> : null}
          <span>{actionError.message}</span>
        </InlineError>
      )}
      {refreshError && <div role="status"><Notice tone="info">{refreshError}</Notice></div>}
      {listError && <InlineError><span>{listError}</span></InlineError>}

      <div
        className="vault__panel"
        id="vault-panel"
        {...(mobile
          ? { role: 'region', 'aria-label': `${statusLabel} jobs` }
          : { role: 'tabpanel', 'aria-labelledby': activeTabId, tabIndex: 0 })}
      >
        {loading ? (
          <>
            <div className="vault__table" aria-hidden="true">
              <VaultTableHead />
              {Array.from({ length: 6 }, (_, index) => (
                <div className="row vault__row vault__row--skeleton" key={index}>
                  <div className="vault__posting">
                    <span className="skel vault__skel-title" style={{ width: `${40 + ((index * 7) % 30)}%` }} />
                    <span className="skel vault__skel-sub" />
                  </div>
                  <span className="skel vault__skel-select" />
                  <span className="skel vault__skel-date" />
                  <span className="skel vault__skel-actions" />
                </div>
              ))}
            </div>
            <p className="toast-line t-meta vault__loading" role="status">
              <Spinner size="sm" />
              Loading {statusLabel.toLowerCase()} jobs…
            </p>
          </>
        ) : listError ? null : visibleRows.length === 0 ? (
          <EmptyState icon="tray" title={`No jobs in ${statusLabel} yet.`}>
            {EMPTY_BODY[status]}
          </EmptyState>
        ) : (
          <div className="vault__table">
            <VaultTableHead />
            <ul className="vault__list" aria-label={`${statusLabel} jobs`}>
              {visibleRows.map(row => {
                const href = postingUrl(row.job.application_url)
                const confirming = confirmingId === row.job.job_id
                const failed = actionError?.jobId === row.job.job_id
                const classes = [
                  'row',
                  'vault__row',
                  confirming ? 'row--confirm vault__row--confirm' : '',
                  failed ? 'vault__row--failed' : '',
                  row.job.is_active ? '' : 'vault__row--inactive',
                ].filter(Boolean).join(' ')
                const subline = `${row.job.company_name}${row.job.location ? ` · ${row.job.location}` : ''}`

                if (confirming) {
                  return (
                    <li className={classes} key={row.job.job_id}>
                      <div
                        className="vault__confirm"
                        role="group"
                        aria-label={`Confirm removal of ${row.job.title}`}
                        onKeyDown={event => { if (event.key === 'Escape') setConfirmingId(null) }}
                      >
                        <div className="vault__confirm-text">
                          <div className="vault__confirm-title">
                            Remove “<h2 className="vault__title vault__title--inline">{row.job.title}</h2>” from your vault?
                          </div>
                          <p className="row__sub">It can show up in Discover again. Your status ({STATUS_LABELS[row.status]}) is not kept.</p>
                        </div>
                        <div className="row__actions vault__confirm-actions">
                          <button className={buttonClass({ variant: 'ghost' })} disabled={pendingJobId !== null} onClick={() => setConfirmingId(null)} ref={cancelButton} type="button">Cancel</button>
                          <Button variant="danger" icon="trash" disabled={pendingJobId !== null} onClick={() => void removeRow(row)}>Remove</Button>
                        </div>
                      </div>
                    </li>
                  )
                }

                return (
                  <li className={classes} key={row.job.job_id}>
                    <div className="vault__posting">
                      <div className="row__title">
                        <h2 className="vault__title">{row.job.title}</h2>
                        {!row.job.is_active && <Badge tone="danger">No longer listed</Badge>}
                      </div>
                      <p className="row__sub">{subline}</p>
                    </div>
                    <div className="vault__status">
                      <select
                        aria-label={`Status for ${row.job.title}`}
                        className="field__input vault__select"
                        disabled={pendingJobId !== null}
                        onChange={event => void changeStatus(row, event.currentTarget.value as TrackerStatus)}
                        value={row.status}
                      >
                        {STATUS_ORDER.map(option => <option key={option} value={option}>{STATUS_LABELS[option]}</option>)}
                      </select>
                    </div>
                    <p className="t-meta vault__updated">
                      <span className="vault__updated-label">Updated </span>
                      <time dateTime={row.updated_at}>{formatUpdated(row.updated_at)}</time>
                    </p>
                    <div className="row__actions vault__actions">
                      {href ? (
                        <a className="link vault__open" href={href} rel="noopener noreferrer" target="_blank">
                          <span className="vault__open-text">Open posting</span>
                          <Icon name="arrow-square-out" />
                        </a>
                      ) : !row.job.is_active ? (
                        <span className="t-meta vault__closed">Posting closed</span>
                      ) : null}
                      <button
                        aria-label="Remove"
                        className={buttonClass({ variant: 'ghost', iconOnly: true }, 'vault__remove')}
                        disabled={pendingJobId !== null}
                        onClick={() => setConfirmingId(row.job.job_id)}
                        ref={element => { if (element) removeButtons.current.set(row.job.job_id, element); else removeButtons.current.delete(row.job.job_id) }}
                        title={`Remove ${row.job.title}`}
                        type="button"
                      >
                        <Icon name="trash" />
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        )}

        {total > PAGE_SIZE && (
          <nav className="vault__pager" aria-label="Tracker pages">
            <span className="t-meta mono">
              <span className="vault__range-word">Showing </span>{rangeStart}–{rangeEnd} of {total}
            </span>
            <span className="sr-only">Page {page + 1} of {pageCount}</span>
            <div className="vault__pager-buttons">
              <Button aria-label="Previous page" disabled={page === 0 || loading || pendingJobId !== null} icon="caret-left" onClick={() => setPage(current => current - 1)} variant="secondary">Previous</Button>
              <Button aria-label="Next page" disabled={page + 1 >= pageCount || loading || pendingJobId !== null} iconRight="caret-right" onClick={() => setPage(current => current + 1)} variant="secondary">Next</Button>
            </div>
          </nav>
        )}
      </div>
    </section>
  )
}

/** Column labels for the desktop table; the rows carry their own names for screen readers. */
function VaultTableHead() {
  return (
    <div className="vault__table-head" aria-hidden="true">
      <span className="t-label">Posting</span>
      <span className="t-label">Status</span>
      <span className="t-label">Updated</span>
      <span className="t-label vault__table-head-actions">Actions</span>
    </div>
  )
}

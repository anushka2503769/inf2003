import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { InlineError, Spinner } from '../../components/Feedback'
import { Icon } from '../../components/Icon'
import { TextField } from '../../components/TextField'
import type { Skill } from '../../types/api'
import { isSkillsClientError, mockSkillsClient, type SkillsClient } from './client'
import './skill-editor.css'
import type { SkillEditorProps, SkillOperation, SkillRowState } from './types'

const SEARCH_DEBOUNCE_MS = 300
const SEARCH_LIMIT = 20

type SearchStatus = 'idle' | 'loading' | 'ready' | 'error'

/**
 * Confirmed-skill editor (ANU-01/02).
 *
 * Owns nothing about *where* `confirmedSkills` comes from or how
 * `onProfileReload` is implemented — see features/skills/types.ts for that
 * boundary. Accepts an optional `client` so ANU-02 can inject a real
 * authenticated adapter without touching this file; defaults to the local
 * mock so the component renders and behaves correctly on its own.
 */
export function SkillEditor({
  confirmedSkills,
  onProfileReload,
  className,
  client = mockSkillsClient,
}: SkillEditorProps & { client?: SkillsClient }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Skill[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [searchStatus, setSearchStatus] = useState<SearchStatus>('idle')
  const [searchError, setSearchError] = useState<string | null>(null)
  const [rowState, setRowState] = useState<Record<number, SkillRowState>>({})

  // Guards against stale search responses: only the response matching the
  // most recently issued request is ever applied to state.
  const latestRequestId = useRef(0)
  const isFirstRun = useRef(true)
  // Synchronous lock for in-flight per-skill operations. React state is
  // async and re-render-gated, so it cannot reliably block a second call
  // issued in the same tick (e.g. a fast double click) before the first
  // setRowState has committed — a ref can.
  const inFlightSkillIds = useRef<Set<number>>(new Set())

  const confirmedIds = useMemo(
    () => new Set(confirmedSkills.map(skill => skill.skill_id)),
    [confirmedSkills],
  )

  const runSearch = useCallback(
    (rawQuery: string) => {
      const requestId = ++latestRequestId.current
      setSearchStatus('loading')
      setSearchError(null)

      client
        .search(rawQuery, SEARCH_LIMIT)
        .then(response => {
          if (requestId !== latestRequestId.current) return // superseded by a newer search
          setResults(response.items)
          setHasMore(response.has_more)
          setSearchStatus('ready')
        })
        .catch((cause: unknown) => {
          if (requestId !== latestRequestId.current) return
          setSearchStatus('error')
          setSearchError(
            isSkillsClientError(cause) ? cause.message : 'Search failed. Try again.',
          )
        })
    },
    [client],
  )

  useEffect(() => {
    if (isFirstRun.current) {
      isFirstRun.current = false
      runSearch(query) // contract: empty q lists the first skills alphabetically
      return
    }
    const handle = setTimeout(() => runSearch(query), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(handle)
  }, [query, runSearch])

  const setRow = useCallback((skillId: number, state: SkillRowState) => {
    setRowState(previous => ({ ...previous, [skillId]: state }))
  }, [])

  const clearRow = useCallback((skillId: number) => {
    setRowState(previous => {
      if (!(skillId in previous)) return previous
      const next = { ...previous }
      delete next[skillId]
      return next
    })
  }, [])

  const runOperation = useCallback(
    async (skillId: number, operation: SkillOperation) => {
      // Serialize: a skill already mid-operation ignores a second trigger
      // rather than racing two requests for the same skill_id. Checked and
      // set synchronously on the ref so two calls in the same tick can't
      // both pass the check before either sets the lock.
      if (inFlightSkillIds.current.has(skillId)) return
      inFlightSkillIds.current.add(skillId)
      setRow(skillId, { status: 'pending' })

      try {
        try {
          if (operation === 'add') {
            await client.add(skillId)
          } else {
            await client.remove(skillId)
          }
        } catch (cause) {
          setRow(skillId, {
            status: 'error',
            errorMessage: isSkillsClientError(cause)
              ? cause.message
              : 'That did not save. Try again.',
          })
          return
        }

        try {
          await onProfileReload()
          clearRow(skillId)
        } catch {
          // The write itself succeeded server-side — only the refresh failed.
          // Never tell the student the add/remove was lost when it wasn't.
          setRow(skillId, {
            status: 'error',
            errorMessage: 'Saved, but your skill list could not be refreshed. Reload the page.',
          })
        }
      } finally {
        inFlightSkillIds.current.delete(skillId)
      }
    },
    [client, onProfileReload, setRow, clearRow],
  )

  const trimmedQuery = query.trim()

  return (
    <section className={className ? `skill-editor ${className}` : 'skill-editor'}>
      <div className="skill-editor__head">
        <h2 className="skill-editor__title">
          Skills <span className="skill-editor__count">{confirmedSkills.length}</span>
        </h2>
        <p className="skill-editor__lede">Add what you can genuinely talk about in an interview.</p>
      </div>

      {confirmedSkills.length === 0 ? (
        <p className="note">You haven't confirmed any skills yet. Search below to add some.</p>
      ) : (
        <ul className="skill-editor__chips" aria-label="Your confirmed skills">
          {confirmedSkills.map(skill => {
            const state = rowState[skill.skill_id]
            const nameId = `skill-editor-confirmed-${skill.skill_id}`
            const pending = state?.status === 'pending'
            return (
              <li key={skill.skill_id} className="skill-editor__chip-item">
                <span className="chip">
                  <span id={nameId}>{skill.name}</span>
                  <button
                    type="button"
                    className="chip__x"
                    aria-label={pending ? 'Removing…' : 'Remove'}
                    aria-describedby={nameId}
                    disabled={pending}
                    onClick={() => void runOperation(skill.skill_id, 'remove')}
                  >
                    {pending ? <Spinner size="sm" /> : <Icon name="x" />}
                  </button>
                </span>
                {state?.status === 'error' ? (
                  <span className="skill-editor__row-error">
                    <InlineError>{state.errorMessage}</InlineError>
                  </span>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}

      <div className="skill-editor__search">
        <TextField
          label="Search the skill dictionary"
          value={query}
          onChange={setQuery}
          placeholder="Search skills to add, e.g. Tableau"
          icon="magnifying-glass"
        />

        {searchStatus === 'loading' ? (
          <p className="toast-line t-meta" role="status">
            <Spinner size="sm" />
            Searching…
          </p>
        ) : null}

        {searchStatus === 'error' ? <InlineError>{searchError}</InlineError> : null}

        {searchStatus === 'ready' && results.length === 0 ? (
          <p className="note">
            {trimmedQuery === ''
              ? 'No skills are in the dictionary yet.'
              : `No skills match "${trimmedQuery}". Try a different search.`}
          </p>
        ) : null}

        {searchStatus === 'ready' && results.length > 0 ? (
          <ul className="skill-editor__results" aria-label="Skill search results">
            {results.map(skill => {
              const state = rowState[skill.skill_id]
              const isConfirmed = confirmedIds.has(skill.skill_id)
              return (
                <li key={skill.skill_id} className="skill-editor__result">
                  <span className="skill-editor__name">{skill.name}</span>
                  {isConfirmed ? (
                    <Badge tone="accent" icon="check">
                      Added
                    </Badge>
                  ) : (
                    <Button
                      variant="ghost"
                      icon="plus"
                      busy={state?.status === 'pending'}
                      onClick={() => void runOperation(skill.skill_id, 'add')}
                    >
                      {state?.status === 'pending' ? 'Adding…' : 'Add'}
                    </Button>
                  )}
                  {state?.status === 'error' ? (
                    <span className="skill-editor__row-error">
                      <InlineError>{state.errorMessage}</InlineError>
                    </span>
                  ) : null}
                </li>
              )
            })}
          </ul>
        ) : null}

        {hasMore ? (
          <p className="note">More matches than shown. Narrow your search to see all results.</p>
        ) : null}
      </div>
    </section>
  )
}

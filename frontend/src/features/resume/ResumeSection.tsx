import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react'

import { Badge } from '../../components/Badge'
import { Button } from '../../components/Button'
import { InlineError, Spinner } from '../../components/Feedback'
import { Icon } from '../../components/Icon'
import type { UserSkill } from '../../types/api'
import type { SkillsClient } from '../skills/client'
import { SkillEditor } from '../skills/SkillEditor'
import type { AsyncProfileReload } from '../skills/types'
import { profileSkillsClient, resumeClient, type ResumeClient } from './client'
import './resume.css'
import { isResumeClientError, type ResumeResponse } from './types'
import { RESUME_ACCEPT, validateResumeFile } from './validation'

type RowStatus = 'idle' | 'saving' | 'failed'

export interface ResumeSectionProps {
  confirmedSkills: UserSkill[]
  onProfileReload: AsyncProfileReload
  client?: ResumeClient
  skillsClient?: SkillsClient
}

const formatter = new Intl.DateTimeFormat('en-SG', { dateStyle: 'medium', timeStyle: 'short' })

function formatUploaded(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : formatter.format(date)
}

/**
 * Resume upload, the skills found in it for the student to confirm, and the
 * manual skill editor. Suggestions are never saved automatically: "Add selected"
 * confirms the ticked ones one at a time, so one failure leaves the rest saved.
 */
export function ResumeSection({
  confirmedSkills,
  onProfileReload,
  client = resumeClient,
  skillsClient = profileSkillsClient,
}: ResumeSectionProps) {
  const [resume, setResume] = useState<ResumeResponse | null>(null)
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [unticked, setUnticked] = useState<Set<number>>(new Set())
  const [rows, setRows] = useState<Record<number, RowStatus>>({})
  const [adding, setAdding] = useState(false)
  const [reloadError, setReloadError] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  // Only the most recent load or upload may write the resume; older responses are dropped.
  const generation = useRef(0)
  const uploadingRef = useRef(false)
  const loadStateRef = useRef<'loading' | 'ready' | 'error'>('loading')

  const confirmedIds = new Set(confirmedSkills.map(skill => skill.skill_id))
  const suggestions = resume?.suggested_skills ?? []

  const updateLoadState = useCallback((state: 'loading' | 'ready' | 'error') => {
    loadStateRef.current = state
    setLoadState(state)
  }, [])

  const loadCurrent = useCallback(async () => {
    if (uploadingRef.current) return
    const mine = ++generation.current
    updateLoadState('loading')
    setLoadError(null)
    try {
      const current = await client.current()
      if (mine !== generation.current) return
      setResume(current)
      updateLoadState('ready')
    } catch (cause) {
      if (mine !== generation.current) return
      updateLoadState('error')
      setLoadError(isResumeClientError(cause) ? cause.message : 'Your resume did not load.')
    }
  }, [client, updateLoadState])

  useEffect(() => {
    void loadCurrent()
  }, [loadCurrent])

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = '' // lets the same file be chosen again after an error
    if (!file) return

    const problem = validateResumeFile(file)
    if (problem !== null) {
      setUploadError(problem)
      return
    }

    if (uploadingRef.current || adding) return
    const mine = ++generation.current // drops any load still in flight
    const stateBefore = loadStateRef.current
    setUploadError(null)
    uploadingRef.current = true
    setUploading(true)
    updateLoadState('ready')
    try {
      const uploaded = await client.upload(file)
      if (mine === generation.current) {
        setResume(uploaded)
        setUnticked(new Set())
        setRows({})
      }
    } catch (cause) {
      setUploadError(isResumeClientError(cause) ? cause.message : 'The upload did not work. Try again.')
      uploadingRef.current = false
      // The load we cancelled never reported; ask again so "No resume yet" is not a guess.
      if (stateBefore !== 'ready') void loadCurrent()
    } finally {
      uploadingRef.current = false
      setUploading(false)
    }
  }

  function toggle(skillId: number) {
    setUnticked(previous => {
      const next = new Set(previous)
      if (next.has(skillId)) next.delete(skillId)
      else next.add(skillId)
      return next
    })
  }

  async function confirm(skillIds: number[]) {
    if (uploadingRef.current) return
    setAdding(true)
    setReloadError(false)
    // One request at a time, so a failure is attributed to the right skill.
    for (const skillId of skillIds) {
      setRows(previous => ({ ...previous, [skillId]: 'saving' }))
      try {
        await skillsClient.add(skillId)
        setRows(previous => {
          const next = { ...previous }
          delete next[skillId]
          return next
        })
      } catch {
        setRows(previous => ({ ...previous, [skillId]: 'failed' }))
      }
    }
    try {
      await onProfileReload()
    } catch {
      setReloadError(true)
    }
    setAdding(false)
  }

  const pending = suggestions.filter(
    skill => !confirmedIds.has(skill.skill_id) && !unticked.has(skill.skill_id),
  )
  const hasPending = suggestions.some(skill => !confirmedIds.has(skill.skill_id))

  return (
    <div className="resume">
      <div className="resume__upload">
        <div className="resume__current" aria-live="polite">
          {loadState === 'loading' ? (
            <span className="muted resume__status">
              <Spinner size="sm" /> Checking for your resume…
            </span>
          ) : loadState === 'error' ? (
            <InlineError actionLabel={uploading ? undefined : 'Retry'} onAction={() => void loadCurrent()}>
              {loadError}
            </InlineError>
          ) : resume ? (
            <p className="resume__file">
              <Icon name="file-text" />
              <span className="resume__file-name">{resume.file_name}</span>
              <span className="muted">Uploaded {formatUploaded(resume.uploaded_at)}</span>
            </p>
          ) : (
            <p className="muted">No resume yet. Upload a PDF or DOCX, up to 5 MB.</p>
          )}
        </div>

        <input
          ref={fileInput}
          className="sr-only"
          type="file"
          accept={RESUME_ACCEPT}
          aria-label="Resume file"
          tabIndex={-1}
          onChange={event => void handleFile(event)}
        />
        <Button
          icon="upload-simple"
          busy={uploading}
          disabled={loadState === 'loading' || adding}
          onClick={() => fileInput.current?.click()}
        >
          {uploading ? 'Reading your resume…' : resume ? 'Replace resume' : 'Upload resume'}
        </Button>
      </div>

      {uploadError ? <InlineError>{uploadError}</InlineError> : null}

      {resume ? (
        <div className="resume__suggest">
          <h3 className="resume__subheading">Skills found in your resume</h3>
          {suggestions.length === 0 ? (
            <p className="muted">
              No new skills to add. Everything we found is already in your profile, or is not in the skills list.
            </p>
          ) : (
            <>
              <p className="muted">Untick any that are not right, then add the rest to your profile.</p>
              <ul className="resume__list">
                {suggestions.map(skill => {
                  const added = confirmedIds.has(skill.skill_id)
                  const status = rows[skill.skill_id] ?? 'idle'
                  const ticked = !unticked.has(skill.skill_id)
                  return (
                    <li key={skill.skill_id} className="resume__item">
                      <label className={ticked && !added ? 'checkbox is-checked' : 'checkbox'}>
                        <input
                          type="checkbox"
                          className="resume__check"
                          checked={added || ticked}
                          disabled={added || adding}
                          onChange={() => toggle(skill.skill_id)}
                        />
                        <span className="checkbox__box" aria-hidden="true">
                          {ticked || added ? <Icon name="check" /> : null}
                        </span>
                        <span className="resume__name">{skill.name}</span>
                      </label>
                      {added ? (
                        <Badge tone="accent" icon="check">Added</Badge>
                      ) : status === 'saving' ? (
                        <Spinner size="sm" label={`Adding ${skill.name}`} />
                      ) : status === 'failed' ? (
                        <span className="resume__failed" role="alert">
                          <Badge tone="danger" icon="warning-circle">Not saved</Badge>
                          <Button
                            variant="ghost"
                            disabled={adding || uploading}
                            aria-label={`Retry adding ${skill.name}`}
                            onClick={() => void confirm([skill.skill_id])}
                          >
                            Retry
                          </Button>
                        </span>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
              {hasPending ? (
                <div className="actions">
                  <Button
                    variant="primary"
                    busy={adding}
                    disabled={pending.length === 0 || uploading}
                    onClick={() => void confirm(pending.map(skill => skill.skill_id))}
                  >
                    {adding ? 'Adding…' : `Add selected (${pending.length})`}
                  </Button>
                </div>
              ) : null}
              {reloadError ? (
                <InlineError actionLabel="Reload" onAction={() => void onProfileReload().catch(() => undefined)}>
                  The list did not refresh.
                </InlineError>
              ) : null}
            </>
          )}
        </div>
      ) : null}

      <SkillEditor confirmedSkills={confirmedSkills} onProfileReload={onProfileReload} client={skillsClient} />
    </div>
  )
}

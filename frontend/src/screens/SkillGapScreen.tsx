import { useEffect, useRef, useState } from 'react'

import { Badge } from '../components/Badge'
import { Button, buttonClass } from '../components/Button'
import { Card } from '../components/Card'
import { EmptyState, InlineError, Notice, Spinner } from '../components/Feedback'
import { Icon } from '../components/Icon'
import { Meter } from '../components/Meter'
import { ApiError, toDisplayMessage } from '../lib/api-client'
import { Link } from 'react-router-dom'
import { routes } from '../app/routes'
import { skillGapClient } from '../features/skill-gap/activeClient'
import type { SkillGapClient, SkillGapResponse, SkillGapRow, SkillGapRole } from '../features/skill-gap/types'
import '../features/skill-gap/skill-gap.css'

function isProfileMissing(cause: unknown): boolean {
  if (cause instanceof ApiError) return cause.code === 'not_found' && cause.details?.resource === 'profile'
  return typeof cause === 'object' && cause !== null && 'code' in cause && cause.code === 'not_found' && 'details' in cause && typeof cause.details === 'object' && cause.details !== null && 'resource' in cause.details && cause.details.resource === 'profile'
}

function displayError(cause: unknown): string {
  if (cause instanceof ApiError) return toDisplayMessage(cause)
  if (typeof cause === 'object' && cause !== null && 'message' in cause && typeof cause.message === 'string') return cause.message
  return toDisplayMessage(cause)
}

export function SkillGapScreen({ client = skillGapClient }: { client?: SkillGapClient }) {
  const [roles, setRoles] = useState<SkillGapRole[]>([])
  const [role, setRole] = useState('')
  const [gap, setGap] = useState<SkillGapResponse | null>(null)
  const [rolesLoading, setRolesLoading] = useState(true)
  const [gapLoading, setGapLoading] = useState(false)
  const [rolesError, setRolesError] = useState<string | null>(null)
  const [rolesProfileMissing, setRolesProfileMissing] = useState(false)
  const [gapError, setGapError] = useState<string | null>(null)
  const [gapProfileMissing, setGapProfileMissing] = useState(false)
  const [confirmations, setConfirmations] = useState<Record<number, boolean>>({})
  const [pending, setPending] = useState<number | null>(null)
  const [addErrors, setAddErrors] = useState<Record<number, string>>({})
  const [addSuccess, setAddSuccess] = useState<Record<number, boolean>>({})
  const generation = useRef(0)
  const confirmedSkillIds = useRef(new Set<number>())
  const gapRef = useRef<SkillGapResponse | null>(null)
  function withConfirmedSkills(response: SkillGapResponse): SkillGapResponse {
    const skills = response.skills.map(skill => confirmedSkillIds.current.has(skill.skill_id) ? { ...skill, user_has: true } : skill)
    const user_has_in_top_n = skills.slice(0, response.summary.top_n).filter(skill => skill.user_has).length
    return { ...response, skills, summary: { ...response.summary, user_has_in_top_n } }
  }
  gapRef.current = gap

  async function loadRoles() {
    setRolesLoading(true); setRolesError(null); setRolesProfileMissing(false)
    try {
      const result = await client.roles()
      setRoles(result.items)
      setRole(current => result.items.some(item => item.role_category === current) ? current : '')
    } catch (cause) { setRolesError(displayError(cause)); setRolesProfileMissing(isProfileMissing(cause)) }
    finally { setRolesLoading(false) }
  }

  useEffect(() => { void loadRoles() }, [client])

  useEffect(() => {
    const requestId = ++generation.current
    setGap(null); gapRef.current = null; setGapError(null); setGapProfileMissing(false); setConfirmations({}); setAddErrors({}); setAddSuccess({}); setPending(null)
    if (!role) { setGapLoading(false); return }
    const controller = new AbortController()
    setGapLoading(true)
    client.forRole(role, controller.signal).then(result => {
      if (requestId !== generation.current) return
      const current = withConfirmedSkills(result)
      setGap(current); gapRef.current = current
    }).catch(cause => {
      if (requestId === generation.current) { setGapError(displayError(cause)); setGapProfileMissing(isProfileMissing(cause)) }
    }).finally(() => {
      if (requestId === generation.current) setGapLoading(false)
    })
    return () => { controller.abort() }
  }, [client, role])

  async function addSkill(skill: SkillGapRow) {
    if (!confirmations[skill.skill_id] || pending !== null || !role) return
    const targetRole = role
    const requestId = generation.current
    setPending(skill.skill_id); setAddErrors(current => ({ ...current, [skill.skill_id]: '' }))
    try {
      await client.add(skill.skill_id)
      confirmedSkillIds.current.add(skill.skill_id)
      if (generation.current === requestId) {
        setAddSuccess(current => ({ ...current, [skill.skill_id]: true }))
      }
      const current = gapRef.current
      if (current) {
        const updated = withConfirmedSkills(current)
        setGap(updated); gapRef.current = updated
      }
      // Reconcile the active role only. Every response overlays successful
      // additions so an older GET cannot undo a confirmed membership.
      if (generation.current === requestId) {
        try {
          const refreshed = withConfirmedSkills(await client.forRole(targetRole))
          if (generation.current === requestId) { setGap(refreshed); gapRef.current = refreshed }
        } catch { /* keep the successful PUT reflected in local state */ }
      }
    } catch (cause) {
      if (generation.current === requestId) setAddErrors(current => ({ ...current, [skill.skill_id]: displayError(cause) }))
    } finally {
      if (generation.current === requestId) setPending(null)
    }
  }

  function retryGap() {
    setGapError(null); setGapLoading(true)
    const id = ++generation.current
    client.forRole(role).then(result => {
      if (generation.current === id) { const current = withConfirmedSkills(result); setGap(current); gapRef.current = current }
    }).catch(error => {
      if (generation.current === id) { setGapError(displayError(error)); setGapProfileMissing(isProfileMissing(error)) }
    }).finally(() => {
      if (generation.current === id) setGapLoading(false)
    })
  }

  const pickedRole = roles.find(item => item.role_category === role)
  const onboardingLink = <Link className={buttonClass({ variant: 'primary' })} to={routes.welcome}>Start onboarding</Link>

  return <div className="skill-gap">
    <header className="skill-gap__head">
      <h1 className="skill-gap__title">Skill Gap</h1>
      <p className="skill-gap__lede">What employers in one field ask for, and which of those skills you have not added yet.</p>
    </header>

    {rolesLoading ? <p className="toast-line t-meta" role="status"><Spinner size="sm" />Loading roles…</p>
      : rolesError ? <div className="skill-gap__error-block">
        <InlineError actionLabel="Retry roles" onAction={() => void loadRoles()}><strong>The roles did not load.</strong> {rolesError}</InlineError>
        {rolesProfileMissing ? <div>{onboardingLink}</div> : null}
      </div>
      : roles.length === 0 ? <EmptyState icon="chart-bar-horizontal" title="No roles have active postings yet." actions={<Button icon="arrow-clockwise" onClick={() => void loadRoles()}>Check again</Button>}>
        None of the active postings has a role category yet. This fills in after the next job import is classified.
      </EmptyState>
      : <>
        <div className="field skill-gap__role">
          <label className="field__label" htmlFor="skill-gap-role">Role</label>
          <select id="skill-gap-role" aria-label="Target role" className={role ? 'field__input field__input--lg' : 'field__input field__input--lg skill-gap__role-empty'} value={role} onChange={event => setRole(event.target.value)}>
            <option value="" disabled>Pick a role…</option>
            {roles.map(item => <option key={item.role_category} value={item.role_category}>{item.role_category} ({item.job_count})</option>)}
          </select>
        </div>
        {role ? null : <EmptyState icon="chart-bar-horizontal" title="Pick a role to see your gap.">
          We count how often each skill appears across that role's active postings, then line it up with your profile. Nothing loads until you choose.
        </EmptyState>}
      </>}

    {role && <section className="skill-gap__result" aria-label={`Skill gap for ${role}`}>
      {gapLoading && !gap ? <>
        <p className="toast-line t-meta" role="status"><Spinner size="sm" />{pickedRole ? `Counting skills across ${pickedRole.job_count} ${pickedRole.job_count === 1 ? 'posting' : 'postings'}` : 'Loading skill gaps…'}</p>
        <div className="skill-gap__skeleton" aria-hidden="true">
          {[42, 55, 68, 46, 60].map((width, index) => <div className="skill-gap__row" key={index}>
            <span className="skill-gap__rank">{index + 1}</span>
            <div className="skill-gap__main">
              <span className="skel skill-gap__skel-name" style={{ width: `${width}%` }} />
              <span className="skel skill-gap__skel-bar" />
              <span className="skel skill-gap__skel-facts" />
            </div>
            <div className="skill-gap__side"><span className="skel skill-gap__skel-side" /></div>
          </div>)}
        </div>
      </> : null}
      {gapError ? <div className="skill-gap__error-block">
        <InlineError actionLabel="Retry skill gaps" onAction={retryGap}><strong>The skill counts did not load.</strong> {gapError}</InlineError>
        {gapProfileMissing ? <div>{onboardingLink}</div> : null}
      </div> : null}
      {gap && <>
        {gap.sample_size < 5 ? <div role="status"><Notice>
          <strong>Small sample: only {gap.sample_size} active {gap.sample_size === 1 ? 'posting' : 'postings'} for this role.</strong>{' '}
          <span className="muted">Skill frequencies may be less representative. Treat them as a hint, not a trend.</span>
        </Notice></div> : null}
        {gap.skills.length === 0 ? <EmptyState icon="question" title={`Nothing to count for ${gap.role_category}.`}>
          <span>No skill requirements are available for this role yet.</span>{' '}
          <span>Based on {gap.sample_size} active postings for {gap.role_category}</span>, none listed skills we could read. Try a neighbouring role, or open a few postings directly.
        </EmptyState> : <>
          <Card className="skill-gap__summary-card">
            <div className="skill-gap__summary-text">
              <h2 className="skill-gap__summary" aria-live="polite">You have {gap.summary.user_has_in_top_n} of the top {gap.summary.top_n} skills for this role.</h2>
              <p className="t-meta">Based on {gap.sample_size} active postings for {gap.role_category}</p>
            </div>
            <div className="skill-gap__meter"><Meter value={gap.summary.user_has_in_top_n} total={gap.summary.top_n} label={`${gap.summary.user_has_in_top_n} of the top ${gap.summary.top_n}`} /></div>
          </Card>
          <ol className="skill-gap__list">
            {gap.skills.map((skill, index) => {
              const percent = gap.sample_size ? Math.round(skill.frequency * 100) : 0
              const confirmed = Boolean(confirmations[skill.skill_id])
              return <li className="skill-gap__row" key={skill.skill_id}>
                <span className="skill-gap__rank" aria-hidden="true">{index + 1}</span>
                <div className="skill-gap__main">
                  <div className="skill-gap__top">
                    <span className="skill-gap__name">{skill.name}</span>
                    <span className="skill-gap__freq">{skill.job_count} / {gap.sample_size} postings · {gap.sample_size ? `${percent}%` : '0%'}</span>
                  </div>
                  <div className="bar" role="img" aria-label={`${skill.name}: ${percent}% of postings`}><span className={skill.user_has ? 'bar__fill bar__fill--have' : 'bar__fill'} style={{ width: `${gap.sample_size ? Math.max(0, Math.min(100, skill.frequency * 100)) : 0}%` }} /></div>
                  <p className="skill-gap__facts">
                    <span><span className="req">Required</span> <span className="mono">{skill.required_count}</span></span>{' '}
                    <span><span className="req req--pref">Preferred</span> <span className="mono">{skill.preferred_count}</span></span>
                  </p>
                  {skill.max_minimum_years !== null && skill.years_mentions > 0 ? <p className="skill-gap__experience">Experience mentioned: up to {skill.max_minimum_years} yrs ({skill.years_mentions} postings)</p> : null}
                </div>
                <div className="skill-gap__side">
                  {skill.user_has ? <Badge tone="accent" icon="check">You have this</Badge> : <>
                    <Badge tone="gap">Gap</Badge>
                    <label className={confirmed ? 'checkbox is-checked skill-gap__confirm' : 'checkbox skill-gap__confirm'}>
                      <input type="checkbox" checked={confirmed} disabled={pending !== null} onChange={event => setConfirmations(current => ({ ...current, [skill.skill_id]: event.target.checked }))} />
                      <span className="checkbox__box" aria-hidden="true">{confirmed ? <Icon name="check" /> : null}</span>
                      I already have this skill
                    </label>
                    <Button variant={confirmed ? 'accent' : 'ghost'} icon="plus" busy={pending === skill.skill_id} disabled={!confirmed || pending !== null} onClick={() => void addSkill(skill)}>{pending === skill.skill_id ? 'Adding…' : addSuccess[skill.skill_id] ? 'Added' : 'Add to my skills'}</Button>
                  </>}
                </div>
                {!skill.user_has && addErrors[skill.skill_id] ? <div className="inline-error skill-gap__add-error" role="alert">
                  <Icon name="warning-circle" />
                  <span className="inline-error__text">{addErrors[skill.skill_id]}</span>
                  <Button icon="arrow-clockwise" disabled={pending !== null} onClick={() => void addSkill(skill)}>Retry</Button>
                </div> : null}
              </li>
            })}
          </ol>
        </>}
      </>}
    </section>}
  </div>
}

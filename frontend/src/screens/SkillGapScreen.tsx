import { useEffect, useRef, useState } from 'react'

import { InlineError } from '../components/Feedback'
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
  const gapRef = useRef<SkillGapResponse | null>(null)
  gapRef.current = gap

  async function loadRoles() {
    setRolesLoading(true); setRolesError(null); setRolesProfileMissing(false)
    try {
      const result = await client.roles()
      setRoles(result.items)
      setRole(current => result.items.some(item => item.role_category === current) ? current : result.items[0]?.role_category ?? '')
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
      setGap(result); gapRef.current = result
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
      if (generation.current !== requestId || role !== targetRole) return
      setAddSuccess(current => ({ ...current, [skill.skill_id]: true }))
      const current = gapRef.current
      if (current?.role_category === targetRole) {
        const skills = current.skills.map(item => item.skill_id === skill.skill_id ? { ...item, user_has: true } : item)
        const user_has_in_top_n = skills.slice(0, current.summary.top_n).filter(item => item.user_has).length
        const updated = { ...current, skills, summary: { ...current.summary, user_has_in_top_n } }
        setGap(updated); gapRef.current = updated
      }
      // Reconcile with server after the successful 204. A refresh failure does
      // not undo the confirmed local state or claim that the PUT failed.
      try {
        const refreshed = await client.forRole(targetRole)
        if (generation.current === requestId && role === targetRole) { setGap(refreshed); gapRef.current = refreshed }
      } catch { /* keep the successful PUT reflected in local state */ }
    } catch (cause) {
      if (generation.current === requestId && role === targetRole) setAddErrors(current => ({ ...current, [skill.skill_id]: displayError(cause) }))
    } finally {
      if (generation.current === requestId) setPending(null)
    }
  }

  return <main className="skill-gap stack-lg">
    <section className="stack">
      <h1 className="heading-1">Skill Gap</h1>
      <hr className="rule rule--heavy" />
      <label className="skill-gap__role-label" htmlFor="skill-gap-role">Target role</label>
      {rolesLoading ? <p role="status">Loading roles…</p> : rolesError ? <div className="stack-sm"><InlineError>{rolesError}</InlineError>{rolesProfileMissing ? <Link to={routes.welcome}>Start onboarding</Link> : null}<button className="button" type="button" onClick={() => void loadRoles()}>Retry roles</button></div> : roles.length === 0 ? <p>No roles have active postings yet.</p> : <select id="skill-gap-role" aria-label="Target role" value={role} onChange={event => setRole(event.target.value)}>
        {roles.map(item => <option key={item.role_category} value={item.role_category}>{item.role_category} ({item.job_count})</option>)}
      </select>}
    </section>
    {role && <section className="stack" aria-live="polite">
      {gapLoading && !gap ? <p role="status">Loading skill gaps…</p> : null}
      {gapError ? <div className="stack-sm"><InlineError>{gapError}</InlineError>{gapProfileMissing ? <Link to={routes.welcome}>Start onboarding</Link> : null}<button className="button" type="button" onClick={() => { setGapError(null); setGapLoading(true); const id = ++generation.current; client.forRole(role).then(result => { if (generation.current === id) { setGap(result); gapRef.current = result } }).catch(error => { if (generation.current === id) { setGapError(displayError(error)); setGapProfileMissing(isProfileMissing(error)) } }).finally(() => { if (generation.current === id) setGapLoading(false) }) }}>Retry skill gaps</button></div> : null}
      {gap && <>
        <h2 className="heading-2">Based on {gap.sample_size} active postings for {gap.role_category}</h2>
        {gap.sample_size < 5 ? <p className="skill-gap__warning" role="status">Small sample: fewer than 5 active postings. Skill frequencies may be less representative.</p> : null}
        <p className="skill-gap__summary">You have {gap.summary.user_has_in_top_n} of the top 10 skills for this role.</p>
        {gap.skills.length === 0 ? <p>No skill requirements are available for this role yet.</p> : <ol className="skill-gap__list">
          {gap.skills.map(skill => <li className="skill-gap__row" key={skill.skill_id}>
            <div className="skill-gap__row-head"><strong>{skill.name}</strong><span>{skill.job_count} / {gap.sample_size} postings · {gap.sample_size ? `${Math.round(skill.frequency * 100)}%` : '0%'}</span><span>{skill.user_has ? '✓ You have this' : 'Gap'}</span></div>
            <div className="skill-gap__bar" role="img" aria-label={`${skill.name}: ${gap.sample_size ? Math.round(skill.frequency * 100) : 0}% of postings`}><span style={{ width: `${gap.sample_size ? Math.max(0, Math.min(100, skill.frequency * 100)) : 0}%` }} /></div>
            <p className="skill-gap__split">REQUIRED {skill.required_count} · PREFERRED {skill.preferred_count}</p>
            {skill.max_minimum_years !== null && skill.years_mentions > 0 ? <p className="skill-gap__experience">Experience mentioned: up to {skill.max_minimum_years} yrs ({skill.years_mentions} postings)</p> : null}
            {!skill.user_has && <div className="skill-gap__add">
              <label><input type="checkbox" checked={Boolean(confirmations[skill.skill_id])} disabled={pending !== null} onChange={event => setConfirmations(current => ({ ...current, [skill.skill_id]: event.target.checked }))} /> I already have this skill</label>
              <button type="button" className="button button--primary" disabled={!confirmations[skill.skill_id] || pending !== null} onClick={() => void addSkill(skill)}>{pending === skill.skill_id ? 'Adding…' : addSuccess[skill.skill_id] ? 'Added' : 'Add to my skills'}</button>
              {addErrors[skill.skill_id] ? <span className="skill-gap__error" role="alert">{addErrors[skill.skill_id]} <button type="button" className="button button--quiet" disabled={pending !== null} onClick={() => void addSkill(skill)}>Retry</button></span> : null}
            </div>}
          </li>)}
        </ol>}
      </>}
    </section>}
  </main>
}

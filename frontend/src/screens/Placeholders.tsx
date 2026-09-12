import { NotBuiltYet } from '../components/Feedback'

/**
 * Routed placeholders for the screens the other pair owns. They exist so the
 * navigation works end to end and so nobody has to invent a route later.
 */

export function DiscoverScreen() {
  return (
    <NotBuiltYet
      title="Discover"
      body="Jobs matching your confirmed skills appear here, newest first. Swipe left to record not interested, right to save. Both decisions move the job to your vault."
    />
  )
}

export function VaultScreen() {
  return (
    <NotBuiltYet
      title="Vault"
      body="Everything you saved or passed on, with the status you set: saved, applied, interview, rejected or offer. You change the status yourself after applying on the employer's site."
    />
  )
}

export function SkillGapScreen() {
  return (
    <NotBuiltYet
      title="Skill gap"
      body="Pick a role you are aiming for and see which skills its postings ask for most often, which of those you have already confirmed, and which you do not."
    />
  )
}

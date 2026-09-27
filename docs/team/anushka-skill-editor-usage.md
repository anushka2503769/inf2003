# SkillEditor — usage notes for shell integration

For Nasya, wiring `<SkillEditor>` into `ProfileScreen.tsx` (or wherever the
"Resume and skills" section ends up living).

## Where it lives

```
frontend/src/features/skills/SkillEditor.tsx
```

Everything it needs is exported from that file and `./types`. Nothing else
in `features/skills/` needs to be imported directly by the shell.

## Minimal usage

```tsx
import { SkillEditor } from '../features/skills/SkillEditor'
import { useProfile } from '../auth/useProfile'

function ProfileScreen() {
  const { profile, reload } = useProfile() // see "Depends on" below

  return (
    // ...existing shell markup...
    <SkillEditor
      confirmedSkills={profile?.skills ?? []}
      onProfileReload={reload}
    />
  )
}
```

That's the whole integration. `SkillEditor` owns its own search/add/remove
state internally; the shell only needs to hand it the current confirmed list
and a way to ask for a fresh one.

## Props

| Prop | Type | Notes |
|---|---|---|
| `confirmedSkills` | `UserSkill[]` | Whatever the shell currently has for the signed-in student. `SkillEditor` never mutates this itself — it only reads it to know what's already confirmed (so search results show "Added" instead of an Add button) and to render the confirmed-skills list with Remove buttons. |
| `onProfileReload` | `() => Promise<void>` | Called after every successful add/remove. Must resolve only once fresh data has actually landed — see "Depends on" below for why this can't be fire-and-forget. |
| `className` | `string?` | Optional, for shell layout hooks. No global CSS is touched — see `skill-editor.css`, scoped entirely under `.skill-editor__*`. |
| `client` | `SkillsClient?` | Optional, defaults to a built-in mock (`mockSkillsClient` from `./client`). A real implementation now exists — see `realClient.ts` below. |

## Depends on (both landed — merged via PR #2 from `dev`)

1. **`MeResponse.skills: Skill[]`** on `types/api.ts` — `profile.skills` in
   the example above is real now.
2. **`ProfileContextValue.reload` promisified** to `() => Promise<void>` —
   resolves after the fetch settles, rejects on genuine failure (not on "no
   profile row yet", which stays a normal state, not an error).

Full test suite (44 tests) and `npm run build` pass with both in place —
verified from a fresh clone, not carried over from an earlier check.

## The real client — ready to use, not just proposed anymore

`SkillEditor`'s `client` prop defaults to a mock (`mockSkillsClient`). A real
adapter now exists and talks to Jason's actual `/api/skills` and
`/api/me/skills/{id}` endpoints (confirmed against
`backend/app/routers/skills.py`, merged in via `dev`):

```
frontend/src/features/skills/realClient.ts
```

It goes through the shared `skillsApi` (`lib/api.ts`) — the same additive,
`profileApi`-shaped helpers, not a second fetch layer — which itself calls
the existing authenticated `request()`. Wiring it in is exactly the one-line
prop swap it always was meant to be:

```tsx
import { realSkillsClient } from '../features/skills/realClient'

<SkillEditor
  confirmedSkills={profile?.skills ?? []}
  onProfileReload={reload}
  client={realSkillsClient} // instead of the default mock
/>
```

Nothing in `SkillEditor.tsx` itself changed for this swap — exactly as
originally promised. 9 tests in `realClient.test.ts` cover this against a
faked `fetch`, proving the full `realClient -> skillsApi -> request ->
fetch` path round-trips correctly (query building, 204-with-no-body,
error-envelope parsing) — not yet exercised against a real running server,
since that needs an actual Postgres instance with seeded skill rows
(flagging as blocked on environment access, not silently assumed to work).

## What NOT to do

- Don't hold a second copy of confirmed skills anywhere in the shell for this
  component specifically — `SkillEditor` re-reads via `onProfileReload`
  rather than predicting the new state itself, so the shell's `profile.skills`
  should stay the single source of truth.
- Don't pass a `client` unless you're intentionally overriding the default —
  the mock is safe to ship as-is for any screen that isn't ready to hit the
  real backend yet.
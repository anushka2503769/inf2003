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
| `client` | `SkillsClient?` | Optional, defaults to a built-in mock (`mockSkillsClient` from `./client`). **This is the one thing that still needs a real implementation before this is live** — see "Still needed" below. |

## Depends on (both proposed, not yet merged — see PR to `dev`)

1. **`MeResponse.skills: Skill[]`** on `types/api.ts` — so `profile.skills` in
   the example above actually exists. Currently `MeResponse` only has
   `{profile, onboarding_complete}`.
2. **`ProfileContextValue.reload` promisified** to `() => Promise<void>` —
   currently `() => void` (fire-and-forget). `SkillEditor` awaits this after
   every write and only clears a row's pending state once it resolves; if it
   rejects, the row shows "Saved, but your skill list could not be
   refreshed" rather than claiming the write itself failed. A synchronous
   `reload` can't support that distinction.

Both are drafted as ready-to-review diffs (see PR description / the two
files directly: `frontend/src/types/api.ts`, `frontend/src/auth/ProfileProvider.tsx`).
Full test suite (35 tests) and `npm run build` pass with both applied.

## Still needed before this is live (not the shell's job — flagging so it's visible)

`SkillEditor`'s `client` prop defaults to a mock (`mockSkillsClient`). A real
adapter implementing the `SkillsClient` interface (`search`/`add`/`remove`)
against `lib/api.ts`'s authenticated `request()` doesn't exist yet — that's
the last piece before this talks to Jason's actual `/api/skills` and
`/api/me/skills/{id}` endpoints instead of in-memory fixtures. Once it
exists, wiring it in is a one-line prop:

```tsx
<SkillEditor
  confirmedSkills={profile?.skills ?? []}
  onProfileReload={reload}
  client={realSkillsClient} // instead of the default mock
/>
```

Nothing in `SkillEditor.tsx` itself needs to change for that swap.

## What NOT to do

- Don't hold a second copy of confirmed skills anywhere in the shell for this
  component specifically — `SkillEditor` re-reads via `onProfileReload`
  rather than predicting the new state itself, so the shell's `profile.skills`
  should stay the single source of truth.
- Don't pass a `client` unless you're intentionally overriding the default —
  the mock is safe to ship as-is for any screen that isn't ready to hit the
  real backend yet.
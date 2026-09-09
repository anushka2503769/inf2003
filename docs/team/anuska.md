# Anuska — confirmed-skill editing

Read [team workflow](README.md), [setup](../README.md), [PRD](../PRD.md) and
[API contract](../API.md). Own the skill editor in the first milestone; Nasya owns
the profile shell, authentication and shared API client.

## ANU-01 — skill editor against contract-shaped mocks

Planned owned files: frontend/src/features/skills/* (component, local styles and tests).

- Agree SkillEditor props and shared client exports with Nasya before implementation.
  Start from confirmed skills plus an async profile-reload callback. Agree exact types
  in a small shared change; do not create a competing global client/types module.
- Search GET /api/skills, display results/empty state and ask for a narrower query when
  has_more is true. Handle stale search responses so old results do not replace newer ones.
- Add with PUT /api/me/skills/{skill_id}; remove with DELETE. No free-text dictionary
  creation. Handle 204 without parsing a body; refresh GET /api/me on success.
- Serialize operations on the same skill and show pending/error state. Do not claim
  failed operations were saved or replay old skill edits automatically offline.
- Provide synthetic mocks with the exact API shapes, including empty results,
  SKILL_NOT_FOUND, validation and service failures. Mock IDs need not equal live seed IDs.

Done when: search/select/remove behaviours and failures are tested in isolation, the
component accepts its agreed inputs, and styling stays local to avoid shell conflicts.

## ANU-02 — integrate with Nasya and Jason

- Deliver the component/export and usage notes to Nasya, who wires the application shell.
- Use the common authenticated client; do not create a second Supabase session manager.
- Test adding/removing and reloading against Jason's live endpoints with real test-user
  identity and canonical skill IDs from the actual lookup response.

Done when: confirmed skills survive reload, no-op operations work, logout/account changes
do not show a previous user's skills, and integration is recorded beyond mock-only checks.

## Boundaries and progress

Coordinate package/test-tool additions through Nasya. Do not edit App.tsx, global CSS or
shared dependency files concurrently. Vault/Tracker and Skill Gap screens are later tasks
and require their API contracts before implementation.

Initial status: ANU-01/02 not verified complete; skill UI/client integration is not built.
Inspect current state before starting. Append task/result/check/PR/next-step notes here.

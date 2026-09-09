# Zhihao — moderator, final reviewer and integration

Read [team workflow](README.md), [PRD](../PRD.md), [API contract](../API.md),
[ERD](../erd.md) and [database setup](../DB/README.md).

## ZHI-01 — coordinate the starting baseline

- Review the two database scripts and API contract with the team. Discuss refinements
  together; Jason/Jiaxin prepare their database changes and verify their own work.
- Ensure the baseline reaches the agreed shared dev branch before teammates branch
  from it. A local uncommitted document is not available in teammates' clones.
- Confirm access continuity for the development projects Jason and Jiaxin set up.
  They own setup; you do not need to create both deployments personally.
- Confirm the early dependency order: Nasya's common UI/client interfaces unblock
  Anuska; Jason's Supabase/auth/API work enables live profile integration; Jiaxin can
  verify MongoDB independently without blocking the first SQL profile milestone.
- Own changes to shared API/PRD/ERD documents and coordinate one editor for each.

Done when: everyone can find their guide and the same contract, database targets/owners
are known, and each person has a small first task with clear dependencies.

## ZHI-02 — review focused PRs into dev

Use [the PR checklist](../pull-request-template.md). Check behaviour and evidence:

- Does the change fulfil its task acceptance criteria and match API.md exactly?
- Did the author test success, validation, retry/error and ownership where relevant?
- Are real database checks distinguished from static/unit/mock checks?
- Are schema changes reproducible, with applied scripts preserved and shared data safe?
- Are secrets and personal data absent from source/examples/logs?
- Were shared-file and dependency changes coordinated with the other developer?

Return concrete feedback to the owner when needed. Final review does not make you the
sole tester. Agents must not approve their own PRs on your behalf; follow applicable
runtime/repository merge authority when performing integration.

## ZHI-03 — demonstrate the first complete flow

After component PRs land in dev, verify with the team:
Google sign-in → create/read profile → edit name → select/remove skills → reload.
Include a returning user, an expired session and two different accounts. Run the
documented build/backend checks and confirm the real API contract before promoting
the milestone to main. No deployment or branch protection is implied by these guides.

## Progress

Initial status: guides, API contract and bootstrap scripts are prepared locally;
publication, applied database state and feature completion must be checked. Only the
starter/health flow has implementation evidence at guide creation. Append reviewed
task/PR, integration checks and next milestone notes here without duplicating everyone’s logs.

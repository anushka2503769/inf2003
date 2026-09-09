# Jiaxin — MongoDB and document access

Read [team workflow](README.md), [PRD](../PRD.md), [ERD](../erd.md),
[MongoDB setup](../DB/README.md#mongodb) and the [API contract](../API.md).
Own MongoDB deployment/document work. Jason owns shared Python auth and SQL access.

## JIA-01 — prepare and verify MongoDB development storage

- Select/configure the intended team development deployment using the available account
  and explicit target authorization. Discuss costs before choosing a paid resource.
- Arrange appropriate project access for Zhihao and a database user scoped to the
  application database. Keep credentials outside Git; document names, not secret values.
- Review/apply docs/DB/001_initial_collections.js according to DB/README.md. It is not
  atomic; inspect and repair partial setup rather than dropping existing collections.
- Verify validators and unique reference indexes using synthetic records: valid insert,
  duplicate user/job reference, missing/wrong field types and resume replacement.
- Use isolated synthetic IDs and remove only your own fixtures. Test parent-reference
  handling separately: MongoDB itself cannot prove SQL IDs exist.

Done when: both collections, validators and indexes are inspected on the intended
deployment, checks are recorded and current-resume replacement is demonstrated.

## JIA-02 — minimal Python MongoDB access

Planned owned files: backend/app/documents.py and backend/tests/test_documents.py.

- Coordinate driver/config additions with Jason before changing backend shared files.
  Keep one settings/auth implementation. Agree the document-module call signatures with
  Jason before another feature depends on them.
- Implement only current-resume and current-job document read/write operations needed
  by the skeleton, with predictable missing-document behaviour and explicit database selection.
- Test BSON date/ID handling, duplicate protection, replacement and error behaviour.
  Unit fixtures can run without the SQL API. Live tests must be explicitly selected
  and must not reset a shared database.

Done when: the access module can be tested independently, failures are surfaced clearly,
and no real credentials/resumes are in fixtures or logs. No public document endpoints
are implied; the first profile/skill milestone does not yet depend on MongoDB.

## Later work — discuss before implementation

Resume upload/extraction, JD processing and role-gap aggregation belong here later.
They need contracts, provider selection and normalization/SQL consistency decisions.
Do not choose an LLM/job provider, invent endpoints or start a background-worker system
as part of JIA-01/02. Raise ambiguities in validators for team review.

## Progress

Initial status: JIA-01/02 not verified complete. The bootstrap has syntax/simulated-shell
checks only; no deployment, live enforcement or Python document module is verified.
Inspect current code before work. Append task/result/check/PR/next-step notes here.

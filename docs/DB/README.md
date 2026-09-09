# Database skeleton v1

[001_initial_schema.sql](001_initial_schema.sql) creates the six agreed PostgreSQL
tables on Supabase. It is a provisional team baseline; review and refine it together.
It has not been applied to a shared database by this task.

## Apply the SQL skeleton

1. Review the script against [the ERD](../erd.md).
2. Open the intended development Supabase project's SQL Editor. This script requires
   Supabase's `auth.users`, `anon`, `authenticated` and `service_role` objects to exist.
3. Run the complete script once as the project database administrator. None of its
   six `public` tables should exist yet. All statements are in one transaction.
4. Confirm the six tables, primary/foreign keys, indexes and enabled RLS in the dashboard.
   Verify table access and constraints in the development environment before building on it.
5. Record the application date and commit in the team's PR. After the first application,
   preserve this file and add numbered change scripts for refinements.

If a table already exists, stop and compare the schemas. The script deliberately does
not use `IF NOT EXISTS`, which could conceal a different existing schema. It does not
drop data. Do not run the directory with a wildcard: future scripts must run in order.

## Choices in this baseline

- All six agreed tables and columns are preserved. No additional application tables.
- `public.users.user_id` references `auth.users.id` for Google sign-in via Supabase Auth.
  Passwords and email login identity stay in Supabase Auth. Google provider configuration
  is a separate dashboard task, not part of this SQL file.
- Foreign keys use `ON DELETE RESTRICT`. Remove dependent records explicitly when a
  future deletion flow is designed. Account deletion also needs MongoDB cleanup; there
  is no cross-database cascade. Mark closed jobs inactive to preserve tracker records.
- `skills.name` rejects blank/surrounding-space values and has a case-insensitive unique
  index. The backend handles synonyms and normalizes provider identifiers before import.
- Job type and work arrangement may be null when unknown. An internship takes the
  `INTERNSHIP` category even when full-time. Status and requirement type are required.
- Python maintains `updated_at` and `last_seen_at` on updates. No automatic timestamp
  triggers or automatic profile-creation trigger are included in the minimal skeleton.
- The backend must validate application URLs and extraction results; a nonblank URL
  constraint alone does not establish that a URL is valid or safe to open.

## Access through Python

The frontend uses Supabase directly only for authentication. The script enables RLS
and revokes `PUBLIC`, `anon` and `authenticated` access to these six application tables
and the skill-ID sequence. A frontend publishable key or user token cannot query them
directly. This does not change Supabase Auth's own tables or sign-in behaviour.

The script grants CRUD access to `service_role` for a trusted Python backend using a
server-only secret key. This is an explicit baseline implementation choice: that role
bypasses RLS, so every personal-data route must verify the token, derive the user ID
from that token and enforce ownership. RLS does not perform ownership checks for that
privileged backend. A publishable key alone will not support these database operations.
No backend connection or authorization routes are implemented by this script.

## MongoDB

Use [001_initial_collections.js](001_initial_collections.js) in `mongosh`, not the
Supabase SQL Editor. Connect to the intended development MongoDB deployment using
its connection instructions, with credentials kept outside repository files. Start
mongosh from the repository root, then run:

```javascript
use jobless_simulator
db.getName()
load('docs/DB/001_initial_collections.js')
```

Select the team's actual database name if it differs from `jobless_simulator`.
The script uses the selected database; it refuses system databases and the default
`test` database. It also checks both collection names before making changes and stops
if either already exists. Run it while no application writers are active.

It creates strict validators and unique `user_id` / `job_id` indexes, plus a role-category
index for job filtering. MongoDB automatically creates each collection's `_id` index.
After running, inspect:

```javascript
db.getCollectionInfos({ name: { $in: ['resume_documents', 'job_documents'] } })
db.resume_documents.getIndexes()
db.job_documents.getIndexes()
```

Unlike the SQL bootstrap, these setup commands are not one atomic transaction. If an
operation fails, earlier creations may remain. Inspect the collections and indexes and
complete the missing steps through a reviewed repair; do not drop collections or blindly
rerun this bootstrap. Preserve the script after applying it and use separate change
scripts for refinements.

### Document rules

- UUID references are lowercase strings, dates are BSON dates (Python datetime values;
  `new Date()` in mongosh), and `_id` is an automatically generated ObjectId.
- Resume skills are an array of suggested skill-name strings. Education, experience and
  projects are arrays of flexible objects, since their detailed formats are not finalized.
- Job skill IDs must be BSON 32-bit integers, matching SQL integer IDs. In mongosh use
  `Int32(1)`; Python's ordinary small integer values are encoded as BSON int32 by PyMongo.
- Each requirement includes REQUIRED/PREFERRED, nonblank evidence, and `minimum_years`
  as a nonnegative number or explicit null when not stated. Do not infer missing years.
- Stable top-level fields are enforced. Extraction objects allow additional fields to
  retain useful future LLM output without adding collections. Required arrays may be empty
  after a successful extraction that found no entries; failed extraction must not be
  disguised as empty results. This v1 collection stores completed extraction documents.
- MongoDB cannot check that a referenced SQL user, job or skill exists. Python must
  validate IDs, deduplicate requirements by skill, resolve ambiguous extraction results
  and maintain SQL/Mongo consistency. It must verify user ownership on every personal-data
  operation. These validators are not access controls or proof that LLM evidence is accurate.
- This script does not configure database users, network access or credentials. Connect
  only from the backend with an appropriately scoped database user.

Before integrating the app, test valid inserts, invalid field types/required fields,
duplicate references and replacement of the current resume using synthetic data.

## Verification status

The file has been reviewed statically against the agreed fields and current official
documentation. No local PostgreSQL executable is available in this session, so execution
and constraint/access tests on Supabase remain to be performed by the team. MongoDB
script syntax and bootstrap flow are checked locally using a simulated shell interface;
mongosh is not installed here. Actual MongoDB validator enforcement and index behaviour
must still be tested on the development database. Neither script has been applied remotely.

References: [Supabase user data](https://supabase.com/docs/guides/auth/managing-user-data),
[Supabase RLS and grants](https://supabase.com/docs/guides/database/postgres/row-level-security),
[PostgreSQL constraints](https://www.postgresql.org/docs/current/ddl-constraints.html).
MongoDB references: [JSON Schema validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/)
and [createCollection](https://www.mongodb.com/docs/manual/reference/method/db.createCollection/).

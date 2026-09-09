# Project context

Updated 9 September 2026. The current source of truth is [PRD.md](PRD.md).
The approved provisional table/collection skeleton is in [erd.md](erd.md).
See [README.md](README.md) for setup and team workflow.

Jobless Simulator helps students discover suitable jobs, save both interested and
not-interested decisions, track external applications and explore target-role skill gaps.

The team selected TypeScript frontend and Python backend. The starter uses React/Vite
and FastAPI. PostgreSQL and MongoDB integrations are planned, not implemented.

Zhihao moderates and performs final review. Nasya and Anuska handle frontend;
Jason and Jiaxin handle backend. The professor accepted the current skeleton as an MVP
starting point, with refinement expected as the course progresses.

Earlier ideas of separate swipes/applications/history tables and LLM-controlled ranking
are superseded. The current design has six SQL tables and two MongoDB collections.
LLM extraction assists data entry; matching/analytics use stored evidence and defined rules.

# Expert Content Studio implementation - Checkpoint

- Task ID: 2026-08-12-expert-content-studio
- Current todo: Prepare isolated development workspace and dispatch Task 1
- Active slice: Task 1 service scaffold
- Blocked on: none
- Next step: Create a verified Git worktree, then dispatch the Task 1 implementer

## Checkpoint Update

- Current todo: Implement Task 1: scaffold service and safe health configuration
- Active slice: Task 1 service scaffold
- Completed todos:
- none
- Evidence refs:
- Git worktree feature/expert-content-studio created from main 1c08c9d
- Blocked on: none
- Next step: Dispatch Task 1 implementation subagent

## DriftCheckDraft

- Scope status: Still aligned to the approved full-stack plan
- Compatibility status: No source code or credential boundary changed during setup
- Retirement status: No legacy owner or fallback exists in the greenfield worktree
- New risk signals:
- none
- Advisory decision: continue

## Checkpoint Update

- Current todo: Resolve Task 1 spec review gaps
- Active slice: Task 1 review repair
- Completed todos:
- none
- Evidence refs:
- Spec review: Uvicorn undeclared and TDD red evidence not persisted
- Blocked on: none
- Next step: Add project-declared Uvicorn, regenerate lock and rerun Task 1 verification

## DriftCheckDraft

- Scope status: Task 1 only: backend service configuration and health contract; no unplanned product feature
- Compatibility status: Secrets remain server-only; response contract typed and stable; AI absence is explicit
- Retirement status: Deprecated TestClient test path retired; no legacy production path exists
- New risk signals:
- No AI/X credentials expected; later tasks must retain configuration-missing behavior
- Advisory decision: continue

## Checkpoint Update

- Current todo: Implement Task 2: canonical persistence and migration ownership
- Active slice: Task 2 persistence
- Completed todos:
- Task 1: service scaffold and safe health configuration
- Evidence refs:
- Task 1 verified: uv lock --check, pytest -q -W error (3 passed), ruff check, isolated uvicorn import
- Blocked on: none
- Next step: Commit verified Task 1 changes, then dispatch Task 2 persistence implementer

## Checkpoint Update

- Current todo: Resolve Task 2 persistence integrity review findings
- Active slice: Task 2 database integrity repair
- Completed todos:
- Task 1: service scaffold and safe health configuration
- Evidence refs:
- Task 2 spec review found P1: no PostgreSQL driver, SQLite foreign keys disabled, cross-source artifact parent permitted
- Blocked on: none
- Next step: Implement and test DB-level referential and lineage constraints, then re-review Task 2

## DriftCheckDraft

- Scope status: Task 2 repair stays within canonical persistence and migrations
- Compatibility status: Strengthens source/artifact contract without adding routes or changing health API
- Retirement status: No fallback is added; database becomes canonical enforcement layer
- New risk signals:
- Artifact lineage and foreign-key integrity must be DB-enforced on default SQLite and PostgreSQL dialect
- Advisory decision: continue

## DriftCheckDraft

- Scope status: Task 2 persistence only; no connector/API/AI/frontend scope introduced
- Compatibility status: DB now enforces source/artifact/note provenance; bare PostgreSQL and special credentials normalize consistently for app and Alembic
- Retirement status: No legacy fallback; deprecated test client remains retired; default DB file excluded from version control
- New risk signals:
- No live PostgreSQL instance tested; offline dialect/DDL and URL handoff are covered
- Advisory decision: continue

## Checkpoint Update

- Current todo: Implement Task 3: URL classification and SSRF protection
- Active slice: Task 3 URL safety
- Completed todos:
- Task 1: service scaffold and safe health configuration
- Task 2: canonical persistence and migration integrity
- Evidence refs:
- Task 2 controller verification: 16 tests warning-strict, ruff, SQLite Alembic upgrade/current/downgrade
- Blocked on: none
- Next step: Commit Task 2 then dispatch URL safety implementer

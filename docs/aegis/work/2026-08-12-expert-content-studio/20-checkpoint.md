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

## DriftCheckDraft

- Scope status: Task 3 URL guard only; no source connector or HTTP API introduced
- Compatibility status: HTTPS public targets only; DNS/private redirects rejected before next outbound request; caller cannot override client safety policy
- Retirement status: No legacy fetch path exists; DNS IP pinning intentionally deferred outside approved task
- New risk signals:
- Future connector must use SafeHttpClient for all remote fetches; no direct httpx route around guard
- Advisory decision: continue

## Checkpoint Update

- Current todo: Implement Task 4: normalized connector contract and generic web extraction
- Active slice: Task 4 connector contract and web extraction
- Completed todos:
- Task 1: service scaffold and safe health configuration
- Task 2: canonical persistence and migration integrity
- Task 3: URL classification and SSRF protection
- Evidence refs:
- Task 3: controller verified 20 focused and 36 full warning-strict tests
- Blocked on: none
- Next step: Commit Task 3 and dispatch generic web connector implementer

## DriftCheckDraft

- Scope status: Task 4 generic web contract/router/extraction only; no source API, persistence service, AI or frontend added
- Compatibility status: All generic remote retrieval requires SafeHttpClient.get_public; output records are status-aware and JSON-shaped immutable source records
- Retirement status: No legacy direct HTTP connector path exists; in-buffer size guard remains explicitly limited until a shared streaming client task
- New risk signals:
- Future platform connectors must implement the shared NormalizedSource contract and cannot use raw httpx clients
- Advisory decision: continue

## Checkpoint Update

- Current todo: Implement Task 5: GitHub, arXiv and Hugging Face connectors
- Active slice: Task 5 structured platform connectors
- Completed todos:
- Task 1: service scaffold and safe health configuration
- Task 2: canonical persistence and migration integrity
- Task 3: URL classification and SSRF protection
- Task 4: generic normalized connector contract and web extraction
- Evidence refs:
- Task 4 controller verified: 25 connector tests and 61 full warning-strict tests
- Blocked on: none
- Next step: Commit Task 4 then dispatch structured platform connector implementer

## DriftCheckDraft

- Scope status: Task 5 plus design-required SafeHttpClient rate limiter; no Task6/API/persistence/frontend work added
- Compatibility status: Public connectors use get_public, direct unsafe inputs nonreflective, all response bodies policy-checked, GitHub token server-only, rate limit preserves rate_limited reason
- Retirement status: No direct HTTP connector path or duplicate response policy remains; generic Web now shares policy
- New risk signals:
- Responses are still buffered by SafeHttpClient before connector size check; a streaming transport cap is deferred as documented
- Advisory decision: continue

## Checkpoint Update

- Current todo: Implement Task 6: constrained YouTube and X source handling
- Active slice: Task 6 YouTube and X access boundaries
- Completed todos:
- Task 1: service scaffold and safe health configuration
- Task 2: canonical persistence and migration integrity
- Task 3: URL classification, SSRF protection and rate limits
- Task 4: generic normalized connector contract and web extraction
- Task 5: GitHub, arXiv and Hugging Face connectors
- Evidence refs:
- Task 5 controller verification: 105 targeted and 118 full warning-strict tests
- Blocked on: none
- Next step: Commit Task5 and rate limiter changes, then dispatch Task6 implementer

## DriftCheckDraft

- Scope status: Task 6 constrained YouTube/X connectors only; no API/persistence/AI/frontend work added
- Compatibility status: No captions/no X credentials yield empty metadata-only states; v2 text only with SecretStr; safe timedtext parsing denies DTD/entity content
- Retirement status: No scraping/fabricated transcript path exists; parser accepts only declared legacy transcript MIME/root
- New risk signals:
- X access and captions remain external-platform dependent; user credentials/availability determine ready vs partial/blocked
- Advisory decision: continue

## Checkpoint Update

- Current todo: Implement Task 7: persisted import and knowledge-library API
- Active slice: Task 7 persistence-backed import and library API
- Completed todos:
- Task 1: service scaffold and safe health configuration
- Task 2: canonical persistence and migration integrity
- Task 3: URL classification, SSRF protection and rate limits
- Task 4: generic normalized connector contract and web extraction
- Task 5: GitHub, arXiv and Hugging Face connectors
- Task 6: constrained YouTube and X source handling
- Evidence refs:
- Task 6 controller verification: 53 focused, 123 connector and 171 full warning-strict tests
- Blocked on: none
- Next step: Commit Task6 then dispatch knowledge API implementer

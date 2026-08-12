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

## DriftCheckDraft

- Scope status: Task 7 complete within approved scope; review added production pool/lifecycle regressions only.
- Compatibility status: API contracts and prior connector behavior preserved.
- Retirement status: Proceed to Task 8 after committing Task 7.
- New risk signals:
- No unretired Task 7 risk.
- Advisory decision: continue

## Checkpoint Update

- Current todo: Implement Task 8: AI adapter, source derivations, grounded chat, and settings APIs
- Active slice: Task 8
- Completed todos:
- Tasks 1-7 complete: foundation, persistence/migrations, URL safety, all connectors, persisted import and knowledge APIs
- Evidence refs:
- task7-green
- Blocked on: none
- Next step: Dispatch Task 8 implementer, then specification and quality reviews.

## DriftCheckDraft

- Scope status: Task 8 complete within approved AI derivation and source-grounded chat scope; reviews added safety budgets and cleanup semantics.
- Compatibility status: OpenAI-compatible contract retained; provider credentials remain server-only and optional.
- Retirement status: Proceed to Task 9 client scaffold after Task 8 commit.
- New risk signals:
- No unretired Task 8 finding; production provider requires user-configured credentials.
- Advisory decision: continue

## Checkpoint Update

- Current todo: Implement Task 9: typed React client and API contract
- Active slice: Task 9
- Completed todos:
- Tasks 1-8 complete: foundation, persistence, SSRF safety, all source connectors, library APIs, and AI derivation/chat/settings APIs
- Evidence refs:
- task8-green
- Blocked on: none
- Next step: Read frontend builder guidance; dispatch Task 9 client scaffold implementer, then reviews.

## DriftCheckDraft

- Scope status: Task 9 client scaffold complete within approved API boundary; extra guards harden malformed response handling.
- Compatibility status: Browser uses only public VITE API base URL and same-origin FastAPI contract; no credentials exposed.
- Retirement status: Proceed to Task 10 three-pane workspace after committing Task 9.
- New risk signals:
- No unretired Task 9 finding.
- Advisory decision: continue

## Checkpoint Update

- Current todo: Implement Task 10: functional three-pane knowledge studio
- Active slice: Task 10
- Completed todos:
- Tasks 1-9 complete: backend service/import/AI pipeline and hardened typed React client
- Evidence refs:
- task9-green
- Blocked on: none
- Next step: Implement three-pane workspace using generated desktop/mobile design baselines, then visual and code reviews.

## DriftCheckDraft

- Scope status: Task 10 complete within planned three-pane studio scope; extra repairs cover async selection and full modal/mobile focus behavior.
- Compatibility status: Typed same-origin API client, append-only edit route and raw source immutability preserved.
- Retirement status: Proceed to Task 11 source chat and export UX after commit.
- New risk signals:
- No unretired Task 10 finding; local real import correctly surfaces platform partial content state.
- Advisory decision: continue

## Checkpoint Update

- Current todo: Implement Task 11: source-scoped chat, Markdown preview/export, and mobile quality
- Active slice: Task 11
- Completed todos:
- Tasks 1-10 complete: full backend import/AI pipeline, hardened client, and functional accessible three-pane studio
- Evidence refs:
- task10-green
- Blocked on: none
- Next step: Implement chat/preview/export client components, then complete desktop and 390px visual QA.

## DriftCheckDraft

- Scope status: Task 11 complete within planned chat/export/mobile scope; review repairs hardened markdown ownership, settings ordering, accessibility and visual contrast.
- Compatibility status: Only non-secret settings are exposed; browser third-party image fetches are blocked; API/source/AI contracts preserved.
- Retirement status: Proceed to Task 12 operations documentation, Compose and end-to-end verification after commit.
- New risk signals:
- No unretired Task 11 finding; provider-backed derivations remain correctly configuration-dependent.
- Advisory decision: continue

## Checkpoint Update

- Current todo: Implement Task 12: runtime documentation, Docker Compose, and end-to-end QA
- Active slice: Task 12
- Completed todos:
- Tasks 1-11 complete: secure source imports, persistence, AI derivation/chat, responsive accessible three-pane client, safe rendering/export, and settings UX
- Evidence refs:
- task11-green
- Blocked on: none
- Next step: Dispatch Task 12 implementer, then run Docker and documented end-to-end workflow verification.

## DriftCheckDraft

- Scope status: Task 12 complete within docs/Compose/e2e scope; container launch evidence limited only by absent Docker runtime.
- Compatibility status: Local-only Compose ports, named PostgreSQL volume and Nginx same-origin /api proxy preserve deployment contracts.
- Retirement status: All implementation tasks complete; final integration and verification handoff next.
- New risk signals:
- External environment limitation: Docker CLI/daemon unavailable, so docker compose up --build must be run on a Docker-enabled host.
- Advisory decision: continue

## Checkpoint Update

- Current todo: Integrate verified feature branch and hand off complete Expert Content Studio
- Active slice: Final integration
- Completed todos:
- Tasks 1-12 complete: secure sources, persistence, AI, responsive studio, safe chat/export/settings, operations docs, Compose and end-to-end API workflow
- Evidence refs:
- task12-green
- Blocked on: none
- Next step: Commit Task 12, fast-forward main branch after final status review, report verification and Docker runtime limitation.

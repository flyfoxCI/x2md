# Public deployment login and session security - Checkpoint

- Task ID: 2026-08-18-public-login-security
- Current todo: Write approved implementation plan and establish strict-TDD red tests.
- Active slice: Authentication design and planning
- Blocked on: none
- Next step: Read writing-plans and subagent-driven-development guidance, then create an executable plan.

## Checkpoint Update

- Current todo: Task 1: password/session persistence core
- Active slice: Strict-TDD auth core and migration
- Completed todos:
- none
- Evidence refs:
- baseline-green
- Blocked on: none
- Next step: Dispatch Task 1 implementation agent with isolated context packet.

## DriftCheckDraft

- Scope status: Baseline is clean; active scope is only Task 1 auth core/configuration/schema.
- Compatibility status: Existing API payloads and unauthenticated health route are unchanged at this slice.
- Retirement status: No runtime route changed yet; unauthenticated knowledge access retires in Task 2.
- New risk signals:
- Auth enabled by default means existing non-auth API fixtures must be explicitly isolated in the later HTTP slice.
- Advisory decision: continue

## Checkpoint Update

- Current todo: Task 2: auth HTTP routes, bootstrap lifecycle and API enforcement
- Active slice: Strict-TDD FastAPI auth endpoints and protected knowledge routes
- Completed todos:
- Task 1: Argon2 password/session persistence core, 0002 migration and concurrency hardening
- Evidence refs:
- task1-green
- Blocked on: none
- Next step: Dispatch a fresh Task 2 implementation agent using the verified AuthService contract.

## DriftCheckDraft

- Scope status: Task 1 completed within password/session persistence and migration scope; Task 2 is the approved HTTP policy slice.
- Compatibility status: Health remains public; legacy API payloads are unchanged until authenticated; test fixture isolation will be explicit.
- Retirement status: Unauthenticated knowledge access remains present only until Task 2 replaces it with route-level dependencies.
- New risk signals:
- AuthService use in dependencies must not retain request DB sessions during slow connector or provider I/O.
- Advisory decision: continue

## Checkpoint Update

- Current todo: Task 3: typed browser session and CSRF transport
- Active slice: Strict-TDD React API authentication transport
- Completed todos:
- Task 1 core persistence/concurrency hardening; Task 2 public auth HTTP routes, bootstrap lifecycle and protected legacy API policy
- Evidence refs:
- task2-green
- Blocked on: none
- Next step: Dispatch a fresh Task 3 frontend transport agent.

## DriftCheckDraft

- Scope status: Tasks 1 and 2 completed within approved authentication design; Task 3 is the typed browser transport slice only.
- Compatibility status: Existing authenticated payloads remain stable; health stays public; browser will continue same-origin API use.
- Retirement status: Unauthenticated backend knowledge access retired; frontend still lacks login gate until Task 4.
- New risk signals:
- Frontend must avoid local/session storage and clear stale in-memory CSRF after 401.
- Advisory decision: continue

## Checkpoint Update

- Current todo: Task 4: gate the React studio and add administrator account flows
- Active slice: Strict-TDD React authentication experience
- Completed todos:
- Task 1 core persistence/concurrency hardening; Task 2 public auth HTTP routes, bootstrap lifecycle and protected legacy API policy; Task 3 typed browser session/CSRF transport and stale-response hardening
- Evidence refs:
- task3-green
- Blocked on: none
- Next step: Dispatch a fresh Task 4 frontend UI implementation agent.

## DriftCheckDraft

- Scope status: Tasks 1-3 completed within the approved design; Task 4 is only the login gate, account dialog, header actions and responsive styles.
- Compatibility status: Authenticated data payloads and health remain stable; the UI will defer protected loading until session restoration succeeds.
- Retirement status: Unauthenticated browser access to studio content is retired by the API and will now be removed from the root render path.
- New risk signals:
- invalid_credentials retains an active session; only current-generation authentication_required may clear UI state.
- Advisory decision: continue

## Checkpoint Update

- Current todo: Task 5: document bootstrap secret and public HTTPS deployment
- Active slice: Bounded operator configuration and API documentation
- Completed todos:
- Task 1 core persistence/concurrency hardening; Task 2 public auth HTTP routes, bootstrap lifecycle and protected legacy API policy; Task 3 typed browser session/CSRF transport and stale-response hardening; Task 4 login-gated studio and accessible administrator account flows
- Evidence refs:
- task4-green
- Blocked on: none
- Next step: Dispatch Task 5 deployment documentation agent.

## DriftCheckDraft

- Scope status: Tasks 1-4 are complete; Task 5 is only environment, Compose, README and API documentation.
- Compatibility status: The UI now blocks protected loading until authentication; deployment docs must align with the typed secure defaults and same-origin proxy.
- Retirement status: Unauthenticated browser rendering and API knowledge access are retired; health remains the public operational probe.
- New risk signals:
- App.tsx reached 681 lines; no refactor is authorized in the docs slice, but future auth UI work should extract the studio container.
- Advisory decision: continue

## Checkpoint Update

- Current todo: Task 6: final integration evidence and independent handoff review
- Active slice: Fresh whole-branch security verification and browser smoke
- Completed todos:
- Task 1 core persistence/concurrency hardening; Task 2 public auth HTTP routes, bootstrap lifecycle and protected legacy API policy; Task 3 typed browser session/CSRF transport and stale-response hardening; Task 4 login-gated studio and accessible administrator account flows; Task 5 bootstrap, HTTPS and API deployment documentation
- Evidence refs:
- task5-green
- Blocked on: none
- Next step: Run full backend/frontend verification, static Compose check, and local authenticated browser smoke; then dispatch final independent reviews.

## DriftCheckDraft

- Scope status: Implementation and operations slices are complete; only final whole-branch verification and handoff review remain.
- Compatibility status: All protected browser/API entry points are authenticated; final verification must prove this against the integrated branch.
- Retirement status: Unauthenticated knowledge access and unauthenticated studio rendering remain retired; health is the only public probe.
- New risk signals:
- Docker CLI is unavailable; record static Compose validation only unless the environment changes.
- Advisory decision: needs-verification

# Implementation Plan — Public deployment login and session security

**Goal:** Make Expert Content Studio a private Internet-deployable, single-administrator application. The first administrator is created from a deployment-only environment secret; opaque database sessions and CSRF protect every existing knowledge endpoint.

**Architecture:** AuthService owns Argon2id password hashing, bootstrap, random opaque sessions and revocation. FastAPI dependencies apply session/CSRF policy; React’s typed API module owns same-origin cookie and in-memory CSRF handling. Migration 0002 adds only authentication tables.

**Tech stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, Pydantic Settings, pwdlib[argon2], pytest/httpx; React 19, TypeScript, Vite, Vitest, Testing Library; Docker Compose/Nginx.

**Baseline / Authority Refs:**

- [Approved authentication design](../specs/2026-08-18-public-login-security-design.md).
- [Original product design](../specs/2026-08-11-expert-content-studio-design.md), whose authentication non-goal is now superseded.
- Existing backend bootstrap/router/test fixture and frontend App.tsx/API/header styles as named below.

**Compatibility Boundary:** /api/health stays public and unchanged. Authenticated knowledge requests/responses stay unchanged. Anonymous library routes return 401 authentication_required; unsafe calls without matching CSRF return 403 csrf_invalid. No password or raw session value enters persistence, response, logs, client storage or source control. This remains a single-administrator instance with no registration or tenancy.

**Verification:** Strict TDD: each task starts with a focused test observed failing before production edits, then goes green. The final suite runs backend warning-strict pytest/Ruff, frontend lint/test/build, migration checks, Compose configuration and a real browser login journey.

## Plan basis

### Facts, assumptions and ripple triage

- The API currently has unauthenticated imports/sources/artifacts/settings routers, with tests using isolated SQLite api_harness instances.
- Docker runs Alembic before Uvicorn; app_lifespan is the only legitimate bootstrap owner. Frontend browser traffic is same-origin through Nginx and no permissive CORS exists.
- Public deployment must terminate HTTPS; local native/Compose HTTP will explicitly set AUTH_COOKIE_SECURE=false.
- Auth routes produce a cookie, CSRF token and safe user metadata. Dependency/carrier consumers are every current API route and the root React bootstrap. Integration tests must cover both endpoints and one real authenticated import/library path.

### File map and architecture integrity

| Owner | Files |
| --- | --- |
| Auth domain core | backend/app/services/auth.py; backend/app/{config,models}.py; backend/pyproject.toml; backend/alembic/versions/0002_add_authentication.py |
| Runtime/API enforcement | backend/app/main.py, backend/app/schemas.py, backend/app/api/{auth,dependencies,imports,sources,artifacts,settings}.py |
| Backend evidence | backend/tests/test_auth.py, backend/tests/api/test_auth.py, existing lifecycle/e2e fixture tests |
| Browser transport | frontend/src/{types,api}.ts, frontend/src/api.test.ts |
| Browser experience | frontend/src/App.tsx, frontend/src/components/{LoginScreen,AccountDialog,AppHeader}.tsx, tests and frontend/src/styles/app.css |
| Operations | .env.example, docker-compose.yml, README.md, docs/api.md |

- **Invariant:** AuthService is the only password/token primitive owner; dependencies, rather than route bodies or frontend visibility, enforce policy.
- **Retirement:** unauthenticated access to knowledge routers ends. /api/health and /api/auth/* are the sole public API surface; AUTH_ENABLED=false is explicit fixture/local-only configuration.
- **Plan-time complexity:** App.tsx is already 483 lines, so it retains only checking|anonymous|authenticated gate state. Dedicated login/account components own form/focus state. main.py only composes lifecycle/router owners; crypto is not added there.
- **Verdict:** add one service owner and two small UI components, without JWT, client storage, identity-provider adapter or per-route duplicated guards.

## Tasks

### 1. Create the test-driven password/session persistence core

**Files:** modify backend/pyproject.toml, backend/uv.lock, backend/app/config.py, backend/app/models.py, backend/tests/test_models.py; create backend/app/services/auth.py, backend/tests/test_auth.py, backend/alembic/versions/0002_add_authentication.py.

**Why / boundary:** persistence must support revocable sessions before HTTP routes exist. The migration creates users and auth_sessions; it never seeds a password.

**Required contracts:**

~~~
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    singleton_marker: Mapped[str] = mapped_column(String(32), unique=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("singleton_marker = 'administrator'"),)

class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
~~~

AuthService receives a session and deterministic now input. It uses PasswordHash.recommended(), secrets.token_urlsafe(32), sha256(raw_token).hexdigest(), and hmac.compare_digest. It exposes bootstrap, authenticate, current-session, create/revoke and change-password operations. The fixed singleton marker has database `CHECK` plus `UNIQUE` enforcement, so concurrent empty-database bootstraps with different names can only create one administrator; an insert loser re-reads the marker winner. Settings default to enabled authentication, default admin, 12-hour bounded TTL, and secure cookie; blank bootstrap secret only fails startup on an empty enabled database.

**Verification:**

~~~
cd backend
uv run pytest tests/test_auth.py tests/test_models.py -q -W error
uv run alembic upgrade head
uv run alembic current
uv run alembic downgrade -1
uv run alembic upgrade head
uv run ruff check app tests
~~~

- [ ] Write failing tests: Argon2 verifies but plaintext never persists; bootstrap is idempotent and rejects empty seed; database stores digest rather than raw token; expiry/revocation and old-password-required rotation work; unique username/session foreign key hold.
- [ ] Run the focused pytest command and observe failures because the models/service are absent, not fixture mistakes.
- [ ] Add the locked dependency, settings, models/relationships, service, indexes and reversible migration; no literal password appears in code, migration or test assertions.
- [ ] Re-run the listed focused pytest, migration round-trip and Ruff commands until green.
- [ ] Commit feat(auth): add administrator session core.

### 2. Add auth HTTP routes, lifecycle bootstrap and universal API policy

**Files:** modify backend/app/main.py, backend/app/schemas.py, backend/app/api/dependencies.py, existing four router files, backend/tests/api/conftest.py, backend/tests/api/test_lifecycle.py, backend/tests/api/test_e2e_workflow.py; create backend/app/api/auth.py, backend/tests/api/test_auth.py.

**Why / boundary:** route handlers translate safe typed contracts; dependencies enforce session and CSRF across all legacy endpoints. Tests deliberately set auth_enabled=False only in api_harness; dedicated tests use enabled auth and lifespan.

**Required contracts:**

~~~
# success body
{"user": {"id": 1, "username": "admin"}, "csrfToken": "random-value"}

# public routes
POST /api/auth/login
GET  /api/auth/me
POST /api/auth/logout
POST /api/auth/change-password
~~~

Login sets a cookie with httponly=True, secure=settings.auth_cookie_secure, samesite="strict", path="/" and bounded max_age; logout clears the same cookie. Login failure for nonexistent/wrong username and wrong password is the identical 401 invalid_credentials envelope. Existing routers are included with Depends(require_authenticated_user); their POST/PATCH declarations additionally have Depends(require_csrf). Health remains public. Password change validates current password, revokes all sessions and returns a fresh current session/cookie.

**Verification:**

~~~
cd backend
uv run pytest tests/api/test_auth.py tests/api/test_e2e_workflow.py tests/api/test_lifecycle.py -q -W error
uv run pytest -q -W error
uv run ruff check .
~~~

- [ ] Write failing lifespan/API tests: empty enabled database fails bootstrap; environment seed creates exactly one user; cookie flags/me/login error equality; anonymous GET/POST knowledge calls reject; missing/mismatched CSRF rejects every write; valid CSRF succeeds; logout invalidates; password rotation revokes a second session.
- [ ] Run the focused command and observe those new tests fail before routes/dependencies are added.
- [ ] Implement typed auth request/response schemas, router, cookie helper, lifecycle seed and dependencies. Attach policy at router inclusion/declaration, preserving connector and AI request-session ownership.
- [ ] Re-run focused and full backend/Ruff commands; confirm cleanup after normal and failed lifespan paths.
- [ ] Commit feat(auth): protect knowledge APIs with sessions.

### 3. Add typed browser auth transport and CSRF discipline

**Files:** modify frontend/src/types.ts, frontend/src/api.ts, frontend/src/api.test.ts.

**Why / boundary:** every browser request must have one auditable source for credentials and CSRF. No UI component writes tokens or manually constructs headers.

**Required client interface:**

~~~
export interface AuthenticatedSession {
  user: AuthenticatedUser;
  csrfToken: string;
}
export function getCurrentSession(signal?: AbortSignal): Promise<AuthenticatedSession>;
export function login(username: string, password: string): Promise<AuthenticatedSession>;
export function logout(): Promise<void>;
export function changePassword(currentPassword: string, newPassword: string): Promise<AuthenticatedSession>;
export function clearAuthentication(): void;
~~~

All fetches set credentials: "same-origin". A module-local CSRF value is installed only from guarded login/me/change-password payloads, cleared by logout or a current-generation `401 authentication_required`, and sent as X-CSRF-Token only for non-GET/HEAD/OPTIONS requests. `401 invalid_credentials` retains an otherwise active session; delayed reads and errors may not override or clear a newer credential generation.

**Verification:**

~~~
cd frontend
npm run test -- --run src/api.test.ts
npm run lint
~~~

- [ ] Write failing API tests for response guards, same-origin credentials, login request body, unsafe-header attachment, safe read omission, logout clearing and 401 clearing before a later unsafe call.
- [ ] Run the focused Vitest target; absent exports/header assumptions must fail.
- [ ] Add types, guarded auth calls and central request changes while retaining existing invalid-response/AbortSignal handling and adding no browser persistence.
- [ ] Re-run focused Vitest and lint; inspect mocked fetch calls for exact header scope.
- [ ] Commit feat(web): add secure session API client.

### 4. Gate React data loading and build login/account flows

**Files:** modify frontend/src/App.tsx, frontend/src/App.test.tsx, frontend/src/components/AppHeader.tsx, frontend/src/styles/app.css; create frontend/src/components/LoginScreen.tsx, frontend/src/components/LoginScreen.test.tsx, frontend/src/components/AccountDialog.tsx, frontend/src/components/AccountDialog.test.tsx.

**Why / boundary:** a real UI must not fetch or flash knowledge data before session restoration, and must let the owner immediately replace the bootstrap password.

- App calls /auth/me first. It renders a non-data checking state, then LoginScreen on authentication-required, and starts the existing source/settings effects only when authenticated. A current-generation `401 authentication_required` clears auth UI state and returns to login; invalid credentials from a login/password form do not discard an active session.
- LoginScreen accepts onLogin(username, password), uses labelled autocomplete username/current-password inputs, focuses username and renders only generic errors.
- AccountDialog owns current/new/confirm input state, validates confirmation and 12-character minimum locally, restores trigger focus, invokes logout/change-password callbacks and never echoes credentials.
- AppHeader receives safe user metadata and account/logout actions; mobile retains a reachable account action.

**Verification:**

~~~
cd frontend
npm run test -- --run src/components/LoginScreen.test.tsx src/components/AccountDialog.test.tsx src/App.test.tsx
npm run lint
npm run build
~~~

- [ ] Write failing tests: no sources/settings call until /me authenticates; generic failed login; successful login loads library; account username/logout; validation mismatch/minimum; password change; later 401 returns to login without studio content.
- [ ] Run the focused Vitest command and observe failures before components/gate exist.
- [ ] Add focused components and responsive CSS; refactor only root auth orchestration, use abortable async effects to avoid stale login races, retain existing studio/editor state semantics after sign-in.
- [ ] Re-run focused plus all frontend lint/test/build; perform desktop and 390px manual focus/layout pass.
- [ ] Commit feat(web): gate studio behind administrator login.

### 5. Document secret bootstrap and public HTTPS deployment

**Files:** modify .env.example, docker-compose.yml, README.md, docs/api.md.

**Why / boundary:** operators must not accidentally deploy a public hard-coded password or an HTTPS-only cookie over HTTP.

- .env.example has empty values only: AUTH_INITIAL_ADMIN_USERNAME=admin, AUTH_INITIAL_ADMIN_PASSWORD=, relevant TTL/enabled/cookie options with secure production guidance.
- Compose remains loopback-local and assigns AUTH_COOKIE_SECURE=false only to its HTTP example; no password is in Compose/image/migration.
- README describes first-start secret injection, startup failure on an empty DB without it, immediate rotation/removal, HTTPS AUTH_COOKIE_SECURE=true, same-origin proxy and upstream IP login-rate-limit requirement.
- API docs insert public auth route bodies, cookie/CSRF usage, and 401 authentication_required, 401 invalid_credentials, 403 csrf_invalid before legacy route descriptions.

**Verification:**

~~~
docker compose config --quiet
rg -n --hidden --glob '!backend/uv.lock' --glob '!frontend/package-lock.json' 'AUTH_INITIAL_ADMIN_PASSWORD=.*[^=[:space:]]' .env.example docker-compose.yml README.md docs backend frontend
rg -n 'password_hash|token_hash|csrfToken|authentication_required|csrf_invalid' docs/api.md README.md backend frontend
~~~

- [ ] Capture the current missing-auth configuration/API-documentation evidence with the two rg checks.
- [ ] Treat that evidence as RED; do not add an example password to make it pass.
- [ ] Apply the bounded docs/Compose changes above.
- [ ] Run docker compose config --quiet and both checks; read back doc snippets against typed runtime settings without printing rendered secret-bearing configuration.
- [ ] Commit docs: document secure public login deployment.

### 6. Independent review, integration evidence and branch handoff

**Files:** update docs/aegis/work/2026-08-18-public-login-security/{20-checkpoint,90-evidence,99-reflection}.md and helper JSON artifacts. Repair production code only when independent review identifies a valid finding.

**Why / boundary:** authentication crosses every data/public boundary, so individual agent green reports are insufficient.

**Verification:**

~~~
cd backend && uv lock --check && uv run pytest -q -W error && uv run ruff check .
cd ../frontend && npm run lint && npm run test -- --run && npm run build
cd .. && docker compose config --quiet
python /Users/jerry/.codex/aegis/scripts/aegis-workspace.py bundle --root /Users/jerry/code/x2md --work 2026-08-18-public-login-security
python /Users/jerry/.codex/aegis/scripts/aegis-workspace.py check --root /Users/jerry/code/x2md
~~~

- [ ] Dispatch an independent spec reviewer with the approved design, this plan, diff and green evidence. Require findings-first checks of public route inventory, bootstrap secrecy, cookie/CSRF flags, all legacy policy boundaries, migration and non-goals.
- [ ] Repair every valid Important/Critical finding through a new failing test, then re-review to clean.
- [ ] Dispatch an independent code-quality/security reviewer. Require findings-first review of timing/error equality, session ownership/revocation, response/log secrecy, dependency coverage, focus/responsive state and docs/runtime drift; repair/re-review valid Important/Critical findings.
- [ ] Run every listed command plus browser smoke: seed → login → one library call → logout rejected call → change password → old session rejected, at desktop and 390px. Record any unavailable Docker/browser runtime rather than claiming it passed.
- [ ] Update checkpoints/evidence/drift, inspect complexity/diff, commit verified work, then use finishing-a-development-branch for user-directed branch integration.

## Risks, retirement and ADR signal

| Risk | Mitigation |
| --- | --- |
| Public default password | no source literal; empty initial secret; empty DB fails closed |
| DB compromise | Argon2id for passwords; raw session only in HttpOnly cookie; database digest/expiry/revocation |
| CSRF | SameSite Strict plus per-session server-bound token on every unsafe route |
| Forgotten legacy guard | explicit router inventory, anonymous tests, independent search/review |
| Browser persistence | one module-memory token owner; review excludes local/session storage |
| Incorrect HTTPS deployment | secure default, deliberate local override, TLS docs and Compose loopback |
| Bootstrap cannot be rotated | account dialog requires current password and revokes all sessions |

- **Retired:** implicit-private unauthenticated knowledge API access.
- **Retained:** public health and test/local AUTH_ENABLED=false; the latter is not a public deployment option.
- **Future trigger:** a second user requires an explicit ownership/tenant migration plan.
- **ADR Backfill:** run at completion. Expected action is skip, because the approved dated design and this plan document the durable owner/contract decision unless implementation diverges.

## Plan self-review

Every approved requirement maps to Tasks 1–6: secure bootstrap, hashing/session data, cookie/CSRF, all API enforcement, client/UI state, operations, review and final evidence. The tasks name concrete files, red/green commands, no fallback path and the public compatibility boundary. No implementation placeholder or second identity abstraction remains.

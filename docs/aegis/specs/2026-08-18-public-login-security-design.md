# Public deployment login and session security — Design Spec

**Status:** Approved for unattended execution under the user's explicit autonomous-delivery instruction  
**Date:** 2026-08-18  
**ArchitectureReviewRequired:** yes

## Intent and scope

The existing Expert Content Studio was deliberately designed as a local single-user service. The user now needs to deploy it publicly without exposing the knowledge library. This spec supersedes the earlier design's "authentication deferred" non-goal for one bounded capability: one administrator account, password login, and browser-session protection.

### TaskIntentDraft

- **Outcome:** a public-facing installation refuses all knowledge API access until the administrator signs in; first deployment creates that administrator from deployment-only environment variables.
- **Success evidence:** a fresh migrated database starts only when an initial administrator password is supplied; correct login establishes a protected session; anonymous, expired, logged-out, and CSRF-invalid calls cannot read or change knowledge data; the React app presents login, logout, restore-session, and password-change flows.
- **Stop condition:** backend migration/API tests, frontend interaction/API tests, and documented deployment verification cover the entire initial-login-to-library journey.
- **Non-goals:** user registration, email verification/recovery, multi-factor authentication, SSO/OIDC, multi-user ownership or sharing, role management, and data tenancy. This remains a private single-administrator instance.

### BaselineReadSetHint

- `docs/aegis/specs/2026-08-11-expert-content-studio-design.md` (original single-user architecture and explicitly deferred auth)
- `backend/app/{main,config,models,db}.py`, `backend/app/api/*.py`, `backend/tests/api/conftest.py`
- `frontend/src/{App,api,types}.ts(x)`, `frontend/src/styles/*.css`
- `.env.example`, `docker-compose.yml`, `frontend/nginx.conf`, `README.md`, `docs/api.md`
- OWASP password, session, authentication, and CSRF guidance; FastAPI response-cookie documentation; pwdlib's Argon2 recommendation.

### ImpactStatementDraft

- **Affected layers:** runtime configuration, SQL schema and Alembic, FastAPI dependencies/routes, every existing knowledge API route, the typed React API client and root state, deploy configuration and operating documentation.
- **Invariant:** passwords and raw session identifiers never enter application responses, logs, settings storage, browser storage, or source control. Only a random session cookie authenticates requests; every state-changing request additionally proves same-origin intent with a server-bound CSRF value.
- **Compatibility:** the existing `/api/health` endpoint stays public for container checks. Existing knowledge routes retain their payloads when authenticated, but now return `401 authentication_required` when anonymous and `403 csrf_invalid` for an unauthorised write intent. Test fixtures explicitly disable auth; production defaults it on.

## Options considered

| Option | Advantages | Rejected trade-off |
| --- | --- | --- |
| Signed self-contained cookie / JWT | Fewer database queries | Revocation, logout and invalidating every existing session after a password change require a blacklist or extra state; it also encourages browser token handling. |
| External identity provider | Mature SSO/MFA possibilities | Requires an issuer, callback configuration and user decisions that are outside the requested private-instance scope. |
| **Database-backed opaque sessions (chosen)** | Logout and password-change revocation are authoritative; the browser never sees a persistent bearer token; works with the existing relational database | Adds two small tables and a request-scoped lookup. |

## First-principles and architecture review

**First Principle:** an Internet-reachable knowledge library must disclose or mutate nothing unless a real administrator session authorizes the request.

**Non-negotiables:** no hard-coded public password; secret password handling uses a slow adaptive hash; cookie identifiers are unguessable and never stored raw server-side; CSRF is checked separately from cookie authentication; default runtime behaviour is fail-closed.

**Assumptions to drop:** a local single-user UI is private merely because it lacks a navigation link; an HttpOnly cookie alone prevents forged state changes; a JWT is inherently simpler for a single-node service.

**Smallest sufficient path:** one non-registering administrator table plus opaque persisted sessions; no identity-provider abstraction or frontend token store.

### Decision hygiene review

**Canonical owners:**

| Concern | Canonical owner | Explicit boundary |
| --- | --- | --- |
| Password hashing, bootstrap, login, session creation/revocation | `backend/app/services/auth.py` | Routes and dependencies never implement cryptography or token construction. |
| Runtime policy/cookie configuration | `backend/app/config.py` | Environment-only settings; no secret persisted in `app_settings`. |
| SQL persistence | `User` and `AuthSession` models plus migration `0002` | `token_hash`, never raw session values, is persisted. |
| API enforcement | authentication and CSRF dependencies in `backend/app/api/dependencies.py` | Protected routers require authentication; unsafe route declarations also require CSRF. |
| Browser session state | `frontend/src/api.ts` plus the root React authentication state | Cookie is sent with `credentials: same-origin`; CSRF token remains in memory only. |

**Retirement:** the prior unauthenticated knowledge API is retired. `/api/health` and `/api/auth/*` are the only intentional unauthenticated API surface. No compatibility bypass is retained in production; `AUTH_ENABLED=false` exists solely as an explicit test-only/local-development setting.

**Falsifiers:** a route that can access `/api/sources`, `/api/imports`, `/api/artifacts`, or `/api/settings` without `require_authenticated_user`, or a POST/PATCH path that accepts no matching CSRF token, invalidates the design. A raw password or raw session token present in a database row, API response, log assertion, `.env.example`, or client persistence also invalidates it.

**Verdict:** adopt database-backed opaque sessions. The new service is a clear owner rather than a caller-side guard, and has no parallel compatibility path.

## Data and bootstrap design

```text
User
  id, username (unique), password_hash, is_active, created_at, updated_at

AuthSession
  id, user_id -> users.id, token_hash (unique), csrf_token,
  expires_at, created_at, updated_at
```

- `password_hash` is created and verified with `pwdlib[argon2]` using its recommended Argon2id configuration. Passwords never use SHA-256, encryption, or reversible storage.
- Login issues a cryptographically random, opaque token. The HTTP cookie carries the raw value; the database stores only its SHA-256 digest, which is appropriate for a high-entropy bearer secret rather than a user password.
- A session receives a separate random CSRF value. The login and `GET /api/auth/me` response return it to the SPA; it is held only in module memory and supplied as `X-CSRF-Token` on `POST`, `PATCH`, `PUT`, or `DELETE` API calls.
- Session expiry is absolute, configurable, and enforced server-side. Logging out deletes the active database session. A password change verifies the current password, changes its Argon2id hash, revokes every old session, and issues exactly one fresh session to the current browser.
- At application lifespan startup, after migrations have created the table, no-user databases seed one account only if `AUTH_INITIAL_ADMIN_PASSWORD` is non-empty. `AUTH_INITIAL_ADMIN_USERNAME` defaults to `admin`. If there is no user and no seed password, startup fails closed with an operator-only configuration error. Once an account exists, the bootstrap password is ignored, so it can be removed from deployment secrets.

## HTTP and browser contract

Public endpoints:

| Route | Behaviour |
| --- | --- |
| `GET /api/health` | Remains public and contains no account state or secrets. |
| `POST /api/auth/login` | Takes `username` + `password`; response contains safe user metadata and a transient `csrfToken`, and sets the session cookie. Any invalid credential gets the same `401 invalid_credentials` envelope. |
| `GET /api/auth/me` | Returns the active username and a replacement/access current `csrfToken`, or `401 authentication_required`. |
| `POST /api/auth/logout` | Requires current session plus CSRF token, removes the server session and clears the cookie. |
| `POST /api/auth/change-password` | Requires current session plus CSRF; takes `currentPassword` and a minimum-12-character `newPassword`, rotates password and sessions. |

All existing `/api/imports`, `/api/sources`, `/api/artifacts`, and `/api/settings` endpoints become authentication-required. All existing read payloads remain unchanged after authentication. Existing state-changing endpoints require `X-CSRF-Token`; the Markdown download is read-only and requires only the session.

The cookie has `HttpOnly`, `SameSite=Strict`, `Path=/`, no `Domain`, a bounded `Max-Age`, and `Secure=true` by default. Public deployment must terminate HTTPS before serving the app. Native HTTP development and the local Compose example explicitly set `AUTH_COOKIE_SECURE=false`; that setting is not suitable for a public hostname. The browser uses same-origin requests only and does not write credential values to `localStorage`, `sessionStorage`, IndexedDB, URL query strings, or React persisted state.

The server intentionally does not enable permissive CORS. Public production uses the frontend's same-origin Nginx proxy. An upstream edge/proxy should additionally rate-limit `POST /api/auth/login` by client IP; this deployment responsibility is documented rather than trusting client-supplied forwarding headers in application code.

## Runtime configuration

| Environment variable | Production default / requirement | Purpose |
| --- | --- | --- |
| `AUTH_ENABLED` | `true` | Fail closed on all knowledge APIs. `false` is test/local-only. |
| `AUTH_INITIAL_ADMIN_USERNAME` | `admin` | First-bootstrap username; validated and not browser-configurable. |
| `AUTH_INITIAL_ADMIN_PASSWORD` | required only while no user exists | Deployment secret used exactly to seed first database. Never committed. |
| `AUTH_SESSION_TTL_SECONDS` | `43200` | Absolute session lifetime, bounded by typed settings validation. |
| `AUTH_COOKIE_SECURE` | `true` | Requires HTTPS for public traffic. Local development deliberately overrides it. |

## React experience

1. On initial application load, call `GET /api/auth/me` before any library/settings request.
2. If it returns `401`, render an accessible focused login view; do not mount the studio or issue protected loading calls.
3. Successful login saves only user metadata and the transient CSRF token in memory, then loads the existing studio.
4. Any later `401` clears in-memory authentication state and returns to login. Logout sends CSRF, clears local state and relies on the response to clear the HttpOnly cookie.
5. The header exposes the active administrator and an account dialog with current/new/confirm password fields. It shows generic safe errors and never echoes a password.

## Testing and acceptance

Strict TDD applies: each slice begins with a focused test observed failing before production implementation.

Backend coverage must prove:

1. fresh bootstrap creates exactly the configured administrator and never stores plaintext;
2. blank bootstrap password prevents startup of an otherwise empty database;
3. wrong username and wrong password get indistinguishable `401` results;
4. login uses the required cookie flags, session digest persistence, expiry, and `GET /me` shape;
5. every existing knowledge route rejects an anonymous caller, and its writes reject absent/mismatched CSRF;
6. logout invalidates the cookie/session; changing a password requires the old password, invalidates another session, and permits a fresh/current session only;
7. migration upgrade/downgrade is valid for SQLite and PostgreSQL dialect checks; the API fixture can deliberately disable authentication without leaking this configuration to production.

Frontend coverage must prove typed login and session guards, same-origin credential options, CSRF header attachment to unsafe calls only, login-gated initial render, logout/session-expiry recovery, and password-change validation. Full regression includes all existing backend/frontend suites, type/lint/build checks, migration checks, static Compose configuration, and a browser pass at desktop and mobile widths.

## Deployment boundaries and deferred work

- First public deployment requires an HTTPS reverse proxy and a strong unique `AUTH_INITIAL_ADMIN_PASSWORD` supplied as a secret. The first successful startup creates `admin` (or the configured username); immediately rotate/remove the bootstrap value after verifying login.
- This is a private single-administrator instance. Adding a second account later requires an explicit user-ownership migration before library data can be safely shared; it is not a hidden registration feature.
- Password recovery, MFA/SSO, email verification, audit/event retention, per-IP durable throttling, and enterprise proxy trust policy are deliberately deferred. The docs require edge login throttling for Internet exposure.

## Sources

- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [FastAPI response-cookie documentation](https://fastapi.tiangolo.com/advanced/response-cookies/)
- [pwdlib Argon2 recommendation](https://pypi.org/project/pwdlib/)

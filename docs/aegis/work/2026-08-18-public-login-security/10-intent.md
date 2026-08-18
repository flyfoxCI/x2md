# Public deployment login and session security - Intent

## TaskIntentDraft

- Requested outcome: Protect public knowledge APIs with a seeded administrator login and secure browser sessions.
- Goal: Deliver a fail-closed, single-administrator password login that protects every knowledge-library API and supports public HTTPS deployment.
- Success evidence:
- Fresh DB bootstrap, protected-route, CSRF, logout/password-rotation, frontend login, and deployment configuration evidence all pass.
- Stop condition: Done only after all authenticated flows and regressions pass; blocked if a required security boundary cannot be verified.
- Non-goals:
- Registration, SSO, MFA, password reset, multi-user tenancy.
- Scope: Backend auth persistence/API enforcement, frontend login/session UX, migration, environment and deployment documentation.
- Change kinds:
- security
- Risk hints:
- Passwords, bearer-session handling, public API access and migration contracts are security-sensitive.

## BaselineReadSetHint

- docs/aegis/specs/2026-08-11-expert-content-studio-design.md

## ImpactStatementDraft

- Compatibility boundary: Health stays public; authenticated route payloads stay stable.
- Affected layers:
- configuration, persistence, API, React client, operations
- Owners:
- AuthService and auth API dependencies
- Invariants:
- No knowledge API leaks data without a valid session; no raw password or session token persists server-side.
- Non-goals:
- Registration, SSO, MFA, password reset, multi-user tenancy.

These records are Method Pack drafts / hints, not authoritative runtime decisions.

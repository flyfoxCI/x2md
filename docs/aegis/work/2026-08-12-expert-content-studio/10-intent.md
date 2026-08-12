# Expert Content Studio implementation - Intent

## TaskIntentDraft

- Requested outcome: Build the approved full-stack expert content studio
- Goal: Implement and verify the single-user source-to-knowledge-to-Skill workflow
- Success evidence:
- Supported public imports persist; configured AI derivations work; UI supports import, edit, search, chat and export
- Stop condition: Done when all planned tasks and acceptance verification pass; otherwise preserve a checkpoint with blockers
- Non-goals:
- Accounts, billing, private-source access, bypassing platform restrictions, vector search and background jobs
- Scope: React frontend, FastAPI backend, connectors, AI adapter, SQLite/PostgreSQL persistence and local runtime documentation
- Change kinds:
- feature
- Risk hints:
- Platform access limits, SSRF safety and provider configuration must remain explicit

## BaselineReadSetHint

- docs/aegis/specs/2026-08-11-expert-content-studio-design.md
- docs/aegis/plans/2026-08-11-expert-content-studio.md

## ImpactStatementDraft

- Compatibility boundary: OpenAI-compatible AI configuration and structured source-restriction status
- Affected layers:
- frontend
- backend
- connectors
- persistence
- Owners:
- FastAPI owns remote retrieval, source records and AI calls; React owns presentation state
- Invariants:
- No secret in browser; raw sources are immutable; only public safe URLs are fetched
- Non-goals:
- Accounts, billing, private-source access, bypassing platform restrictions, vector search and background jobs

These records are Method Pack drafts / hints, not authoritative runtime decisions.

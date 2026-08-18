# Public deployment login and session security - Evidence

No evidence has been recorded yet.

## EvidenceBundleDraft

- Artifact key: baseline-green
- Type: command
- Source: worktree baseline
- Summary: Backend: uv lock --check, pytest -q -W error (216 passed), Ruff passed. Frontend: lint, Vitest (61 passed), build passed.
- Verifier: controller

## EvidenceBundleDraft

- Artifact key: task1-green
- Type: command
- Source: Task 1 core commits 70ec4a2, 8794ed8, 93ceed8, 22e71fd
- Summary: Focused auth/model suite 37 passed; five repeated concurrent initializer regressions passed; Ruff, uv lock, and SQLite Alembic upgrade/current/downgrade/upgrade passed. Spec and quality reviews approved after concurrency repairs.
- Verifier: controller plus independent reviewers

## EvidenceBundleDraft

- Artifact key: task2-green
- Type: command
- Source: Task 2 commits bc934fe and 2a713ad
- Summary: Focused auth/core/API/lifecycle suite 38 passed; full backend suite 251 passed; Ruff, uv lock, SQLite Alembic upgrade/downgrade/upgrade and independent spec/quality reviews passed. API race regressions cover old-password delayed login and revoked-session CSRF recheck.
- Verifier: controller plus independent reviewers

## EvidenceBundleDraft

- Artifact key: task3-green
- Type: command and independent review
- Source: Task 3 commits 01d68b1,b62b82a,02aad8e,9e53ed1,173b07f
- Summary: RED reproduced stale /auth/me overwriting new login CSRF; GREEN guards installs by intent and credential generation. Focused API 43, full frontend 86, lint, build and diff check passed; two independent reviews approved.
- Verifier: controller plus independent reviewers

# Implementation Plan — Expert Content Studio

**Goal:** Deliver a locally runnable single-user service that imports supported public URLs, persists canonical source material, generates AI-derived Chinese knowledge and Skill Markdown through a configured OpenAI-compatible endpoint, and exposes the flow through a responsive three-pane React workspace.

**Architecture:** React + TypeScript client; FastAPI + SQLAlchemy service; SQLite by default and PostgreSQL through `DATABASE_URL`; typed connector router; one server-only OpenAI-compatible adapter.

**Tech stack:** Python 3.12, uv, FastAPI, SQLAlchemy, Alembic, Pydantic Settings, httpx, BeautifulSoup/readability, pytest; React, TypeScript, Vite, Vitest, React Testing Library, `react-markdown`, Lucide icons and CSS modules/variables.

**Baseline / authority refs:**

- Approved [design spec](../specs/2026-08-11-expert-content-studio-design.md).
- The initial workspace has no maintained source files. `docs/aegis/` contains the only governing project artifacts.

**Compatibility boundary:** keep provider keys server-only; keep raw imported source immutable; preserve an OpenAI-compatible AI-provider contract; accurately surface source restrictions; reject internal/private URL targets before any outbound request. No client-side source/vendor calls, browser scraping, or fake AI responses.

**Verification:** run focused backend/frontend tests after each slice, then `pytest -q`, `npm run test -- --run`, `npm run build`, `docker compose up --build`, and manual browser checks for import, derivation, editing, library search, download and narrow viewport layout.

## Plan basis

### Facts, assumptions and unknowns

- **Fact:** Python 3.12.9, Node 24.7.0, npm 11.5.1 and uv 0.6.12 are installed locally.
- **Fact:** an OpenAI-compatible provider and an X API token are not present yet; their absence must be a tested state.
- **Assumption:** public GitHub repositories, Hugging Face cards, arXiv records and ordinary HTTPS articles are representative import fixtures.
- **Unknown:** exact production hosting and model provider. The configuration contract isolates both from application logic.

### File map

| Area | Files | Ownership |
| --- | --- | --- |
| Service bootstrap | `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/db.py` | runtime configuration, application lifecycle and database session. |
| Persistence | `backend/app/models.py`, `backend/app/schemas.py`, `backend/alembic/**` | canonical source and append-only artifact representation. |
| URL guard | `backend/app/services/url_safety.py`, `backend/tests/test_url_safety.py` | validation before connector dispatch. |
| Connector router | `backend/app/services/connectors/{base,router,web,github,arxiv,huggingface,youtube,x}.py` and connector tests | normalized public-source retrieval. |
| Knowledge API | `backend/app/api/{imports,sources,artifacts,settings}.py`, `backend/app/services/knowledge.py` | HTTP contract and persisted workflow. |
| AI boundary | `backend/app/services/ai.py`, `backend/tests/test_ai.py` | provider calls, prompts and citation-bound answers. |
| Client bootstrap/API | `frontend/package.json`, `frontend/vite.config.ts`, `frontend/src/{main,App,api,types}.ts(x)` | API consumption and root state. |
| Client workspace | `frontend/src/components/*.tsx`, `frontend/src/styles/*.css`, tests | three panes, working controls and responsive visual system. |
| Operations | `.env.example`, `docker-compose.yml`, `README.md`, `docs/api.md` | local configuration and deployment handoff. |

### Architecture integrity lens

- **Invariant:** `Source` and outbound fetching live behind the FastAPI connector/knowledge boundaries; React only renders and edits returned state.
- **Canonical contract:** every connector produces `NormalizedSource`; every derivation produces versioned `Artifact` rows.
- **Overlap to avoid:** never add URL parsing to route handlers or individual React components; never allow an artifact save to update raw-source fields.
- **Higher-level path:** one `ConnectorRouter` and `AIService` reduce platform/model branching while allowing clean unit tests.
- **Retirement / falsifier:** the synchronous import path is the only initial path. When request duration/retry evidence requires it, replace it with a formal job queue rather than request-local retry branches.
- **Verdict:** proceed; no historical implementation needs retirement because this is a greenfield workspace.

### Plan pressure and complexity checks

- **Owner / contract / retirement:** all new owners are named in the file map; no compatibility carrier is planned.
- **Verification scope:** service unit/API tests, client interaction tests, build and browser flow checks cover the main acceptance evidence.
- **Task executability:** each task includes files, a red test, the minimum implementation, a green check and an isolated commit.
- **Pressure result:** proceed.
- **Target size / shape:** all source owners are new. Keep API files limited to HTTP translation, connectors under 200 lines when feasible, and split platform clients rather than accumulating conditionals in `router.py`.
- **Better file boundary:** add owner files; do not create a generic `utils.py` or a client-side platform adapter.

## Tasks

### 1. Scaffold the service and prove health configuration

**Files:** create `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/tests/conftest.py`, `backend/tests/test_health.py`.

**Why:** establishes a repeatable server/test command and a non-secret configuration boundary before feature code exists.

**Impact / compatibility:** only `APP_*`, `DATABASE_URL`, `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`, `X_BEARER_TOKEN` names are allowed in configuration. `GET /api/health` reports booleans/status only and never serializes a secret.

**Verification:** from `backend`, `uv run pytest tests/test_health.py -q` prints `1 passed`; `uv run uvicorn app.main:app --port 8000` allows `curl -fsS http://127.0.0.1:8000/api/health`.

- [ ] Write `test_health_hides_provider_secret` using `TestClient`, set `AI_API_KEY=test-secret`, and assert a `200` health payload does not contain `test-secret`.
- [ ] Run `cd backend && uv run pytest tests/test_health.py -q`; confirm collection fails because `app.main` does not yet exist.
- [ ] Add `Settings(BaseSettings)` with typed defaults, an app factory and `GET /api/health` returning `{\"status\": \"ok\", \"database\": \"uninitialized\", \"aiConfigured\": bool(settings.ai_api_key)}`; declare FastAPI, Pydantic Settings, SQLAlchemy, Alembic, httpx, pytest and pytest-asyncio dependencies in `pyproject.toml`.
- [ ] Re-run `cd backend && uv run pytest tests/test_health.py -q`; confirm the focused test passes, then run `uv run ruff check .`.
- [ ] Commit `chore(backend): scaffold FastAPI service and safe health endpoint`.

### 2. Create canonical persistence and migration ownership

**Files:** create `backend/app/db.py`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_initial_schema.py`, `backend/tests/test_models.py`; modify `backend/app/main.py`.

**Why:** source provenance and artifact history must survive process restart before import/AI behavior is built.

**Impact / compatibility:** `Source` raw fields are never writable through artifact paths; `Artifact.parent_artifact_id` supports version lineage. Use JSON columns/types that work on SQLite and PostgreSQL.

**Verification:** `cd backend && uv run pytest tests/test_models.py -q` prints `2 passed`; `uv run alembic upgrade head` creates the tables in the configured database.

- [ ] Write tests that persist a `Source` and two `Artifact` records, then assert artifacts retain their source id and a user edit cannot change `Source.raw_text`.
- [ ] Run `cd backend && uv run pytest tests/test_models.py -q`; confirm failure before model/session implementation.
- [ ] Implement SQLAlchemy declarative models, session dependency, Pydantic read/create schemas and the explicit initial Alembic migration for `sources`, `artifacts`, `knowledge_notes`, `chat_turns` and `app_settings`.
- [ ] Run `cd backend && uv run alembic upgrade head && uv run pytest tests/test_models.py -q`; confirm migration and model tests pass.
- [ ] Commit `feat(data): add immutable sources and versioned artifacts`.

### 3. Implement URL classification and SSRF protection first

**Files:** create `backend/app/services/url_safety.py`, `backend/tests/test_url_safety.py`.

**Why:** every connector relies on one safe, deterministic decision about which public resource may be fetched.

**Impact / compatibility:** accept only `https` URLs; reject credentials, localhost, loopback, unspecified, multicast, link-local and RFC1918 IPv4/IPv6 addresses both in literals and DNS results. Redirect targets must be revalidated by the request wrapper.

**Verification:** `cd backend && uv run pytest tests/test_url_safety.py -q` prints `8 passed` (or more) and does not make a network request for rejected values.

- [ ] Write parametrized tests covering `https://example.com/a`, `http://example.com`, `https://localhost`, `https://127.0.0.1`, `https://10.0.0.2`, `https://[::1]`, user-info URLs and a mocked DNS resolution to `192.168.1.1`.
- [ ] Run `cd backend && uv run pytest tests/test_url_safety.py -q`; confirm failure because `validate_public_url` is absent.
- [ ] Implement `validate_public_url(url) -> URL` and `SafeHttpClient` with finite timeout, `follow_redirects=False`, hostname resolution and a `validate_redirect` helper; give every rejection an `unsafe_url` detail.
- [ ] Re-run `cd backend && uv run pytest tests/test_url_safety.py -q && uv run ruff check app/services/url_safety.py`; confirm all guard tests pass.
- [ ] Commit `feat(security): guard URL imports against private network access`.

### 4. Define the normalized connector contract and generic web extraction

**Files:** create `backend/app/services/connectors/{__init__,base,router,web}.py`, `backend/tests/connectors/test_web.py`, `backend/tests/fixtures/article.html`.

**Why:** a stable normalized output allows the API, storage and AI pipeline to remain independent from platform payload formats.

**Impact / compatibility:** `NormalizedSource` includes canonical URL, platform, title, optional author/date, Markdown/text, metadata and explicit `ready|partial|blocked` status. The generic connector may only use the safe client.

**Verification:** `cd backend && uv run pytest tests/connectors/test_web.py -q` parses the local fixture title/body and removes navigation/script noise.

- [ ] Write a mocked-http test importing `article.html`, expecting platform `web`, title `Reasoning at Scale`, readable paragraphs, canonical URL and no navigation text.
- [ ] Run `cd backend && uv run pytest tests/connectors/test_web.py -q`; confirm red because `WebConnector` does not exist.
- [ ] Add frozen `NormalizedSource` and `Connector` protocol in `base.py`, `ConnectorRouter`, and `WebConnector` using BeautifulSoup/readability with byte/MIME limits through `SafeHttpClient`.
- [ ] Run `cd backend && uv run pytest tests/connectors/test_web.py -q && uv run ruff check app/services/connectors`; confirm fixture extraction is green.
- [ ] Commit `feat(import): normalize generic public articles`.

### 5. Add explicit GitHub, arXiv and Hugging Face connectors

**Files:** create `backend/app/services/connectors/{github,arxiv,huggingface}.py`, `backend/tests/connectors/{test_github,test_arxiv,test_huggingface}.py`, JSON/XML fixture files.

**Why:** these services expose structured public metadata and are the highest-confidence expert-content sources.

**Impact / compatibility:** no platform logic enters route handlers. GitHub requires public repos only and uses a token solely as an optional server setting. arXiv stores abstract-level content; Hugging Face stores card/model/dataset metadata.

**Verification:** `cd backend && uv run pytest tests/connectors -q` confirms every platform emits the common `NormalizedSource` contract and unsupported forms return `blocked`/`partial`, not a crash.

- [ ] Write mocked API-fixture tests for a GitHub README, arXiv Atom record and Hugging Face model card, asserting platform, title, source text, canonical URL and metadata provenance.
- [ ] Run `cd backend && uv run pytest tests/connectors/test_github.py tests/connectors/test_arxiv.py tests/connectors/test_huggingface.py -q`; confirm failure because the three connector modules are absent.
- [ ] Implement the three connectors and register hostname/path predicates with `ConnectorRouter`; use the safe client and return explicit partial/blocked explanations for unsupported/private resources.
- [ ] Run `cd backend && uv run pytest tests/connectors -q`; confirm generic and platform connector suites pass together.
- [ ] Commit `feat(import): support GitHub arXiv and Hugging Face sources`.

### 6. Add honest YouTube and X source handling

**Files:** create `backend/app/services/connectors/{youtube,x}.py`, `backend/tests/connectors/{test_youtube,test_x}.py`.

**Why:** these sources are required, but availability varies. Their connector responses must make access limits visible rather than inventing material.

**Impact / compatibility:** YouTube uses oEmbed/metadata and transcript only when publicly available. X calls v2 only when the server has `X_BEARER_TOKEN`; absent credentials produce an importable metadata-only `partial` state or a `blocked` state with `provider_not_configured`.

**Verification:** `cd backend && uv run pytest tests/connectors/test_youtube.py tests/connectors/test_x.py -q` proves restricted inputs return a reason without an AI call.

- [ ] Write mocked tests for a captioned YouTube video, a no-caption video, X without credentials and X API `403`, asserting status plus exact non-fabrication reasons.
- [ ] Run `cd backend && uv run pytest tests/connectors/test_youtube.py tests/connectors/test_x.py -q`; confirm red because connectors are absent.
- [ ] Implement metadata/transcript normalization and X credential gating, register their URL classifiers and ensure response text is empty when no source content was legally retrieved.
- [ ] Re-run `cd backend && uv run pytest tests/connectors/test_youtube.py tests/connectors/test_x.py -q && uv run pytest tests/connectors -q`; confirm all connector tests pass.
- [ ] Commit `feat(import): add constrained YouTube and X connectors`.

### 7. Expose the persisted import and knowledge-library API

**Files:** create `backend/app/services/knowledge.py`, `backend/app/api/{__init__,imports,sources,artifacts}.py`, `backend/tests/api/{test_imports,test_sources,test_artifacts}.py`; modify `backend/app/main.py`.

**Why:** turns connectors and persistence into a usable, status-aware product workflow.

**Impact / compatibility:** only `KnowledgeService` writes `Source` or creates user artifacts. `POST /api/imports` is idempotent for a canonical URL unless the user explicitly refreshes in a future feature. All public failures use documented structured error codes.

**Verification:** `cd backend && uv run pytest tests/api -q` passes import, search, detail, version-save and markdown-download tests using a fake connector.

- [ ] Write API tests that inject a fake connector, post an import, search by title/URL, fetch source detail, save an edited artifact and verify a Markdown download response.
- [ ] Run `cd backend && uv run pytest tests/api -q`; confirm failures before routers/service are wired.
- [ ] Add `KnowledgeService`, import/source/artifact routers, dependency injection and a `Content-Disposition` Markdown download endpoint; map connector errors to `422` safe JSON responses.
- [ ] Run `cd backend && uv run pytest tests/api -q && uv run pytest -q`; confirm the full backend suite is green.
- [ ] Commit `feat(api): persist imports and expose the knowledge library`.

### 8. Add the server-only AI derivation and source-scoped chat boundary

**Files:** create `backend/app/services/ai.py`, `backend/app/api/settings.py`, `backend/tests/{test_ai.py,api/test_derivations.py,api/test_chat.py}`; modify `backend/app/api/sources.py`, `backend/app/main.py`.

**Why:** makes translation, distillation and answering real provider-backed operations while preserving source traceability.

**Impact / compatibility:** the adapter takes an OpenAI-compatible base URL/API key/model from settings; no response is generated when unconfigured. Translation, summary and Skill output append new artifacts. Chat citations must point to source/artifact sections provided to the model.

**Verification:** `cd backend && uv run pytest tests/test_ai.py tests/api/test_derivations.py tests/api/test_chat.py -q` uses a mocked OpenAI-compatible response and verifies no provider key appears in an API response.

- [ ] Write unit/API tests for absent-provider `provider_not_configured`, translation/Skill artifact creation, prompt source URL inclusion, citation persistence and source-scoped chat refusing empty source material.
- [ ] Run `cd backend && uv run pytest tests/test_ai.py tests/api/test_derivations.py tests/api/test_chat.py -q`; confirm red before `AIService` exists.
- [ ] Implement `AIService`, three deliberate prompt builders, an `httpx` OpenAI-compatible chat-completions client, derive/chat routes, and non-secret `GET/PATCH /api/settings` presentation settings.
- [ ] Run `cd backend && uv run pytest -q && uv run ruff check .`; confirm backend tests and lint are green.
- [ ] Commit `feat(ai): derive translated knowledge and cited Skills`.

### 9. Scaffold and test the React client/API contract

**Files:** create `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/{main.tsx,App.tsx,api.ts,types.ts}`, `frontend/src/test/setup.ts`, `frontend/src/App.test.tsx`.

**Why:** sets an independently testable client boundary before styling the studio.

**Impact / compatibility:** client API functions mirror documented backend routes; error objects retain backend codes/messages for user-facing states. No API key, fetch-to-source URL or third-party model call is added to browser code.

**Verification:** `cd frontend && npm run test -- --run` passes the root loading/error-state test; `npm run build` emits `dist/` without TypeScript errors.

- [ ] Write a test that mocks `listSources`, renders the app and asserts a library source title is visible; add a second mock returning `provider_not_configured` and assert the configuration state appears.
- [ ] Run `cd frontend && npm run test -- --run`; confirm red because package/source files are absent.
- [ ] Create a Vite React TypeScript setup, typed `api.ts` fetch wrapper, source/artifact DTOs, error normalizer and a root query state that loads `/api/sources`.
- [ ] Run `cd frontend && npm run test -- --run && npm run build`; confirm client unit test and production build pass.
- [ ] Commit `feat(web): establish typed client API boundary`.

### 10. Build the functional three-pane studio

**Files:** create `frontend/src/components/{AppHeader,KnowledgeSidebar,EditorWorkspace,PreviewPanel,ImportDialog,StatusMessage}.tsx`, `frontend/src/styles/{tokens,app,workspace}.css`, `frontend/src/components/EditorWorkspace.test.tsx`; modify `frontend/src/App.tsx`.

**Why:** delivers the reference-informed workflow in which users can import, inspect, derive, edit, preview and export actual persisted knowledge.

**Impact / compatibility:** controls call the typed client API and show lifecycle state. Tabs never overwrite source data, saves create user artifacts, preview renders current Markdown safely, and download uses the returned artifact URL.

**Verification:** `cd frontend && npm run test -- --run` covers import submission, artifact tab selection, Save, error state and markdown preview; `npm run build` passes.

- [ ] Write component tests with mocked API methods: submit a GitHub URL, show loading then saved source, switch Original/Chinese/Skill tabs, save an edit and display an import/AI restriction banner.
- [ ] Run `cd frontend && npm run test -- --run`; confirm red because studio components are absent.
- [ ] Implement the header URL workflow, searchable sidebar, tabbed editable Markdown center pane and question/preview right pane with status states, theme tokens, keyboard-accessible controls and responsive CSS grid collapse.
- [ ] Run `cd frontend && npm run test -- --run && npm run build`; confirm interaction tests and build are green.
- [ ] Commit `feat(web): deliver interactive three-pane knowledge studio`.

### 11. Add AI interactions, Markdown export and mobile quality checks

**Files:** create `frontend/src/components/{KnowledgeChat,MarkdownPreview}.tsx`, `frontend/src/components/KnowledgeChat.test.tsx`; modify `frontend/src/components/{EditorWorkspace,PreviewPanel}.tsx` and workspace CSS.

**Why:** completes the visible transformation from source link into queryable, reusable knowledge and Skill files.

**Impact / compatibility:** chat invokes the source-scoped endpoint and renders its citations; preview uses sanitized Markdown rendering; export downloads the current artifact. Desktop/mobile controls cannot be inert.

**Verification:** `cd frontend && npm run test -- --run` passes chat citation and download-link tests; browser QA at 1440px and 390px shows no clipped primary interface.

- [ ] Write tests that submit a question and assert a cited answer, choose “Distilled Skill”, and assert the download link targets `/api/artifacts/{id}/download`.
- [ ] Run `cd frontend && npm run test -- --run`; confirm red because chat/preview actions are absent.
- [ ] Implement source-scoped chat, renderer/preview themes, download action, device mode switch and narrow-screen layout rules using CSS media queries and focus-visible styles.
- [ ] Run `cd frontend && npm run test -- --run && npm run build`; confirm all client tests and build pass.
- [ ] Commit `feat(web): add cited chat preview and Skill export`.

### 12. Document runtime configuration, compose services and run end-to-end QA

**Files:** create `.env.example`, `docker-compose.yml`, `README.md`, `docs/api.md`, `backend/tests/api/test_e2e_workflow.py`; modify `backend/pyproject.toml` only if test extras are needed.

**Why:** makes the complete service runnable by a new developer and records credential-dependent behavior honestly.

**Impact / compatibility:** `.env.example` contains variable names and blank values only; it identifies X/AI credentials as optional and never includes a real key. Compose mounts a named database volume and exposes the frontend/backend only on local development ports.

**Verification:** `docker compose up --build` starts both services; `curl -fsS http://localhost:8000/api/health` returns `status: ok`; browser QA verifies the end-to-end happy path with a local fake AI provider or configured compatible provider.

- [ ] Write an end-to-end API test using a fixture connector/provider that imports content, derives translation and Skill, saves an edit, searches the library and downloads Markdown.
- [ ] Run `cd backend && uv run pytest tests/api/test_e2e_workflow.py -q`; confirm red before the workflow fixture/support wiring is complete.
- [ ] Add configuration documentation, compose definitions, endpoint reference and a minimal environment template describing required/optional variables and X/YouTube limitations.
- [ ] Run `cd backend && uv run pytest -q && uv run ruff check .`; then `cd ../frontend && npm run test -- --run && npm run build`; finally `docker compose up --build` and the documented curl/browser smoke path.
- [ ] Commit `docs: document local deployment and validate full knowledge workflow`.

## Risks and retirement

| Risk | Control | Trigger for redesign |
| --- | --- | --- |
| Remote platforms restrict access | return structured partial/blocked status; document credential needs | repeated production failures require an approved supported-provider integration, not a scraper workaround. |
| Long imports outgrow HTTP timeout | strict response limits and explicit error state | measured timeout/retry demand requires an owned queue/job model. |
| Provider behavior/quality varies | OpenAI-compatible adapter, persisted metadata and conservative prompts | a provider requires a non-compatible protocol, which warrants a new adapter contract. |
| SQLite deployment concurrency | make `DATABASE_URL` portable from first migration | concurrent write errors or multi-user requirement requires PostgreSQL migration guidance. |
| Source text is sensitive/copyrighted | public-only fetch, provenance and no bypass; user controls storage/export | requests for private source access, bulk crawling or redistribution require a separate policy decision. |

**ADR signal:** the canonical source/derived-artifact split, server-only connector/AI boundaries, and synchronous-import retirement trigger are durable decisions. At completion, evaluate whether observed implementation evidence warrants an ADR backfill.

## Plan self-review

- Every approved design section maps to one or more tasks: safety (3), sources (4–6), persistence/API (2, 7), AI (8), UI (9–11), operations and validation (12).
- No placeholders remain; each task defines concrete files, red/green commands and commit boundary.
- Models, connector output and API clients share the `Source`/`Artifact` contract declared by the design spec.
- No compatibility fallback or duplicate source owner is planned. Synchronous import has an explicit retirement signal rather than hidden retry behavior.
- New files have narrow ownership and no file has existing size pressure. The plan tests provider absence, platform restriction and SSRF rejection in addition to happy paths.


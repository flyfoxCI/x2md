# 深度研究知识库实施计划

## Goal

实现已批准的深度研究知识库：GitHub、arXiv 和 Hugging Face 公开材料会被有界地采集为证据，持久化研究任务生成可引用的中文研究档案和可解释的层级标签，并支持手动或自动触发。

## Architecture

新增 `ResearchOrchestrator` 作为证据采集、预算、状态机、AI 研究笔记、报告引用和标签建议的唯一 owner。已有 connector 继续负责初始轻量导入；已有 `AIService` 继续是唯一模型供应商边界；研究工作在数据库持久队列中的单 worker 内执行。`Source` 保持不可变，研究报告是 `Artifact(kind="research")`，证据、引文和标签使用专属关系表。

## Tech Stack

Python 3.12、FastAPI、SQLAlchemy 2、Alembic、httpx、Pydantic、`pypdf`、pytest；React 19、TypeScript、Vite、Vitest 和 Testing Library。

## Baseline / Authority Refs

- `docs/aegis/specs/2026-08-23-deep-research-knowledge-base-design.md`
- `docs/aegis/specs/2026-08-11-expert-content-studio-design.md`
- `docs/aegis/BASELINE-GOVERNANCE.md`
- `README.md` 与 `docs/api.md`

## Compatibility Boundary

- `Source.raw_text`、`Source.source_markdown` 和历史 Artifact 永不被研究任务重写。
- 现有导入、翻译、摘要、Skill、聊天、编辑和下载端点保持行为与响应字段兼容；研究相关字段只追加。
- 浏览器不调用外部平台或 AI 供应商，不接收任何密钥、内部路径或底层网络错误。
- 旧 `KnowledgeNote.tags_json` 迁移为已确认自定义标签；之后 `GET /api/sources?tag=` 的真相来源是 `TagAssignment`。

## Verification

```sh
cd backend
uv run pytest -q -W error
uv run ruff check .

cd ../frontend
npm run lint
npm run test -- --run
npm run build

cd ..
docker compose config
```

## Scope Check

### Facts, assumptions and unknowns

- **Fact:** 当前 GitHub、arXiv 和 Hugging Face connector 仅保存轻量材料；`AIService` 的上下文上限为 24,000 字符；导入目前在请求内同步完成。
- **Fact:** 当前 schema 仅有 `Source`、`Artifact`、`KnowledgeNote`、`ChatTurn` 和 `AppSetting`；当前前端只认识 translation/summary/skill/user_edit Artifact。
- **Assumption:** 单后端实例、单 worker 足以服务首期本地/单用户产品。由持久租约防止进程重启后丢失任务，但不承诺多 worker 并发。
- **Assumption:** `pypdf` 能从大多数有文本层的公开 arXiv PDF 中提取页级文本；无文本层的 PDF 以 `partial` 处理而不引入 OCR。
- **Unknown:** 用户真实仓库和 PDF 的分布尚未测量。首期按已批准预算执行，并把覆盖不足作为后续调优证据而非无界扩容理由。

### Ripple Signal Triage

研究功能会影响 schema、迁移、source 导入、source 查询、应用生命周期、设置、API 类型和编辑器/侧栏 UI。计划把这些调用方统一收敛到研究服务、研究路由和前端研究 hook，避免在现有 connector/router、`KnowledgeService` 或 `App.tsx` 中复制状态机。

### Architecture Integrity Lens

- **Invariant:** 每一个报告引文和每一个 AI 标签建议都只指向同一 `ResearchRun` 中保存的 `ResearchEvidence`。
- **Canonical owner / contract:** `services/research/orchestrator.py` 运行状态机；`services/research/collectors/` 只产出有界采集结果；`AIService` 只执行提供证据的模型调用。
- **Responsibility overlap:** `summary` Artifact 不承担研究报告；`KnowledgeNote.tags_json` 不继续参与标签检索；前端不派生任务状态。
- **Higher-level simplification:** 一个持久 `ResearchRun` 合同供手动、自动、轮询和未来独立 worker 共同使用。
- **Retirement / falsifier:** 迁移完成后删除 tag JSON 查询路径；若一个 worker 的队列延迟被测量为不可接受，保留运行表/API 而替换 worker 进程。
- **Verdict:** 按批准设计实施，不新增客户端 fallback 或第二个研究 owner。

### Plan Pressure Test

- **Owner / contract / retirement:** 新 owner、schema 和公开 API 已在规格中明确；旧标签 JSON 查询需要迁移与退休。
- **Architecture integrity / higher-level path:** 研究任务不是对 `derive` 路由的分支扩展，使用专属路由和编排器。
- **Verification scope:** 单元、connector、服务、路由、迁移/恢复、前端交互和既有回归套件均需要覆盖。
- **Task executability:** 采集器按平台独立；存储/编排/API/UI 可在稳定合同后逐步实现。
- **Pressure result:** proceed。

### Plan-Time Complexity Check

- **Target files:** `models.py`（136 行）、`schemas.py`（133 行）、`ai.py`（276 行）、`knowledge.py`（402 行）、`App.tsx`（483 行）、`api.ts`（363 行）。
- **Owner fit:** 扩展 ORM/schema/AI 的既有 owner，但研究状态、采集和轮询不可继续堆入这些文件。
- **Add-in-place risk:** `App.tsx` 与 `KnowledgeService` 已有多个不相关责任；继续增加任务状态会使行为难以验证。
- **Better file boundary:** 新增 `backend/app/services/research/`、`backend/app/api/research.py`、`backend/app/api/tags.py`、`frontend/src/hooks/useResearchRun.ts`、`ResearchPanel.tsx` 和 `TagManager.tsx`。
- **Recommendation:** 在既有模型/API 类型中做最小合同扩展；所有研究行为进入新 owner 文件。

## File Map

| Area | Create | Modify |
| --- | --- | --- |
| Dependencies | — | `backend/pyproject.toml`, `backend/uv.lock` |
| Persistence | `backend/alembic/versions/0002_deep_research.py` | `backend/app/models.py`, `backend/app/schemas.py`, `backend/tests/test_models.py` |
| Research contracts | `backend/app/services/research/{__init__.py,contracts.py,citations.py,orchestrator.py,worker.py,tags.py}` | `backend/app/services/ai.py`, `backend/app/services/knowledge.py` |
| Source collection | `backend/app/services/research/collectors/{__init__.py,base.py,github.py,arxiv.py,huggingface.py,pdf.py}` | `backend/app/services/composition.py`, `backend/app/services/url_safety.py`, `backend/app/services/connectors/response_policy.py` |
| Backend API/lifecycle | `backend/app/api/{research.py,tags.py}` | `backend/app/api/{__init__.py,dependencies.py,imports.py,sources.py,settings.py}`, `backend/app/main.py`, `backend/app/config.py`, `docs/api.md`, `README.md` |
| Backend tests/fixtures | `backend/tests/{services/test_research_citations.py,services/test_research_orchestrator.py,services/test_research_worker.py,services/test_tags.py,connectors/test_research_github.py,connectors/test_research_arxiv.py,connectors/test_research_huggingface.py,api/test_research.py,api/test_tags.py}` and PDF/JSON/Markdown fixtures | `backend/tests/{test_ai.py,test_models.py,api/test_imports.py,api/test_sources.py,api/test_lifecycle.py}` |
| Frontend contract | `frontend/src/hooks/useResearchRun.ts` | `frontend/src/{types.ts,api.ts,api.test.ts,App.tsx}` |
| Frontend UI/tests | `frontend/src/components/{ResearchPanel.tsx,ResearchPanel.test.tsx,TagManager.tsx,TagManager.test.tsx}` | `frontend/src/components/{EditorWorkspace.tsx,EditorWorkspace.test.tsx,KnowledgeSidebar.tsx}`, `frontend/src/{App.test.tsx,styles/workspace.css,styles/app.css}` |

## Tasks

### 1. Add research persistence contracts and a reversible migration

**Files:** modify `backend/pyproject.toml`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/tests/test_models.py`; create `backend/alembic/versions/0002_deep_research.py`; regenerate `backend/uv.lock`.

**Why:** durable runs, evidence, citations and labels are required before a worker can safely resume or a report can prove its claims.

**Impact / compatibility:** add `research` to the Artifact kind without changing old records. Add `Artifact.research_run_id` as nullable. Create `research_runs`, `research_evidence`, `research_citations`, `tag_definitions`, `tag_assignments` and `tag_assignment_evidence` with foreign keys and indexes. Use `JSON` only for budget/coverage/model metadata snapshots; use relational links for evidence and tags. During upgrade, transform every non-empty legacy `KnowledgeNote.tags_json` item into a deduplicated non-system `TagDefinition` with a null facet and an `accepted` user `TagAssignment`; leave the JSON value intact for rollback safety but never query it after this release. Migration downgrade drops only new tables/indexes/column in dependency order.

**Verification:** `cd backend && uv run alembic upgrade head && uv run pytest tests/test_models.py -q && uv run alembic downgrade -1 && uv run alembic upgrade head`.

- [ ] Write model tests that persist a `ResearchRun`, included and excluded evidence, a `research` Artifact/citation, a suggested tag with evidence, and one user-confirmed tag; assert cross-source foreign-key violations fail and only one active run for a source is accepted.
- [ ] Run `cd backend && uv run pytest tests/test_models.py -q`; confirm the new imports/models are absent and tests fail.
- [ ] Add `pypdf>=5,<6` to `backend/pyproject.toml`, run `cd backend && uv lock`, then implement the ORM/Pydantic enums and models with a partial unique index for queued/running runs, unique citation tokens per Artifact, nullable facet for custom tags, tag hierarchy and tag/evidence joins; write migration `0002_deep_research.py` with explicit indexes and the legacy-tag data transform.
- [ ] Run the verification command above and `cd backend && uv run ruff check app/models.py app/schemas.py`; confirm migration round-trip and model tests are green.
- [ ] Commit `feat(data): persist research evidence runs and governed tags`.

### 2. Define research contracts, budgets and citation validation

**Files:** create `backend/app/services/research/{__init__.py,contracts.py,citations.py}` and `backend/tests/services/test_research_citations.py`; modify `backend/app/services/ai.py` and `backend/tests/test_ai.py`.

**Why:** the orchestrator needs a platform-neutral contract that refuses unbounded material and a deterministic verifier before a model report can become a completed Artifact.

**Impact / compatibility:** define immutable collection results with stable locators, included/excluded decisions and fixed budgets: GitHub 20 files/1.5 MiB, arXiv 25 MiB PDF/60 pages/500k characters, Hugging Face 12 files/1 MiB. Extend `AIService` with research-note, report and structured-tag methods; retain derive/chat behavior and source prompt limits.

**Verification:** `cd backend && uv run pytest tests/services/test_research_citations.py tests/test_ai.py -q`.

- [ ] Write citation tests for valid `[E1]`/`[E12]` use, unknown IDs, duplicate tokens, and an uncited non-empty body paragraph under a required report section; write AI tests asserting research prompts label evidence as untrusted data and never expose an API key.
- [ ] Run the focused tests; confirm they fail because research contracts, citation parsing and AI methods do not exist.
- [ ] Implement typed statuses/phases/budgets, locator validation, report-template section validation and `parse_report_citations`; add AI prompt builders that produce one evidence note, a fixed-template report and JSON tag candidates with evidence IDs/confidence.
- [ ] Re-run the focused tests plus `cd backend && uv run ruff check app/services/research app/services/ai.py`; confirm invalid references cannot be accepted.
- [ ] Commit `feat(research): define bounded evidence and citation contracts`.

### 3. Build bounded GitHub research collection

**Files:** create `backend/app/services/research/collectors/{__init__.py,base.py,github.py}` and `backend/tests/connectors/test_research_github.py`; add GitHub tree/ref/file fixtures under `backend/tests/fixtures/`; modify `backend/app/services/composition.py` and `backend/app/services/url_safety.py`.

**Why:** a codebase cannot be studied from README alone; selected source files, dependency manifests and architecture documents must become version-pinned evidence.

**Impact / compatibility:** use only `SafeHttpClient`; capture default-branch commit SHA and recursive tree, select at most 20 text files in documented priority order, preserve excluded paths/reasons, and never download binary/generated/vendor/minified content. Compose the shared client with a 40-per-host/60-second cap while the collector enforces 32 requests per run. Existing connector unit tests keep the constructor default of 20 requests unless composition explicitly overrides it.

**Verification:** `cd backend && uv run pytest tests/connectors/test_research_github.py tests/test_url_safety.py -q`.

- [ ] Write mocked safe-client tests for a repository tree containing README, `pyproject.toml`, entrypoint, architecture document, source modules, binary and vendor paths; assert deterministic selection, commit-aware locators, 20-file/1.5-MiB bounds, excluded reasons and a partial result for a truncated tree.
- [ ] Run the focused suite; confirm red because the research GitHub collector and collector contract are absent.
- [ ] Implement GitHub ref/tree/file fetches, text admission and deterministic ranking in `collectors/github.py`; make request accounting stop before the per-run limit and return coverage rather than a fabricated complete tree.
- [ ] Re-run the focused suite, then `cd backend && uv run pytest tests/connectors/test_github.py -q`; confirm existing initial GitHub import remains unchanged.
- [ ] Commit `feat(research): collect bounded GitHub code evidence`.

### 4. Build arXiv PDF and Hugging Face research collectors

**Files:** create `backend/app/services/research/collectors/{pdf.py,arxiv.py,huggingface.py}`; create `backend/tests/connectors/{test_research_arxiv.py,test_research_huggingface.py}` and small text-PDF/config/source-file fixtures; modify `backend/app/services/connectors/response_policy.py` only to accept an explicit per-call body limit.

**Why:** papers require paginated full-text evidence, while Hub artifacts require configuration and selected small source files instead of model/data blobs.

**Impact / compatibility:** the PDF-only path permits application/pdf up to 25 MiB and extracts at most 60 pages/500k characters without OCR; all other connectors retain the 5 MiB default. Hugging Face reads Hub metadata/card plus a maximum of 12 allowed text/config files and refuses weights/dataset payloads. Each record has version/revision-aware locators and excluded coverage records.

**Verification:** `cd backend && uv run pytest tests/connectors/test_research_arxiv.py tests/connectors/test_research_huggingface.py tests/connectors/test_response_policy.py -q`.

- [ ] Write fixture tests for a two-page text PDF with page/section locators, an encrypted/non-text/over-page PDF partial outcome, a Hugging Face model with `config.json` and source script, and a dataset with a payload file that is excluded without a request.
- [ ] Run the focused suite; confirm red because the collectors and explicit size-limit parameter do not exist.
- [ ] Implement `pdf.py` with bounded `pypdf` extraction, arXiv PDF acquisition keyed to the imported paper version, Hugging Face revision/file selection and the response-policy optional limit while preserving existing defaults.
- [ ] Re-run the focused suite, then run `cd backend && uv run pytest tests/connectors/test_arxiv.py tests/connectors/test_huggingface.py -q`; confirm light-import regressions remain green.
- [ ] Commit `feat(research): collect arXiv and Hub evidence within budgets`.

### 5. Implement the research orchestrator and tag lifecycle

**Files:** create `backend/app/services/research/{orchestrator.py,tags.py}` and `backend/tests/services/{test_research_orchestrator.py,test_tags.py}`; modify `backend/app/services/knowledge.py` and `backend/tests/api/test_knowledge_service.py`.

**Why:** one owner must atomically persist coverage, evidence notes, citation-validated reports and suggested/accepted tags without overwriting raw source material.

**Impact / compatibility:** the orchestrator selects a collector from `Source.platform`, persists every evidence decision, calls the AI in note → report → tag order, accepts only valid citations/tags and sets `completed`, `partial`, `blocked` or `failed` honestly. The tag service is canonical for hierarchy, suggestion confirmation/rejection, custom labels and source search; legacy tag JSON is migrated once and then ignored by queries.

**Verification:** `cd backend && uv run pytest tests/services/test_research_orchestrator.py tests/services/test_tags.py tests/api/test_knowledge_service.py -q`.

- [ ] Write service tests with fake collectors/AI for completed, partial coverage, provider-not-configured, invalid-citation, transient-provider and user-confirmed-tag scenarios; assert report/evidence/tag rows share the run, no `Source` field changes, and re-running does not erase accepted tags.
- [ ] Run the focused tests; confirm red because no orchestrator/tag service exists.
- [ ] Implement transaction boundaries and phase transitions in `orchestrator.py`, use `AIService` only through typed research methods, persist citation/tag joins, and implement tag hierarchy/custom-label operations and `KnowledgeService` accepted-tag search.
- [ ] Re-run the focused suite and `cd backend && uv run pytest tests/api/test_sources.py -q`; confirm old title/URL search and new tag filtering coexist.
- [ ] Commit `feat(research): orchestrate evidence reports and governed tags`.

### 6. Add durable single-worker execution and auto-start settings

**Files:** create `backend/app/services/research/worker.py` and `backend/tests/services/test_research_worker.py`; modify `backend/app/{main.py,config.py}`, `backend/app/api/settings.py`, `backend/app/api/imports.py`, `backend/app/api/dependencies.py`, `backend/tests/{api/test_lifecycle.py,api/test_imports.py}`.

**Why:** automatic and manual research must survive HTTP response completion and process restart rather than relying on a transient request task.

**Impact / compatibility:** add `research.auto_start` with default false and make existing presentation-only PATCH requests valid. Store a lease owner/until and next-attempt time. Lifespan starts exactly one worker when enabled, reclaims expired leases, retries only transient network/provider failures twice, and stops cleanly. Import success for a supported, content-bearing source enqueues a run only when the setting is enabled.

**Verification:** `cd backend && uv run pytest tests/services/test_research_worker.py tests/api/test_lifecycle.py tests/api/test_imports.py -q`.

- [ ] Write clock-controlled tests for atomic claim, expired-lease recovery, two bounded retries, terminal non-retry cases, worker shutdown, default disabled auto-start and enabled auto-start after a supported import.
- [ ] Run the focused tests; confirm red because no worker lease, research settings or enqueue path exists.
- [ ] Implement compare-and-set claiming, polling/backoff and lifespan ownership in `worker.py`/`main.py`; extend settings storage/API and call the enqueue command only after import persistence commits.
- [ ] Re-run the focused suite and `cd backend && uv run pytest tests/api/test_derivations.py -q`; confirm normal derivations do not start research jobs.
- [ ] Commit `feat(research): run durable manual and automatic studies`.

### 7. Expose research and tag API contracts

**Files:** create `backend/app/api/{research.py,tags.py}` and `backend/tests/api/{test_research.py,test_tags.py}`; modify `backend/app/api/{__init__.py,dependencies.py,sources.py}`, `backend/app/schemas.py`, `docs/api.md`.

**Why:** the client needs additive, typed endpoints to start/poll research, inspect evidence and control tag confirmation without inferring database state.

**Impact / compatibility:** implement `POST /api/sources/{id}/research` (202 or active run), `GET /api/research-runs/{id}`, paginated evidence, tag tree, custom-tag creation, tag PATCH/DELETE, and extended source detail. Map only safe error codes. Preserve old source response fields and existing status/error envelopes.

**Verification:** `cd backend && uv run pytest tests/api/test_research.py tests/api/test_tags.py tests/api/test_sources.py -q`.

- [ ] Write API tests for active-run idempotency, manual enqueue, run detail/evidence pagination, unknown run/source, custom tag creation, confirmation/rejection/deletion, inherited tag filtering and appended source-detail fields.
- [ ] Run the focused suite; confirm red because research/tag routers are not registered.
- [ ] Implement Pydantic request/response types, dependencies that assemble the research/tag service, both routers and source-detail extensions; document every new route/status/error code in `docs/api.md`.
- [ ] Re-run the focused suite, then `cd backend && uv run pytest tests/api -q`; confirm no existing API contract regression.
- [ ] Commit `feat(api): expose research runs evidence and tag governance`.

### 8. Wire typed frontend research contracts and polling

**Files:** create `frontend/src/hooks/useResearchRun.ts`; modify `frontend/src/{types.ts,api.ts,api.test.ts,App.tsx,App.test.ts}`.

**Why:** UI state must come from the persisted run contract and must stop polling at terminal states or when the selected source changes.

**Impact / compatibility:** add discriminated DTOs/guards and request functions for research run, evidence, tag and settings contracts. Keep existing API client guards intact. Move research polling out of the already-large `App.tsx` into `useResearchRun`, pass only typed callbacks/data to components, and preserve cancellation behavior.

**Verification:** `cd frontend && npm run test -- --run src/api.test.ts src/App.test.tsx && npm run build`.

- [ ] Write API guard tests for run/evidence/tag responses and hook/App tests for manual start, polling while running, terminal stop, source switch abort and unmount abort.
- [ ] Run the focused tests; confirm red because the DTOs, fetch methods and hook are absent.
- [ ] Implement request functions, response guards and `useResearchRun` with bounded polling, abort controllers and terminal-state cleanup; update `App.tsx` to own selected-source coordination only.
- [ ] Re-run the focused tests and `cd frontend && npm run lint`; confirm type checks and cancellation expectations pass.
- [ ] Commit `feat(web): add typed research run polling`.

### 9. Build research report, evidence and tag interactions

**Files:** create `frontend/src/components/{ResearchPanel.tsx,ResearchPanel.test.tsx,TagManager.tsx,TagManager.test.tsx}`; modify `frontend/src/components/{EditorWorkspace.tsx,EditorWorkspace.test.tsx,KnowledgeSidebar.tsx}`, `frontend/src/{App.tsx,styles/workspace.css,styles/app.css}`.

**Why:** users need to initiate/re-run research, understand coverage and evidence, read the research Artifact, and govern tags without losing the existing three-pane workflow.

**Impact / compatibility:** add a “深度研究” view without changing original/translation/summary/Skill semantics. Render citation tokens as evidence controls only when their IDs exist. Clearly label user-edited research descendants as unvalidated edits. Show accepted and suggested tags by facet; only accepted tags drive sidebar filtering. Preserve keyboard tab behavior and narrow-view focus management.

**Verification:** `cd frontend && npm run test -- --run src/components/ResearchPanel.test.tsx src/components/TagManager.test.tsx src/components/EditorWorkspace.test.tsx && npm run build`.

- [ ] Write component tests for start/active/completed/partial/blocked states, evidence list expansion, valid citation selection, user-edit warning, accepting/rejecting/adding/removing tags and sidebar filtering; include a narrow-viewport focus assertion.
- [ ] Run the focused tests; confirm red because the research panel/tag manager and research tab do not exist.
- [ ] Implement presentational `ResearchPanel` and `TagManager`, integrate typed callbacks into editor/sidebar, add accessible progress/status/citation controls and responsive CSS without embedding data-fetch logic in components.
- [ ] Re-run the focused tests, then `cd frontend && npm run test -- --run && npm run lint && npm run build`; confirm old editing/chat/preview behavior remains green.
- [ ] Commit `feat(web): present evidence-backed research and governed tags`.

### 10. Run cross-layer QA, migrations and product documentation

**Files:** create/extend fixtures for all three research sources; modify `README.md`, `docs/api.md`, `backend/tests/api/test_e2e_workflow.py`, `frontend/src/App.test.tsx` only where end-to-end UI behavior needs coverage.

**Why:** the feature must be usable and honestly documented as a bounded, evidence-backed local research system rather than a best-effort scraper.

**Impact / compatibility:** document defaults, auto-start behavior, material limits, PDF requirement, single-worker deployment limit, error states and non-goals. Do not claim an unsupported distributed worker or full repository/dataset analysis.

**Verification:** run the full commands in the plan header, then start the local stack and perform one GitHub, arXiv and Hugging Face fixture-backed smoke workflow with a mock OpenAI-compatible provider.

- [ ] Write/extend an end-to-end backend test that imports each supported source, starts/executes research with fixture collector/AI, polls to a terminal state, validates citations/tags, edits the report, filters by an accepted tag and asserts raw source immutability.
- [ ] Run `cd backend && uv run pytest tests/api/test_e2e_workflow.py -q`; confirm red until all cross-layer contracts are wired.
- [ ] Update README/API docs with the precise deep-research workflow, bounds, status meaning, source limitations, automatic setting, single-worker constraint and safe failure behavior; add no secret or environment-specific content.
- [ ] Run every command in the plan header, `cd backend && uv run alembic upgrade head`, and the fixture-backed smoke workflow; record exact results in the implementation evidence record.
- [ ] Commit `docs: document evidence-backed deep research workflow`.

## Risks and Retirement

| Risk | Control | Retirement / redesign trigger |
| --- | --- | --- |
| Large or inaccessible materials | fixed per-platform budgets, coverage records and partial states | measured demand for more material requires changing budget configuration through a reviewed spec update |
| Prompt injection in public artifacts | untrusted-data AI prompts, evidence-only completion inputs and citation validator | no client-side source/model processing is introduced |
| Worker crash or duplicate execution | durable lease/attempt/next-attempt fields and one worker per app instance | measured queue delay or multi-instance deployment replaces worker process, not the run contract |
| Tag drift | controlled definitions, source/evidence-backed suggestions, explicit user state | old `KnowledgeNote.tags_json` query path is removed after migration |
| Provider format/quality variance | central `AIService`, strict JSON/tag/citation validation, safe terminal errors | a provider needs a different protocol requires a new adapter behind `AIService` |

## Plan Self-Review

- The ten tasks map to every approved requirement: bounded tri-platform collection, PDF parsing, persistent runs, automatic/manual trigger, evidence-cited reports, governed tags, API, UI, safety and acceptance.
- All new owners, contracts and retirement paths are explicit; no task adds a second research state or a client-side fallback.
- Database/API additions are additive, old artifacts remain immutable, and the legacy tag path has a concrete migration/retirement step.
- Every task starts with a failing test and names a focused green command; the final task runs all backend, frontend, migration and compose validation.
- No placeholder task text or deferred implementation step remains.

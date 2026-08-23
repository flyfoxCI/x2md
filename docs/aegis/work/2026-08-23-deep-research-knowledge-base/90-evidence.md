# 深度研究知识库 — 实施证据

## Baseline

- `cd backend && uv run pytest -q -W error`: 216 passed。
- `cd backend && uv run ruff check .`: passed。
- `cd frontend && npm run test -- --run`: 61 passed。
- `cd frontend && npm run lint`: passed。
- `cd frontend && npm run build`: passed。

## Slice evidence

后续切片将在此追加 RED、GREEN、回归命令与结果。

## 任务 1 — 研究持久化合同与迁移

- RED：`cd backend && uv run pytest tests/test_models.py -q` 在导入缺失的 `ResearchCitation` 时失败，证明测试覆盖了尚不存在的合同。
- GREEN：同一命令通过，`17 passed in 0.48s`。
- 迁移验证：`uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` 成功。
- 静态验证：`uv run ruff check app/models.py app/schemas.py alembic/versions/0002_deep_research.py` 通过。
- 证据：`ResearchRun`、included/excluded `ResearchEvidence`、同源 `ResearchCitation`、标签建议/证据链接、一个来源仅一个 active run，以及 legacy tag 迁移都由测试覆盖。

## 任务 2 — 预算、引文验证与 AI 研究合同

- RED：`cd backend && uv run pytest tests/services/test_research_citations.py tests/test_ai.py -q` 在 `app.services.research` 与 `GeneratedResearchNote` 均不存在时收集失败，证明预算/解析/提示合同尚未实现。
- GREEN：`uv run pytest tests/services/test_research_citations.py tests/test_ai.py -q` 通过，`18 passed in 0.19s`。
- 静态验证：`uv run ruff check app/services/research app/services/ai.py` 通过；随后 `uv run pytest -q -W error && uv run ruff check .` 通过，`228 passed in 2.45s`。
- 证据：三个来源各有固定预算（含 32 请求上限）；采集定位符和 included/excluded 记录被类型校验；报告固定为十个章节，未知 `[E<n>]`、重复/错序标题和无引用实质段落被拒绝；模型对单证据、报告和标签候选均把公共材料标为 untrusted data，并只接受 evidence-scoped JSON 标签建议。

## 任务 3 — GitHub 有界代码证据采集

- RED：`cd backend && uv run pytest tests/connectors/test_research_github.py tests/test_url_safety.py -q` 因 `app.services.research.collectors` 不存在而收集失败。
- GREEN：同一命令通过，`34 passed in 0.08s`；`uv run ruff check app/services/research/collectors app/services/composition.py` 通过；既有轻量导入回归 `uv run pytest tests/connectors/test_github.py -q` 为 `15 passed in 0.07s`。
- 证据：collector 从 REST metadata、branch ref 与 recursive tree 得到不可变 commit SHA；按 README、manifest、entry point、architecture、source 的固定优先级最多选择 20 个 UTF-8 文本文件；每个 included/excluded 条目拥有 commit-aware locator。vendor、二进制、minified/generated、体积/文件/请求上限及失败响应均作为排除原因保存；truncated tree 被显式标为 partial coverage；共用安全 client 的 host 上限提升为 40 请求/60 秒，collector 自身仍以 32 请求/run 为硬上限。

## 任务 4 — arXiv PDF 与 Hugging Face 有界采集

- RED：`cd backend && uv run pytest tests/connectors/test_research_arxiv.py tests/connectors/test_research_huggingface.py tests/connectors/test_response_policy.py -q` 因 arXiv/Hub research collectors 尚不存在而收集失败。
- GREEN：同一命令通过，`10 passed in 0.13s`；`uv run ruff check app/services/research/collectors app/services/connectors/response_policy.py` 通过；既有轻量导入回归 `uv run pytest tests/connectors/test_arxiv.py tests/connectors/test_huggingface.py -q` 为 `22 passed in 0.07s`；后端全量为 `235 passed in 2.45s`，完整 ruff 通过。
- 证据：PDF 技能指导使用 `pypdf` 对内存中的公开文档作页级文本抽取（不使用 OCR）；arXiv 仅接收 `application/pdf`，将单文档限制为 25 MiB、60 页、50 万字符，使用版本化 PDF/page locator，并把加密、无文本、无效或超限情况标记为 partial。Hub 以 API `sha` 锁定 revision，最多读取 12 个 README/config/源码文本，拒绝权重和数据载荷；共享 response policy 可按调用显式放宽 PDF body limit，而历史默认仍为 5 MiB。

## 任务 5 — 编排器与治理标签生命周期

- RED：`cd backend && uv run pytest tests/services/test_research_orchestrator.py tests/services/test_tags.py tests/api/test_sources.py -q` 因 `ResearchOrchestrator` 与 `TagService` 不存在而收集失败。
- GREEN：同一命令通过，`8 passed in 0.37s`；相关 ruff 通过；`uv run pytest -q -W error && uv run ruff check .` 为 `239 passed in 2.50s`。
- 证据：`ResearchOrchestrator` 在 collector/AI 网络等待外使用短数据库会话，按 collect → persist evidence → note → validate report → tag 的单一状态机运行。它保存内容 hash、覆盖 JSON、证据 digest、同源 citation 和报告 Artifact，且绝不写回 `Source` 原材料；partial 覆盖、未配置 provider 和无效 citation 分别产生真实 terminal 状态。`TagService` 提供受控层级 seed、带 evidence 的 AI suggestion、用户 accept/reject、自定义标签；来源筛选已退休 legacy JSON 路径，仅查 accepted governed tag（含子标签）。

## 任务 6 — 持久 worker 与自动启动设置

- RED：`cd backend && uv run pytest tests/services/test_research_worker.py tests/api/test_imports.py tests/api/test_derivations.py -q` 因 `app.services.research.worker` 不存在而收集失败。
- GREEN：worker/import/settings/lifecycle 关联套件为 `23 passed in 1.00s`；相关 ruff 通过；后端全量 `243 passed in 2.61s`，完整 ruff 通过。
- 证据：单 worker 使用数据库 compare-and-set lease 认领 queued 或过期 running 任务，执行后释放 lease；仅 `provider_error`、`network_error`、`rate_limited` 等瞬时失败可以在初次执行之外重试两次。`research.auto_start` 是持久、默认 false 的 browser-safe 设置；原有仅 presentation 的 PATCH 保持有效。lifespan 仅在该设置已启用时启动一个 worker；支持且有内容的 GitHub/arXiv/Hub 导入只有在提交后才会自动入队。

## 任务 7 — 研究与标签 API 合同

- RED：`cd backend && uv run pytest tests/api/test_research.py tests/api/test_tags.py tests/api/test_sources.py -q` 显示研究/标签路由未注册；随后发现新 API 测试与服务测试同名，已重命名为 `test_tags_api.py` 以避免 pytest 模块冲突。
- GREEN：`tests/api/test_research.py tests/api/test_tags_api.py tests/api/test_sources.py` 为 `7 passed in 0.39s`；全部 API 测试为 `38 passed in 1.91s`；后端全量为 `246 passed in 2.93s`，ruff 通过。
- 证据：`POST /sources/{id}/research` 使用持久运行合同并对 active run 幂等地返回 202；run detail 和证据分页只读取存储状态。tag tree/custom/decision/delete API 与 source detail 的 appended research/tag fields 均为 additive；`docs/api.md` 记录新的状态、自动开关、分页、治理路由和安全错误语义。

## 任务 8 — 前端 typed API 合同与轮询

- RED：`cd frontend && npm run test -- --run src/hooks/useResearchRun.test.tsx src/api.test.ts` 显示 `getResearchRun`、`startResearch` 与 `useResearchRun` 均不存在。
- GREEN：同一命令为 `23 passed in 24ms`；`npm run lint` 通过；`npm run build` 通过。
- 证据：`types.ts` 与 API guard 识别 research run、evidence、tag 和 `research` Artifact；浏览器端可启动任务、读取 run/evidence/tag DTO。独立 `useResearchRun` 只轮询非终态持久 run，在 complete/partial/blocked/failed 后停止，并在来源切换与 unmount 时 abort 请求；既有派生类型被收窄，不能把 research Artifact 错送往 legacy derive 端点。

## 任务 9 — 研究报告、证据与标签治理界面

- RED：`cd frontend && npm run test -- --run src/components/ResearchPanel.test.tsx src/components/TagManager.test.tsx src/components/EditorWorkspace.test.tsx` 在 `ResearchPanel` 和 `TagManager` 尚不存在时收集失败。
- GREEN：上述组件套件为 `19 passed`；完整前端验证为 `10 files / 68 passed in 1.44s`，`npm run lint`、`npm run build` 与 `git diff --check` 全部通过。
- 证据：来源工作区可显式启动深度研究，展示 queued/running/terminal 状态、partial 覆盖原因和安全失败码；仅当报告中的 `[E<n>]` 确实存在于本 run 的持久证据时才显示引用跳转。证据清单保留 included 与 excluded 条目及排除原因。研究报告是独立 tab，编辑界面明示 user edit 不再自动验证引用。AI suggested 标签与 accepted 标签分区，接受、拒绝、自定义和移除均为显式动作；侧栏只把 accepted 标签筛选参数发送给后端。

## 任务 10 — 使用说明、设置修复与最终质量闸门

- RED：将自动研究设置的生产键 `{"auto_start":true}` 放入导入路径，并连续发送“启用自动研究 → 仅更新显示设置”请求后，`tests/api/test_imports.py::test_enabled_auto_research_enqueues_only_supported_content_bearing_imports` 和 `tests/api/test_derivations.py::test_settings_preserves_auto_research_when_only_presentation_changes` 均失败：worker 读取了旧的 `enabled` 键，后一次 PATCH 重置了 research 设置。
- GREEN：修复为 partial PATCH 语义、以 `auto_start` 为 canonical key 并兼容历史 `enabled` 后，上述 API 测试为 `2 passed`；自动导入测试通过正式 `PATCH /api/settings` 写入设置，覆盖端到端持久设置 → 导入 → enqueue 路径。
- 全量验证：`cd backend && uv run pytest -q -W error` 为 `247 passed in 2.66s`，`uv run ruff check .` 通过；全新临时 SQLite 上 `DATABASE_URL=… uv run alembic upgrade head` 完成 `0001_initial_schema → 0002_deep_research`。`cd frontend && npm run test -- --run` 为 `10 files / 69 passed`，lint/build 通过，`git diff --check` 通过。
- 交付文档：README 记录研究工作流、三类平台的证据/预算/禁区、引文和标签治理、自动模式的重启语义及 worker 边界；API 文档说明 PATCH 会保留未提交的设置组。
- 环境限制：没有 `docker` 可执行文件；`podman compose config` 已尝试，但本机 Podman socket 未运行（connection refused），故本环境无法完成 Compose 解析。该项是宿主环境前置条件，不是应用测试失败。

## EvidenceBundleDraft

- Artifact key: final-regression
- Type: test-suite
- Source: backend pytest/ruff/alembic; frontend vitest/lint/build
- Summary: Backend 247 passed, frontend 69 passed; migration upgrade succeeds on a fresh SQLite database.
- Verifier: commands recorded in 90-evidence.md

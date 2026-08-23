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

# Hugging Face Blog 证据采集实施证据

## Initial Evidence

- `https://huggingface.co/blog/openenv-agentic-rl` 是一篇可读取的 Hugging Face Blog 文章；外部浏览结果显示标题、发布日期和正文标题层级。
- 当前部署中的 Hugging Face connector 只将两段普通路径视为模型仓库，因此会错误访问 Hub 模型路径；Podman runtime 对 Hugging Face 的 HTTPS 连接在 10 秒时超时。
- 该外部网络限制不构成修改 URL 分类和 fixture 合同的理由；后续运行时验收会单独记录结果。

## Task 1 — Blog Import Connector

- RED：`cd backend && uv run pytest tests/connectors/test_huggingface.py -k public_blog -q` 得到预期的 `blocked != ready` 断言失败；fixture 特意提供错误模型 API 的 404 响应，避免假阳性的 KeyError。
- GREEN：Blog 连接器 fixture，以及失败时规范 URL 保留、精确路径和畸形路径拒绝等回归，共 `15 passed`。
- 质量：`uv run ruff check app/services/connectors/huggingface.py tests/connectors/test_huggingface.py` 与 `git diff --check` 均通过。
- 独立审查：先后修复了失败路径泄漏 `https://invalid.invalid/` 与冗余斜杠被错误接受两项 requirements-scope implementation drift；最终规格与代码质量复核均无遗留问题。

## Task 2 — Blog Evidence Collector

- RED：Blog 的两段式规范路径在旧 collector 中会被误解析为 `blog/openenv-agentic-rl` 模型；测试为该错误 Hub 路径提供 404 fixture，得到可解释的 `restricted_repository` 失败而非测试错误。
- GREEN：collector fixture 覆盖单条 `blog_article` evidence、UTF-8 SHA-256 revision、非 ready 失败保留和超过 1 MiB 的诚实失败，`4 passed`。
- 集成审查发现过一次工作树隔离导致 Task 1 代码未实际落入部署工作树；已将同一经审查的 connector 改动同步到目标工作树，并由独立合并审查确认四个文件共同通过。
- 最终 slice evidence：`pytest tests/connectors/test_huggingface.py tests/connectors/test_research_huggingface.py -q` 为 `19 passed`；四文件 scoped ruff 和 `git diff --check` 均通过。

## Runtime Defect — arXiv PDF NUL

- 真实 arXiv collector 可解析 25 页，但 PostgreSQL 首次持久化失败：`psycopg.DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes`。
- 修复位于通用 PDF extraction owner：将每个 `\x00` 替换为 `U+FFFD`，再执行空白规范化、字符预算截断与计数；没有新增数据库或 orchestrator fallback。
- RED 为 `1 failed, 3 passed`（`A\x00B` 对比 `A�B`）；GREEN 与相关回归为 19 passed，独立审查无 finding。
- 真实 run #4 成功持久化 25 条 `paper_page` evidence、73,689 字符，并确认包含 1 个替代字符；覆盖为 `complete=true`。

## Final Runtime Acceptance

- 全量 backend：`uv run pytest -q -W error` 为 `259 passed`；`uv run ruff check .` 通过。
- Podman：database、backend、frontend 均为 healthy；`GET /api/health` 为 200，frontend 为 HTTP 200；research auto-start 已启用。
- GitHub：source #1 / run #1，固定 commit `e319a66d7351c75abe7f040d02d9a8d6e25028e9`，20 条 included repository evidence、200 条有界 exclusion 记录、321,139 内容字符；随后因 AI 未配置以 `provider_not_configured` blocked。
- arXiv：source #2 / run #4，PDF 2,700,303 bytes，25/25 页、73,689 字符、25 条 included evidence；随后同样因 AI 未配置 blocked。
- Hugging Face Blog：连接器/collector fixture 与合并审查均通过；真实 import 返回 HTTP 422 `source_unavailable`。宿主机对 `huggingface.co:443` 在 10 秒内连接超时，而 DNS 可解析；这是当前外部网络边界。
- 未覆盖：在真实 Hugging Face 页面上的正文 evidence，以及真实 AI provider 的报告、引用和标签生成。

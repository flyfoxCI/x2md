# Hugging Face Blog 证据采集实施计划

## Goal

实现已批准的 Hugging Face Blog 导入与有界研究证据路径，并用用户提供的 OpenEnv Agentic RL 文章做真实验收。

## Architecture

`HuggingFaceConnector` 仍是 URL 分类与来源平台语义的唯一 owner；`WebConnector` 仍是 HTML 提取的唯一 owner；`HuggingFaceResearchCollector` 仍是研究证据和 Hugging Face 预算的唯一 owner。Blog 不引入新持久化模型、队列或 collector。

## Tech Stack

Python 3.12、FastAPI、BeautifulSoup（现有）、SQLAlchemy、pytest、Podman Compose。

## Baseline/Authority Refs

- `docs/aegis/specs/2026-08-23-huggingface-blog-evidence-brief.md`
- `docs/aegis/specs/2026-08-23-deep-research-knowledge-base-design.md`
- 用户指定的 Hugging Face Blog URL。

## Compatibility Boundary

保留 Hub model/dataset、其 revision/file collector、通用网页和研究 API 的行为。Blog 元数据使用 `resource_type`，绝不伪造 `repository_type`。

## Architecture Integrity Lens

- **Invariant:** 每个 Blog 报告结论只能引用其 ResearchRun 保存的一条有界正文 evidence。
- **Canonical owners:** URL/来源归一化在 HuggingFaceConnector；正文解析在 WebConnector；研究证据在 HuggingFaceResearchCollector。
- **Responsibility overlap:** 不复制 BeautifulSoup 解析，也不让 API 路由推断来源类型。
- **Higher-level simplification:** 复用单一安全 HTML 提取器，不创建博客专用网络客户端。
- **Retirement/falsifier:** 若 Blog 需要分段或多文章集合，应建立经评审的新文章 evidence 合同；本计划不添加临时递归抓取。
- **Verdict:** proceed。

## Plan-Time Complexity Check

- **Target files:** `connectors/huggingface.py`（约 230 行）、`collectors/huggingface.py`（约 330 行）及各自 fixture 测试。
- **Owner fit:** 两个现有 owner 已分别负责 URL 归一化和 Hugging Face 证据采集。
- **Add-in-place risk:** 新分支仅覆盖明确 `resource_type=blog_article`，且共享解析不复制。
- **Recommendation:** edit-in-place。

## Tasks

### 1. Blog 导入契约（strict TDD）

**Files:** modify `backend/tests/connectors/test_huggingface.py`, `backend/app/services/connectors/huggingface.py`.

**Why:** 避免把 `/blog/<slug>` 误认作模型仓库，并保留 Hugging Face 研究语义。

**Verification:** `cd backend && uv run pytest tests/connectors/test_huggingface.py -q`.

- [ ] 写一个 fake safe-client 的 Blog HTML fixture 测试；断言 ready、canonical Blog URL、`platform="huggingface"`、`resource_type="blog_article"`、无 Hub API 请求。
- [ ] 运行该测试并确认当前实现因 Blog 被误分为模型而失败。
- [ ] 最小实现 Blog path 分类，复用 `WebConnector.fetch` 并重新包装为 Hugging Face `NormalizedSource`。
- [ ] 重跑连接器测试并确认 Blog 与现有 model/dataset/Spaces 用例均通过。
- [ ] Commit `feat(huggingface): normalize public blog articles`.

### 2. Blog 研究证据契约（strict TDD）

**Files:** modify `backend/tests/connectors/test_research_huggingface.py`, `backend/app/services/research/collectors/huggingface.py`.

**Why:** 报告必须基于再次有界采集、哈希版本化的文章正文，而不是导入摘要或 Hub 文件。

**Verification:** `cd backend && uv run pytest tests/connectors/test_research_huggingface.py tests/connectors/test_huggingface.py -q`.

- [ ] 写 Blog source fake-client 测试；断言仅一条 `blog_article` evidence、稳定 locator、SHA-256 revision、完整覆盖和单次请求。
- [ ] 写超出 1 MiB 正文的用例；断言无 included evidence 且覆盖原因是 `response_too_large`。
- [ ] 运行测试并确认当前 collector 不识别 Blog source 而失败。
- [ ] 最小实现 Blog 分支：复用 `WebConnector`、在预算内创建单条 article evidence、在失败或超限时记录诚实覆盖结果；Hub 文件逻辑不变。
- [ ] 重跑聚焦测试，随后运行相关 GitHub/arXiv/Hugging Face suites。
- [ ] Commit `feat(research): collect bounded Hugging Face blog evidence`.

### 3. 回归、镜像与真实验收

**Files:** deployment-only rebuild; modify `README.md` only if公开支持范围需要同步。

**Why:** 用用户提供的公开 URL 验证真实入口，不把 fixture green 当作可部署证明。

**Verification:** `cd backend && uv run pytest -q -W error && uv run ruff check app tests`; rebuild backend with `podman build --pull-never`; recreate backend; import and start research through `http://127.0.0.1:8000`.

- [ ] 跑完整后端回归和静态检查。
- [ ] 用 Podman 无远程基础镜像拉取重建后端，重启并确认 `/api/health`。
- [ ] 对 Blog URL 导入并开始 research；启用持久 worker 后轮询 run，读取 evidence/coverage/status。
- [ ] 对 GitHub、arXiv 与 Blog 三条 URL 汇总导入、采集、AI 生成和标签状态；AI 未配置或站点网络限制必须单独说明。
- [ ] Commit deployment compatibility/documentation fixes with验证证据。

## Risks and Retirement

| Risk | Control | Retirement trigger |
| --- | --- | --- |
| Blog HTML 结构变化 | 复用 article/main fallback，保存内容 hash 与真实失败覆盖 | 若需要站点特定 DOM 选择器，另立规格。 |
| 大正文 | 同一平台 1 MiB evidence budget，超限不生成报告 | 经评审后才调整固定预算。 |
| Hugging Face 网络超时 | 保留 `network_error`/blocked 状态，不伪造成功 | 网络恢复后可安全重试同一手动研究入口。 |

## Self-Review

该计划不增加新 API、数据库模式、队列、凭据或爬取边界；两个 TDD 任务分别覆盖来源归一化与证据采集，最后任务覆盖容器与真实入口。所有旧 Hub 行为由相关回归测试覆盖。

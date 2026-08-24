# Hugging Face Blog 证据采集规格简报

## Goal

将 `https://huggingface.co/blog/<slug>` 识别为 Hugging Face 的公开研究对象，使其走既有“导入 → 有界证据 → 研究运行 → 引用与标签”链路；不把它误认为 Hub 模型，也不降级为无平台语义的通用网页。

## Baseline / Authority Refs

- 用户的真实验收链接：`https://huggingface.co/blog/openenv-agentic-rl`。
- `docs/aegis/specs/2026-08-23-deep-research-knowledge-base-design.md`：三平台有界、可追溯研究；禁止下载权重、数据集 payload 与无限抓取。
- `backend/app/services/connectors/huggingface.py`：Hugging Face URL 分类与来源归一化的唯一 owner。
- `backend/app/services/research/collectors/huggingface.py`：Hugging Face 研究证据的唯一 owner。
- `backend/app/services/connectors/web.py`：已验证的安全 HTML 正文提取器。

## Approved Design

1. `HuggingFaceConnector` 将精确匹配 `/blog/<slug>`（仅一个非空 slug；忽略 query）并规范化为 `https://huggingface.co/blog/<slug>`。模型、数据集和 Spaces 的既有分类不变。
2. Blog 导入复用 `WebConnector` 的安全正文提取，而后以 `platform="huggingface"` 持久化，元数据包含 `resource_type="blog_article"` 与 `blog_slug`。它不会请求 `/api/models/...` 或任何 Hub 原始文件。
3. `HuggingFaceResearchCollector` 检测 `resource_type="blog_article"` 后再次通过相同安全提取器读取该规范 URL，只创建一条 `blog_article` included evidence；文章文本必须不超过既有 Hugging Face 1 MiB 内容预算。
4. 该证据的 locator 为 `huggingface://blog/<slug>#article`；`source_revision` 为正文 UTF-8 SHA-256。持久化层同时保存内容哈希，因而每次运行都能辨别文章版本。
5. 非 ready 的页面提取保留真实失败原因和不完整覆盖；正文超限返回 `response_too_large` 覆盖失败。没有 HTML、模型权重、数据 payload、递归链接追踪或新 API/数据库表。

## Alternatives Considered

| Option | Decision | Reason |
| --- | --- | --- |
| 将 Blog 当作模型仓库 | Rejected | `/blog/<slug>` 不是 `owner/repo`，会访问错误的 Hub API。 |
| 交给通用 Web 连接器 | Rejected | 会失去 Hugging Face 平台、研究 collector 与证据治理语义。 |
| 在 Hugging Face 路径内复用安全 HTML 提取器 | Approved | 保留平台语义，避免重复 HTML 解析，并维持现有安全出站边界。 |

## Compatibility Boundary

- `platform="huggingface"`、现有 Hub 模型/数据集、Sources/ResearchRuns API、研究运行状态机和标签合同不变。
- `repository_type` 仅继续表示 `model` 或 `dataset`；Blog 使用独立的 `resource_type`，避免伪造仓库元数据。
- 固定 Hugging Face 预算仍为最多 12 个 evidence / 1 MiB；Blog 只可消耗其中一条和其正文大小。

## Verification

- 连接器 fixture：Blog 导入为 ready Hugging Face source，且只访问文章 URL。
- 采集器 fixture：产出一条 hash-versioned article evidence；超过 1 MiB 时诚实失败。
- 既有 Hub、arXiv、GitHub connector/collector 相关测试保持通过。
- 容器重建后，对用户给出的 Blog URL 进行真实导入和研究队列验收；网络失败与 AI 未配置分开报告。

## Non-goals

- 不支持 Spaces、Hugging Face Docs、论坛、动态评论、全文站点爬取或多文章聚合。
- 不绕过 Hugging Face 登录、反爬或网络策略。
- 不修改受控标签分类；AI 仍只能用本运行保存的证据提出标签建议。

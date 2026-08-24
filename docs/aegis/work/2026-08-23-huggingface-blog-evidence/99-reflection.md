# Hugging Face Blog 证据采集复盘

## Outcome

Hugging Face Blog 已成为独立的 Hugging Face 研究对象：精确 URL 分类、规范身份、安全 HTML 提取、1 MiB 有界正文 evidence、稳定 locator 与内容 revision 均由既有 owner 链路承担。GitHub 与 arXiv 的真实运行验证了同一证据优先状态机。

## What Changed the Result

- 独立审查发现了失败路径 canonical URL 泄漏、冗余斜杠误识别和隔离工作树未同步三类问题，均在容器验收前关闭。
- 真实 arXiv PDF 暴露了 fixture 未覆盖的 PostgreSQL NUL 限制；将规范化放在通用 PDF extraction boundary，避免数据库与 orchestrator 出现重复兼容逻辑。
- “已采集证据”和“已生成研究报告”被明确分开：AI 未配置时保存 evidence，但运行诚实地停为 blocked。

## Residual Boundaries

- 当前主机无法连接 `huggingface.co:443`，因此 Blog 的真实页面验收仍依赖外部网络恢复。
- AI provider 未配置，真实报告、引用校验与标签建议尚未运行；这不是 collector 成功的替代证据。
- GitHub 的 20 文件与 arXiv 的 60 页/500,000 字符预算保持不变；有界 exclusion 不是抓取失败。

## Governance Closure

- Repair track：修复 Blog 错误模型分类与 PDF NUL 持久化失败，并通过 fixture、全量回归和真实数据库 evidence 验证。
- Retirement track：Blog 不再进入 `/api/models/blog/...` 旧分支；没有保留通用 Web fallback 或数据库清洗 fallback。
- Complexity：owner 各增加一个窄分支/规范化操作，未引入新 API、schema、表或重复解析器；净复杂度小幅增加且由平台语义与数据库安全性证明合理。

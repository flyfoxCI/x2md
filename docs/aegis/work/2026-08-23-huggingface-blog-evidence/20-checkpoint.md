# Hugging Face Blog 证据采集检查点

## TodoCheckpointDraft

- **Current todo:** 无实现待办；保留外部配置与网络边界供部署者处理。
- **Active slice:** closed；容器保持运行，自动研究 worker 已启用。
- **Completed todos:** 规格、计划、工作区隔离、真实失败诊断、Blog 导入连接器、Blog 有界 evidence collector、arXiv PDF NUL 规范化、全量回归、Podman 重建和三条真实链接验收。
- **Evidence refs:** GitHub source #1 的 run #1 保存 20 条 included repository evidence（321,139 字符）；arXiv source #2 的 run #4 保存 25/25 页（73,689 字符）；Hugging Face Blog 再次导入返回 `source_unavailable`，且宿主机到 `huggingface.co:443` 连接超时。全量 backend 为 259 passed，ruff 通过，三个容器健康。
- **Blocked-on:** AI provider 未配置，故 GitHub/arXiv 在证据采集完成后以 `provider_not_configured` blocked，未生成研究报告与标签；Hugging Face 的真实导入受当前主机网络限制。
- **Next step:** 配置 AI provider，并恢复主机到 `huggingface.co:443` 的访问后重试 Blog；无需再改 Blog 分类或 collector 合同。

## DriftCheckDraft

- **Scope:** aligned；只覆盖用户提供的精确 `/blog/<slug>` 路径和其一条正文 evidence，再做既有三平台的真实验收。
- **Compatibility:** intact；不改 API、schema、自动 worker、标签合同或 Hub file 分支。
- **New owner/fallback:** HuggingFaceConnector 保留 URL 分类 owner，WebConnector 保留安全 HTML owner；HuggingFaceResearchCollector 是 Blog evidence 的唯一 owner。
- **Retirement:** no temporary workaround introduced.
- **Decision:** stop；实现与本机可执行验证已完成，剩余项需要外部配置或网络状态变化。

## ResumeStateHint

若外部条件恢复，从本文件恢复时先检查 `/api/health` 的 `aiConfigured`，再重试 Blog import；GitHub/arXiv 已有持久化 evidence，无需重复抓取。

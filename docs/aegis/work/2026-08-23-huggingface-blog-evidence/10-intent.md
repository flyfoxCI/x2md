# Hugging Face Blog 证据采集实施意图

## TaskIntentDraft

- **Outcome:** 用户指定的 Hugging Face OpenEnv Agentic RL Blog 可作为 Hugging Face 研究对象导入，并在固定预算内形成可引用证据。
- **Success evidence:** Blog connector/collector fixtures、全量后端回归、容器重建和真实 URL 导入/研究运行均有可复核输出。
- **Stop condition:** Blog 未被误识别为 Hub 模型；真实网络或 AI 配置导致的限制被持久化并分开报告；不增加越权抓取或 Hub payload 下载。
- **Non-goals:** Spaces、Docs、论坛、评论、文章集合与大规模爬取。

## BaselineReadSetHint

- `docs/aegis/specs/2026-08-23-huggingface-blog-evidence-brief.md`
- `docs/aegis/plans/2026-08-23-huggingface-blog-evidence.md`
- `backend/app/services/connectors/huggingface.py`
- `backend/app/services/research/collectors/huggingface.py`
- `backend/app/services/connectors/web.py`

## ImpactStatementDraft

- **Affected layers:** Hugging Face connector、Hugging Face evidence collector、fixture tests、运行时验证。
- **Invariant:** Blog evidence remains bounded to one article and carries a stable locator plus a content-derived revision.
- **Compatibility:** Hub model/dataset imports and their revision-file collector remain unchanged; generic HTML parsing stays owned by WebConnector.
- **Risk:** Hugging Face network path currently times out from the Podman runtime; tests must distinguish this external condition from route correctness.

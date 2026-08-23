# 深度研究知识库 — 检查点

## TodoCheckpointDraft

- 当前切片：任务 6 — 持久单 worker 与自动启动设置。
- 已完成：设计规格、实施计划、隔离工作区、基线验证；任务 1 的 ORM/schema、`0002_deep_research` 迁移、legacy tag 转换和迁移升降级验证；任务 2 的研究预算、报告引文校验和 AI 研究合同；任务 3 的 GitHub revision-pinned 证据采集；任务 4 的 arXiv PDF 与 Hugging Face 有界采集；任务 5 的编排器与治理标签生命周期。
- 未完成：任务 6–10 的实现与全量验证。
- 下一步：为租约认领、过期恢复、两次有界重试、关闭、默认禁用/启用自动启动和 import 后入队编写失败测试。

## ResumeStateHint

- 工作树：`/Users/jerry/code/x2md/.worktrees/deep-research-knowledge-base`
- 分支：`codex/deep-research-knowledge-base`
- 基线：后端 `216 passed`；前端 `61 passed`；前端 lint/build 均通过。
- 任务 1：`tests/test_models.py` 为 17 passed；Alembic 已从 head 降至 `0001` 再升至 head；相关 ruff 通过。
- 任务 2：`tests/services/test_research_citations.py tests/test_ai.py` 为 18 passed；后端全量为 228 passed；ruff 通过。
- 任务 3：`tests/connectors/test_research_github.py tests/test_url_safety.py` 为 34 passed；既有 `tests/connectors/test_github.py` 为 15 passed；collector ruff 通过。
- 任务 4：`tests/connectors/test_research_arxiv.py tests/connectors/test_research_huggingface.py tests/connectors/test_response_policy.py` 为 10 passed；既有 arXiv/Hub 导入回归为 22 passed；后端全量为 235 passed；ruff 通过。
- 任务 5：`tests/services/test_research_orchestrator.py tests/services/test_tags.py tests/api/test_sources.py` 为 8 passed；后端全量为 239 passed；ruff 通过。

## DriftCheckDraft

- Scope：符合已批准的深度研究规格。
- Compatibility：`Source` 与历史 Artifact 未改写；新 `research_run_id` 可空，`research` 仅为新增 Artifact kind；原有 derive/chat 使用的 provider 上限和响应合同保持不变。
- Retirement：legacy `KnowledgeNote.tags_json` 已只作为 migration rollback 安全副本；来源 tag 筛选已改用 accepted `TagAssignment` 与层级 `TagDefinition`。
- Decision：continue。

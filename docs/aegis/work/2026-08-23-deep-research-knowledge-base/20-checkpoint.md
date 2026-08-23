# 深度研究知识库 — 检查点

## TodoCheckpointDraft

- 当前切片：任务 3 — 有界 GitHub 代码证据采集。
- 已完成：设计规格、实施计划、隔离工作区、基线验证；任务 1 的 ORM/schema、`0002_deep_research` 迁移、legacy tag 转换和迁移升降级验证；任务 2 的研究预算、报告引文校验和 AI 研究合同。
- 未完成：任务 3–10 的实现与全量验证。
- 下一步：为 commit/tree/file 采集、确定性文件选择、排除原因与请求/体积预算编写 GitHub collector 失败测试。

## ResumeStateHint

- 工作树：`/Users/jerry/code/x2md/.worktrees/deep-research-knowledge-base`
- 分支：`codex/deep-research-knowledge-base`
- 基线：后端 `216 passed`；前端 `61 passed`；前端 lint/build 均通过。
- 任务 1：`tests/test_models.py` 为 17 passed；Alembic 已从 head 降至 `0001` 再升至 head；相关 ruff 通过。
- 任务 2：`tests/services/test_research_citations.py tests/test_ai.py` 为 18 passed；后端全量为 228 passed；ruff 通过。

## DriftCheckDraft

- Scope：符合已批准的深度研究规格。
- Compatibility：`Source` 与历史 Artifact 未改写；新 `research_run_id` 可空，`research` 仅为新增 Artifact kind；原有 derive/chat 使用的 provider 上限和响应合同保持不变。
- Retirement：迁移会复制 legacy `KnowledgeNote.tags_json` 为 accepted 自定义标签；查询路径退休留待任务 5。
- Decision：continue。

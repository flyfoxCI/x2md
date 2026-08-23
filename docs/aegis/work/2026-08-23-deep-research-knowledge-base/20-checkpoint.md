# 深度研究知识库 — 检查点

## TodoCheckpointDraft

- 当前切片：任务 10 — 文档、端到端质量闸门与交付验证。
- 已完成：设计规格、实施计划、隔离工作区、基线验证；任务 1–8 的后端/API/typed 客户端链路；任务 9 的研究报告、证据、标签治理和侧栏筛选界面。
- 未完成：任务 10 的最终 README、迁移/Compose 与全量回归验证。
- 下一步：更新公开产品说明，执行后端、前端、迁移和 Compose 质量闸门，并核对工作树交付状态。

## ResumeStateHint

- 工作树：`/Users/jerry/code/x2md/.worktrees/deep-research-knowledge-base`
- 分支：`codex/deep-research-knowledge-base`
- 基线：后端 `216 passed`；前端 `61 passed`；前端 lint/build 均通过。
- 任务 1：`tests/test_models.py` 为 17 passed；Alembic 已从 head 降至 `0001` 再升至 head；相关 ruff 通过。
- 任务 2：`tests/services/test_research_citations.py tests/test_ai.py` 为 18 passed；后端全量为 228 passed；ruff 通过。
- 任务 3：`tests/connectors/test_research_github.py tests/test_url_safety.py` 为 34 passed；既有 `tests/connectors/test_github.py` 为 15 passed；collector ruff 通过。
- 任务 4：`tests/connectors/test_research_arxiv.py tests/connectors/test_research_huggingface.py tests/connectors/test_response_policy.py` 为 10 passed；既有 arXiv/Hub 导入回归为 22 passed；后端全量为 235 passed；ruff 通过。
- 任务 5：`tests/services/test_research_orchestrator.py tests/services/test_tags.py tests/api/test_sources.py` 为 8 passed；后端全量为 239 passed；ruff 通过。
- 任务 6：`tests/services/test_research_worker.py tests/api/test_imports.py tests/api/test_derivations.py tests/api/test_lifecycle.py` 为 23 passed；后端全量为 243 passed；ruff 通过。
- 任务 7：`tests/api/test_research.py tests/api/test_tags_api.py tests/api/test_sources.py` 为 7 passed；API 全量为 38 passed；后端全量为 246 passed；ruff 通过。
- 任务 8：`src/hooks/useResearchRun.test.tsx src/api.test.ts` 为 23 passed；前端 lint/build 通过。
- 任务 9：`npm run test -- --run` 为 68 passed；前端 lint/build 和 `git diff --check` 通过。

## DriftCheckDraft

- Scope：符合已批准的深度研究规格。
- Compatibility：`Source` 与历史 Artifact 未改写；新 `research_run_id` 可空，`research` 仅为新增 Artifact kind；原有 derive/chat 使用的 provider 上限和响应合同保持不变。
- Retirement：legacy `KnowledgeNote.tags_json` 已只作为 migration rollback 安全副本；来源 tag 筛选已改用 accepted `TagAssignment` 与层级 `TagDefinition`。
- Decision：continue。

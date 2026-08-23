# 深度研究知识库 — 实施意图

## 目标

在不改写原始来源和历史 Artifact 的前提下，实现 GitHub、arXiv、Hugging Face 的有界证据研究、可引用报告、可解释标签和可恢复的手动/自动任务。

## 成功证据

- 三类来源可留下版本定位、覆盖范围和排除原因。
- `research` Artifact 的每项引用指向同一 `ResearchRun` 的持久证据。
- 标签建议带证据，用户确认的标签可检索且不被后续运行覆盖。
- 全量后端、前端、lint/build 与 compose 配置验证通过。

## 非目标

- 私有或受限材料、模型权重/完整数据集下载、OCR、分布式 worker、跨来源语义检索和多人协作。

## 基线读集

- `docs/aegis/specs/2026-08-23-deep-research-knowledge-base-design.md`
- `docs/aegis/plans/2026-08-23-deep-research-knowledge-base.md`
- `backend/app/models.py`、`backend/app/services/ai.py`、`backend/app/services/knowledge.py`
- `backend/app/services/connectors/`、`backend/app/api/`、`frontend/src/`

## 影响与不变量

- 影响：schema、迁移、采集、AI、队列、API、设置、前端和测试。
- 不变量：后端是远程访问与研究状态的唯一 owner；`Source` 不可变；研究状态不在客户端派生；旧 API 字段只追加不删除。

## ArchitectureReviewRequired

是。研究编排器、标签真相来源和持久 worker 是新的长期边界。

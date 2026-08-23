# 深度研究知识库 — 实施证据

## Baseline

- `cd backend && uv run pytest -q -W error`: 216 passed。
- `cd backend && uv run ruff check .`: passed。
- `cd frontend && npm run test -- --run`: 61 passed。
- `cd frontend && npm run lint`: passed。
- `cd frontend && npm run build`: passed。

## Slice evidence

后续切片将在此追加 RED、GREEN、回归命令与结果。

## 任务 1 — 研究持久化合同与迁移

- RED：`cd backend && uv run pytest tests/test_models.py -q` 在导入缺失的 `ResearchCitation` 时失败，证明测试覆盖了尚不存在的合同。
- GREEN：同一命令通过，`17 passed in 0.48s`。
- 迁移验证：`uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` 成功。
- 静态验证：`uv run ruff check app/models.py app/schemas.py alembic/versions/0002_deep_research.py` 通过。
- 证据：`ResearchRun`、included/excluded `ResearchEvidence`、同源 `ResearchCitation`、标签建议/证据链接、一个来源仅一个 active run，以及 legacy tag 迁移都由测试覆盖。

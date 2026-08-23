"""Contracts for bounded research inputs and evidence-backed reports."""

import pytest

from app.services.research.citations import (
    REQUIRED_REPORT_HEADINGS,
    ResearchReportValidationError,
    parse_report_citations,
    validate_research_report,
)
from app.services.research.contracts import EvidenceInput, collection_budget


def research_report(*, background: str = "研究问题由公开材料明确提出。[E1]") -> str:
    """Return the smallest report that satisfies the fixed public template."""
    return f"""## 研究范围与覆盖率

本次采集覆盖公开材料。

## 背景与目标

{background}

## 核心贡献

贡献由实现说明支持。[E12]

## 方法或架构

方法由架构证据支持。[E1]

## 实现、实验与配置

实现细节由配置证据支持。[E12]

## 关键结果

结果由公开材料支持。[E1]

## 局限与风险

局限由材料中的限制说明支持。[E12]

## 复现与应用建议

复现步骤由项目材料支持。[E1]

## 标签

- 机器学习

## 证据索引

- [E1] README
- [E12] 配置文件
"""


def test_parse_report_citations_preserves_first_occurrence_order() -> None:
    assert parse_report_citations("结果见 [E12]，并由 [E1] 和 [E12] 支持。") == (
        "E12",
        "E1",
    )


def test_validate_research_report_accepts_fixed_template_and_known_citations() -> None:
    citations = validate_research_report(research_report(), known_tokens={"E1", "E12"})

    assert citations == ("E1", "E12")
    assert REQUIRED_REPORT_HEADINGS[0] == "研究范围与覆盖率"


def test_validate_research_report_rejects_unknown_evidence_token() -> None:
    with pytest.raises(ResearchReportValidationError, match="unknown evidence token: E99"):
        validate_research_report(
            research_report(background="这一目标来自材料。[E99]"), known_tokens={"E1", "E12"}
        )


def test_validate_research_report_rejects_uncited_required_body_paragraph() -> None:
    with pytest.raises(ResearchReportValidationError, match="背景与目标"):
        validate_research_report(
            research_report(background="这一段没有可追溯的证据引用。"),
            known_tokens={"E1", "E12"},
        )


def test_evidence_input_rejects_an_unstable_locator() -> None:
    with pytest.raises(ValueError, match="locator"):
        EvidenceInput(evidence_id=1, locator="  ", kind="repository_file", content="text")


def test_collection_budgets_are_fixed_per_platform() -> None:
    github = collection_budget("github")
    arxiv = collection_budget("arxiv")
    huggingface = collection_budget("huggingface")

    assert (github.max_items, github.max_content_bytes, github.max_requests) == (
        20,
        1_572_864,
        32,
    )
    assert (arxiv.max_pdf_bytes, arxiv.max_pages, arxiv.max_extracted_chars) == (
        26_214_400,
        60,
        500_000,
    )
    assert (huggingface.max_items, huggingface.max_content_bytes) == (12, 1_048_576)

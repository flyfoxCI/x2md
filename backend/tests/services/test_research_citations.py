"""Contracts for bounded research inputs and evidence-backed reports."""

import pytest

from app.services.research.citations import (
    ResearchReportValidationError,
    parse_report_citations,
    validate_research_report,
)
from app.services.research.contracts import EvidenceInput, collection_budget
from app.services.research.templates import research_template


def research_report(platform: str = "github", *, uncited_heading: str | None = None) -> str:
    """Return the smallest report satisfying one platform-specific template."""
    template = research_template(platform)
    sections: list[str] = []
    for heading in template.headings:
        if heading == "一图综述":
            body = """```mermaid
flowchart TB
    A[\"研究对象\"] --> B[\"核心机制\"]
    B --> C[\"研究结论\"]
```

图示依据来自已纳入材料。[E1]"""
        elif heading == "研究范围与证据质量":
            body = "本次采集覆盖公开材料，并记录了未覆盖范围。"
        elif heading == "标签":
            body = "- 机器学习"
        elif heading == "证据索引":
            body = "- [E1] README\n- [E12] 配置文件"
        elif heading == uncited_heading:
            body = "这一段没有可追溯的证据引用。"
        else:
            body = f"{heading}的判断由纳入材料支持。[E1][E12]"
        sections.append(f"## {heading}\n\n{body}")
    return "\n\n".join(sections) + "\n"


def test_parse_report_citations_preserves_first_occurrence_order() -> None:
    assert parse_report_citations("结果见 [E12]，并由 [E1] 和 [E12] 支持。") == (
        "E12",
        "E1",
    )


@pytest.mark.parametrize("platform", ["github", "arxiv", "huggingface"])
def test_validate_research_report_accepts_each_platform_template(platform: str) -> None:
    citations = validate_research_report(
        research_report(platform), platform=platform, known_tokens={"E1", "E12"}
    )

    assert citations == ("E1", "E12")
    assert research_template(platform).headings[:3] == (
        "研究摘要",
        "一图综述",
        "研究范围与证据质量",
    )


def test_platform_templates_answer_different_research_questions() -> None:
    github = research_template("github").headings
    arxiv = research_template("arxiv").headings
    huggingface = research_template("huggingface").headings

    assert "系统架构与模块边界" in github
    assert "实验设计与评估协议" in arxiv
    assert "内容定位与目标读者" in huggingface
    assert len({github, arxiv, huggingface}) == 3


def test_validate_research_report_rejects_unknown_evidence_token() -> None:
    with pytest.raises(ResearchReportValidationError, match="unknown evidence token: E99"):
        validate_research_report(
            research_report().replace("[E1][E12]", "[E99]", 1),
            platform="github",
            known_tokens={"E1", "E12"},
        )


def test_validate_research_report_rejects_uncited_required_body_paragraph() -> None:
    with pytest.raises(ResearchReportValidationError, match="项目定位与问题"):
        validate_research_report(
            research_report(uncited_heading="项目定位与问题"),
            platform="github",
            known_tokens={"E1", "E12"},
        )


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("", "exactly one Mermaid"),
        ("```mermaid\nflowchart TB\nA-->B\n```\n\n```mermaid\nflowchart TB\nB-->C\n```", "exactly one Mermaid"),
        ("```mermaid\nflowchart TB\nclick A \"javascript:alert(1)\"\n```", "unsafe Mermaid"),
    ],
)
def test_validate_research_report_rejects_missing_duplicate_or_unsafe_mermaid(
    replacement: str, message: str
) -> None:
    report = research_report()
    start = report.index("```mermaid")
    end = report.index("```", start + len("```mermaid")) + 3

    with pytest.raises(ResearchReportValidationError, match=message):
        validate_research_report(
            report[:start] + replacement + report[end:],
            platform="github",
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


def test_validate_research_report_requires_a_readable_top_down_diagram() -> None:
    with pytest.raises(ResearchReportValidationError, match="top-down"):
        validate_research_report(
            research_report().replace("flowchart TB", "flowchart LR", 1),
            platform="github",
            known_tokens={"E1", "E12"},
        )

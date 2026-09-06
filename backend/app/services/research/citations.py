"""Deterministic validation for evidence-backed research Markdown."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.services.research.templates import research_template

_TOKEN_PATTERN = re.compile(r"\[E([1-9][0-9]*)\]")
_HEADING_PATTERN = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
_MERMAID_PATTERN = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_UNSAFE_MERMAID_PATTERN = re.compile(
    r"%%\{|\bclick\b|javascript\s*:|<\/?[a-z][^>]*>", re.IGNORECASE
)


class ResearchReportValidationError(ValueError):
    """The report cannot safely become a completed research Artifact."""


def parse_report_citations(markdown: str) -> tuple[str, ...]:
    """Return valid evidence tokens once, in their first appearance order."""
    seen: set[str] = set()
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(markdown):
        token = f"E{match.group(1)}"
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tuple(tokens)


def validate_research_report(
    markdown: str, *, platform: str, known_tokens: Iterable[str | int]
) -> tuple[str, ...]:
    """Require the platform template, safe diagram, and known citations."""
    template = research_template(platform)
    sections = _report_sections(markdown)
    actual_headings = tuple(sections)
    if actual_headings != template.headings:
        raise ResearchReportValidationError(
            "report headings must exactly match the required research template"
        )

    _validate_mermaid(sections["一图综述"])

    citations = parse_report_citations(markdown)
    known = {_normalize_token(token) for token in known_tokens}
    for token in citations:
        if token not in known:
            raise ResearchReportValidationError(f"unknown evidence token: {token}")

    for heading in template.citation_required_headings:
        for paragraph in _nonempty_paragraphs(sections[heading]):
            if not any(token in paragraph for token in _TOKEN_PATTERN.findall(paragraph)):
                raise ResearchReportValidationError(
                    f"uncited non-empty body paragraph under {heading}"
                )
            paragraph_tokens = {f"E{number}" for number in _TOKEN_PATTERN.findall(paragraph)}
            unknown = paragraph_tokens - known
            if unknown:
                token = min(unknown, key=lambda value: int(value[1:]))
                raise ResearchReportValidationError(f"unknown evidence token: {token}")
    return citations


def _report_sections(markdown: str) -> dict[str, str]:
    matches = tuple(_HEADING_PATTERN.finditer(markdown))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        if heading in sections:
            raise ResearchReportValidationError(f"duplicate report heading: {heading}")
        sections[heading] = markdown[body_start:body_end]
    return sections


def _nonempty_paragraphs(body: str) -> tuple[str, ...]:
    without_fences = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    return tuple(part.strip() for part in re.split(r"\n\s*\n", without_fences) if part.strip())


def _validate_mermaid(body: str) -> None:
    diagrams = _MERMAID_PATTERN.findall(body)
    if len(diagrams) != 1:
        raise ResearchReportValidationError("report must contain exactly one Mermaid diagram")
    diagram = diagrams[0].strip()
    if len(diagram) > 3_000:
        raise ResearchReportValidationError("Mermaid diagram exceeds the safe size limit")
    first_line = diagram.splitlines()[0].strip().lower() if diagram else ""
    if first_line not in {"flowchart tb", "flowchart td", "graph tb", "graph td"}:
        raise ResearchReportValidationError("Mermaid diagram must be a top-down flowchart")
    if _UNSAFE_MERMAID_PATTERN.search(diagram):
        raise ResearchReportValidationError("unsafe Mermaid directive")


def _normalize_token(token: str | int) -> str:
    if isinstance(token, int):
        if token <= 0:
            raise ValueError("evidence token must be positive")
        return f"E{token}"
    value = token.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if not re.fullmatch(r"E[1-9][0-9]*", value):
        raise ValueError(f"invalid evidence token: {token}")
    return value

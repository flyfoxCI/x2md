"""Governed research taxonomy and source-level tag lifecycle."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ResearchEvidence,
    ResearchRun,
    TagAssignment,
    TagAssignmentEvidence,
    TagDefinition,
)


@dataclass(frozen=True, slots=True)
class TagError(Exception):
    """A stable tag-governance failure safe for later API translation."""

    code: str
    message: str
    status_code: int = 422


_SYSTEM_TAGS = (
    ("object", "研究对象", "object", None),
    ("github-project", "GitHub 项目", "object", "object"),
    ("arxiv-paper", "arXiv 论文", "object", "object"),
    ("huggingface-model", "Hugging Face 模型", "object", "object"),
    ("huggingface-dataset", "Hugging Face 数据集", "object", "object"),
    ("method", "方法", "method", None),
    ("retrieval-augmented-generation", "检索增强生成", "method", "method"),
    ("agent", "智能体", "method", "method"),
    ("fine-tuning", "微调", "method", "method"),
    ("evaluation", "评估", "method", "method"),
    ("capability", "能力", "capability", None),
    ("reasoning", "推理", "capability", "capability"),
    ("multimodal", "多模态", "capability", "capability"),
)


class TagService:
    """The canonical owner of taxonomy definitions and assignment decisions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_system_taxonomy(self) -> None:
        """Idempotently seed a small controlled hierarchy without deleting user labels."""
        existing = {
            definition.slug: definition
            for definition in self._session.scalars(select(TagDefinition))
        }
        for slug, label, facet, parent_slug in _SYSTEM_TAGS:
            definition = existing.get(slug)
            if definition is None:
                definition = TagDefinition(
                    slug=slug, label=label, facet=facet, is_system=True
                )
                self._session.add(definition)
                self._session.flush()
                existing[slug] = definition
            if parent_slug is not None and definition.parent_id is None:
                definition.parent_id = existing[parent_slug].id

    def suggest(
        self,
        *,
        source_id: int,
        run_id: int,
        label: str,
        confidence: float,
        evidence_ids: tuple[int, ...],
    ) -> TagAssignment:
        """Persist one AI suggestion only when every cited evidence row belongs to its run."""
        self.ensure_system_taxonomy()
        run = self._session.get(ResearchRun, run_id)
        if run is None or run.source_id != source_id:
            raise TagError("research_run_not_found", "The research run does not exist.", 404)
        evidence = list(
            self._session.scalars(
                select(ResearchEvidence).where(
                    ResearchEvidence.research_run_id == run_id,
                    ResearchEvidence.source_id == source_id,
                    ResearchEvidence.id.in_(evidence_ids),
                )
            )
        )
        if not evidence_ids or {item.id for item in evidence} != set(evidence_ids):
            raise TagError(
                "invalid_tag_evidence",
                "A tag suggestion must cite included evidence from its own run.",
            )
        if any(item.status != "included" for item in evidence):
            raise TagError(
                "invalid_tag_evidence",
                "A tag suggestion must cite included evidence from its own run.",
            )
        definition = self._definition_for_label(label)
        assignment = TagAssignment(
            source_id=source_id,
            research_run_id=run_id,
            tag_id=definition.id,
            origin="ai",
            status="suggested",
            confidence=confidence,
        )
        self._session.add(assignment)
        self._session.flush()
        self._session.add_all(
            TagAssignmentEvidence(
                tag_assignment_id=assignment.id,
                evidence_id=evidence_id,
                source_id=source_id,
            )
            for evidence_id in dict.fromkeys(evidence_ids)
        )
        return assignment

    def accept(self, assignment_id: int) -> TagAssignment:
        """Confirm one suggestion without touching any assignment from earlier runs."""
        assignment = self._session.get(TagAssignment, assignment_id)
        if assignment is None:
            raise TagError("tag_assignment_not_found", "The tag assignment does not exist.", 404)
        assignment.status = "accepted"
        return assignment

    def reject(self, assignment_id: int) -> TagAssignment:
        """Record an explicit user rejection without deleting its evidence provenance."""
        assignment = self._session.get(TagAssignment, assignment_id)
        if assignment is None:
            raise TagError("tag_assignment_not_found", "The tag assignment does not exist.", 404)
        assignment.status = "rejected"
        return assignment

    def create_custom(self, *, source_id: int, label: str) -> TagAssignment:
        """Create or reuse a user label and make its assignment immediately accepted."""
        normalized = _normalized_label(label)
        definition = self._find_definition_by_label(normalized)
        if definition is None:
            definition = TagDefinition(
                slug=_custom_slug(normalized),
                label=normalized,
                facet=None,
                is_system=False,
            )
            self._session.add(definition)
            self._session.flush()
        assignment = TagAssignment(
            source_id=source_id,
            tag_id=definition.id,
            origin="user",
            status="accepted",
        )
        self._session.add(assignment)
        self._session.flush()
        return assignment

    def tree(self) -> list[TagDefinition]:
        """Return taxonomy rows in parent-first stable label order for later API/UI use."""
        self.ensure_system_taxonomy()
        return list(
            self._session.scalars(
                select(TagDefinition).order_by(
                    TagDefinition.facet, TagDefinition.parent_id, TagDefinition.label
                )
            )
        )

    def _definition_for_label(self, label: str) -> TagDefinition:
        normalized = _normalized_label(label)
        definition = self._find_definition_by_label(normalized)
        if definition is not None:
            return definition
        definition = TagDefinition(
            slug=_custom_slug(normalized),
            label=normalized,
            facet=None,
            is_system=False,
        )
        self._session.add(definition)
        self._session.flush()
        return definition

    def _find_definition_by_label(self, label: str) -> TagDefinition | None:
        return self._session.scalar(select(TagDefinition).where(TagDefinition.label == label))


def _normalized_label(value: str) -> str:
    label = value.strip()
    if not label or len(label) > 160:
        raise TagError("invalid_tag_label", "A tag label must be between 1 and 160 characters.")
    return label


def _custom_slug(label: str) -> str:
    """Generate a global, readable-enough slug without depending on locale transliteration."""
    readable = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-") or "custom"
    digest = hashlib.sha256(label.casefold().encode()).hexdigest()[:12]
    return f"{readable[:140]}-{digest}"

"""Server-only OpenAI-compatible derivation and grounded-chat boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

from app.config import Settings
from app.services.knowledge import SourceMaterial

DerivationKind = Literal["translation", "summary", "skill"]
MAX_PROMPT_CHARS = 24_000
MAX_COMPLETION_TOKENS = 1_200
MAX_COMPLETION_CHARS = 32_000
TRUNCATION_MARKER = "\n\n[Content truncated to fit the AI context budget.]"


@dataclass(frozen=True, slots=True)
class ProviderError(Exception):
    """A deliberately non-diagnostic failure safe to return from API routes."""

    code: str
    message: str
    status_code: int = 422

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class GeneratedContent:
    """Provider output plus the non-secret provenance to persist with it."""

    title: str
    markdown: str
    language: str
    model_metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    """A grounded completion and citations for sections actually in its prompt."""

    markdown: str
    citations: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class PreparedContext:
    """Bounded source-local input and its eligible citations."""

    text: str
    citations: tuple[dict[str, object], ...]


class AIService:
    """One OpenAI-compatible client with explicit, source-grounded prompts."""

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = _nonblank(settings.ai_base_url)
        if self._base_url is not None:
            self._base_url = self._base_url.rstrip("/")
        self._api_key = _nonblank(
            settings.ai_api_key.get_secret_value()
            if settings.ai_api_key is not None
            else None
        )
        self._model = _nonblank(settings.ai_model)
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0))

    async def aclose(self) -> None:
        """Close the service-owned or injected HTTP client deterministically."""
        await self._client.aclose()

    async def derive(
        self, material: SourceMaterial, kind: DerivationKind
    ) -> GeneratedContent:
        """Produce one traceable translation, summary, or reusable Skill document."""
        if not material.has_content:
            raise ProviderError(
                code="source_unavailable",
                message="The selected source has no imported material to derive from.",
            )
        instruction, title, language = _derivation_instruction(kind, material.title)
        prefix = f"{instruction}\n\n"
        context = _material_context(material, max_chars=MAX_PROMPT_CHARS - len(prefix))
        markdown = await self._complete(
            system=(
                "You transform supplied public source material into Markdown. "
                "Do not invent facts, sources, or quotations. Follow the requested task "
                "and preserve explicit source links."
            ),
            user=f"{prefix}{context.text}",
        )
        return GeneratedContent(
            title=title,
            markdown=markdown,
            language=language,
            model_metadata={"provider": "openai_compatible", "model": self._model_or_error()},
        )

    async def answer(self, material: SourceMaterial, question: str) -> GeneratedAnswer:
        """Answer only from the currently selected source and its own artifacts."""
        if not material.has_content:
            raise ProviderError(
                code="source_unavailable",
                message="The selected source has no imported material to answer from.",
            )
        prefix = f"Question: {question}\n\n"
        context = _material_context(material, max_chars=MAX_PROMPT_CHARS - len(prefix))
        markdown = await self._complete(
            system=(
                "Answer only from the supplied source sections. If the material does not "
                "support an answer, say so plainly. Do not use outside knowledge. Cite "
                "the supplied section labels in your Markdown response."
            ),
            user=f"{prefix}{context.text}",
        )
        return GeneratedAnswer(markdown=markdown, citations=context.citations)

    async def _complete(self, *, system: str, user: str) -> str:
        """Perform the sole provider request without exposing transport diagnostics."""
        base_url, api_key, model = self._configuration_or_error()
        try:
            response = await self._client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.2,
                    "max_tokens": MAX_COMPLETION_TOKENS,
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if (
                not isinstance(content, str)
                or not content.strip()
                or len(content) > MAX_COMPLETION_CHARS
            ):
                raise ValueError("empty completion")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError(
                code="provider_error",
                message="The AI provider could not complete the request.",
                status_code=502,
            ) from error
        return content.strip()

    def _configuration_or_error(self) -> tuple[str, str, str]:
        """Require a complete environment-only provider configuration."""
        if not all((self._base_url, self._api_key, self._model)):
            raise ProviderError(
                code="provider_not_configured",
                message="Configure an AI provider on the server to use this action.",
            )
        return self._base_url, self._api_key, self._model

    def _model_or_error(self) -> str:
        """Read the configured model only after the provider configuration check."""
        _, _, model = self._configuration_or_error()
        return model


def _derivation_instruction(
    kind: DerivationKind, source_title: str
) -> tuple[str, str, str]:
    """Return intentionally distinct model instructions and artifact metadata."""
    if kind == "translation":
        return (
            (
                "Translate the source into Chinese. Preserve Markdown headings, links, "
                "proper nouns, and technical terminology. Do not add analysis."
            ),
            f"{source_title} — 中文翻译",
            "zh",
        )
    if kind == "summary":
        return (
            (
                "Write a concise Chinese knowledge summary. Separate source-supported "
                "claims from interpretation, retain essential qualifications, and link the source."
            ),
            f"{source_title} — 知识摘要",
            "zh",
        )
    if kind == "skill":
        return (
            (
                "Create a Chinese reusable Skill Markdown document with sections: purpose, "
                "when to use, inputs, procedure, caveats, and source link. Ground every step "
                "in the supplied material and call out uncertainty."
            ),
            f"{source_title} — Distilled Skill",
            "zh",
        )
    raise ValueError(f"unsupported derivation kind: {kind}")


def _material_context(material: SourceMaterial, *, max_chars: int) -> PreparedContext:
    """Bound deterministic prompt context and retain citations for included sections only."""
    raw_header = (
        f"Source URL: {material.canonical_url}\n\n"
        f"Source title: {material.title}"
    )
    header = _truncate(raw_header, max_chars)
    remaining = max_chars - len(header)
    included = [header]
    citations: list[dict[str, object]] = []
    sections: list[tuple[str, str, dict[str, object]]] = [
        (
            "Original source",
            material.source_markdown
            if material.source_markdown.strip()
            else material.raw_text,
            {
                "source_id": material.id,
                "artifact_id": None,
                "url": material.canonical_url,
                "section": "Original source",
            },
        )
    ]
    sections.extend(
        (
            f"Artifact: {artifact.title}",
            artifact.markdown,
            {
                "source_id": material.id,
                "artifact_id": artifact.id,
                "url": material.canonical_url,
                "section": f"Artifact: {artifact.title}",
            },
        )
        for artifact in material.artifacts
        if artifact.markdown.strip()
    )
    for section, content, citation in sections:
        if not content.strip() or remaining <= 0:
            continue
        text = f"\n\n[{section}]\n{content}"
        if len(text) <= remaining:
            included.append(text)
            citations.append(citation)
            remaining -= len(text)
            continue
        available = remaining - len(f"\n\n[{section}]\n") - len(TRUNCATION_MARKER)
        if available > 0:
            included.append(f"\n\n[{section}]\n{content[:available]}{TRUNCATION_MARKER}")
            citations.append(citation)
        break
    return PreparedContext(text="".join(included), citations=tuple(citations))


def _nonblank(value: str | None) -> str | None:
    """Normalize configuration values without ever serializing a secret."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _truncate(value: str, limit: int) -> str:
    """Keep arbitrary imported metadata inside an exact character envelope."""
    if len(value) <= limit:
        return value
    if limit <= len(TRUNCATION_MARKER):
        return TRUNCATION_MARKER[:limit]
    return f"{value[: limit - len(TRUNCATION_MARKER)]}{TRUNCATION_MARKER}"

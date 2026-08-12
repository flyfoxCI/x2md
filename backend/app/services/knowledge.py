"""Persistence-backed knowledge-library workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.session import sessionmaker

from app.models import Artifact, KnowledgeNote, Source
from app.services.connectors.base import NormalizedSource
from app.services.url_safety import UnsafeUrlError, validate_public_url


@dataclass(frozen=True, slots=True)
class KnowledgeError(Exception):
    """A stable, safe domain error exposed by the knowledge API."""

    code: str
    message: str
    status_code: int


@dataclass(frozen=True, slots=True)
class SourcePage:
    """A page of sources and its unpaginated count."""

    items: list[Source]
    total: int


class ConnectorFetcher(Protocol):
    """The single connector capability the import workflow requires."""

    async def fetch(self, url: str) -> NormalizedSource:
        """Retrieve the URL as a normalized public source."""


type SessionFactory = sessionmaker[Session]


_ERROR_MESSAGES = {
    "artifact_not_found": "The requested artifact does not exist.",
    "provider_not_configured": "The requested provider is not configured.",
    "restricted_source": "The source is restricted or unavailable.",
    "source_unavailable": "The source is temporarily unavailable or could not be read.",
    "source_not_found": "The requested source does not exist.",
    "unsupported_url": "Enter a public HTTPS URL that this service can import.",
}
_UNSUPPORTED_REASONS = frozenset(
    {
        "unsafe_url",
        "unsupported_arxiv_url",
        "unsupported_github_url",
        "unsupported_huggingface_url",
        "unsupported_x_url",
        "unsupported_youtube_url",
    }
)
_RESTRICTED_REASONS = frozenset(
    {"private_repository", "restricted_repository", "restricted_source"}
)
_UNAVAILABLE_REASONS = frozenset(
    {
        "arxiv_http_status",
        "github_http_status",
        "http_status",
        "huggingface_http_status",
        "invalid_arxiv_response",
        "invalid_card_encoding",
        "invalid_charset",
        "invalid_oembed_response",
        "invalid_post_response",
        "invalid_readme_encoding",
        "invalid_repository_response",
        "metadata_unavailable",
        "network_error",
        "no_readable_content",
        "post_text_unavailable",
        "rate_limited",
        "readme_unavailable",
        "response_too_large",
        "unsupported_mime",
        "x_http_status",
        "x_oembed_http_status",
        "youtube_http_status",
    }
)


class KnowledgeService:
    """The only API-layer owner allowed to write sources and user edits."""

    def __init__(
        self,
        session: Session | None,
        router: ConnectorFetcher,
        *,
        import_session_factory: SessionFactory,
    ) -> None:
        self._session = session
        self._router = router
        self._import_session_factory = import_session_factory

    async def import_url(self, url: str) -> Source:
        """Fetch one public URL and persist its canonical source exactly once."""
        try:
            public_url = str(validate_public_url(url))
        except UnsafeUrlError as error:
            raise self._error("unsupported_url", 422) from error

        existing = self._find_imported_source(public_url)
        if existing is not None:
            return existing

        normalized = await self._router.fetch(public_url)
        if normalized.status == "blocked":
            raise self._error(_blocked_error(normalized.reason), 422)

        return await self._persist_import(normalized)

    def _find_imported_source(self, canonical_url: str) -> Source | None:
        """Use a short independent session scope for pre-import identity lookup."""
        with self._import_session_factory() as session:
            return session.scalar(
                select(Source).where(Source.canonical_url == canonical_url)
            )

    async def _persist_import(self, normalized: NormalizedSource) -> Source:
        """Recheck and persist after fetching without retaining a session during I/O."""
        with self._import_session_factory() as session:
            existing = session.scalar(
                select(Source).where(Source.canonical_url == normalized.canonical_url)
            )
            if existing is not None:
                return existing

            source = Source(
                canonical_url=normalized.canonical_url,
                platform=normalized.platform,
                title=normalized.title,
                author=normalized.author,
                published_at=normalized.published_at,
                raw_text=normalized.text,
                source_markdown=normalized.markdown,
                metadata_json=_source_metadata(normalized),
                import_status=normalized.status,
                failure_reason=normalized.reason,
            )
            await self._before_persist_source(source)
            session.add(source)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(Source).where(
                        Source.canonical_url == normalized.canonical_url
                    )
                )
                if existing is None:
                    raise
                return existing
            session.refresh(source)
            return source

    async def _before_persist_source(self, source: Source) -> None:
        """Offer tests a coordination seam before a source's unique-key insert."""

    def list_sources(
        self,
        *,
        query: str | None,
        platform: str | None,
        tag: str | None,
        page: int,
        page_size: int,
    ) -> SourcePage:
        """Search canonical titles and URLs, then return a stable page."""
        statement = select(Source)
        filters = []
        if query and (trimmed_query := query.strip()):
            pattern = f"%{trimmed_query}%"
            filters.append(
                or_(Source.title.ilike(pattern), Source.canonical_url.ilike(pattern))
            )
        if platform and (trimmed_platform := platform.strip()):
            filters.append(Source.platform == trimmed_platform)
        if tag and (trimmed_tag := tag.strip()):
            filters.append(_source_has_tag(trimmed_tag, self._read_session))
        if filters:
            statement = statement.where(*filters)

        total = self._read_session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        items = list(
            self._read_session.scalars(
                statement.order_by(Source.created_at.desc(), Source.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return SourcePage(items=items, total=total or 0)

    def get_source(self, source_id: int) -> Source:
        """Return a source with its append-only artifact history."""
        source = self._read_session.scalar(
            select(Source)
            .where(Source.id == source_id)
            .options(selectinload(Source.artifacts))
        )
        if source is None:
            raise self._error("source_not_found", 404)
        return source

    def create_user_edit(
        self,
        artifact_id: int,
        *,
        title: str | None,
        markdown: str,
        language: str | None,
    ) -> Artifact:
        """Append a user-authored artifact version without changing the original."""
        parent = self._read_session.get(Artifact, artifact_id)
        if parent is None:
            raise self._error("artifact_not_found", 404)
        artifact = Artifact(
            source_id=parent.source_id,
            kind="user_edit",
            title=title if title is not None else parent.title,
            markdown=markdown,
            language=language if language is not None else parent.language,
            parent_artifact_id=parent.id,
            model_metadata_json={},
        )
        self._read_session.add(artifact)
        self._read_session.commit()
        self._read_session.refresh(artifact)
        return artifact

    def get_artifact(self, artifact_id: int) -> Artifact:
        """Return a derived artifact or a safe not-found error."""
        artifact = self._read_session.get(Artifact, artifact_id)
        if artifact is None:
            raise self._error("artifact_not_found", 404)
        return artifact

    @staticmethod
    def _error(code: str, status_code: int) -> KnowledgeError:
        message = _ERROR_MESSAGES.get(code, "The source could not be imported safely.")
        return KnowledgeError(code=code, message=message, status_code=status_code)

    @property
    def _read_session(self) -> Session:
        """Require a request session only for synchronous library reads or edits."""
        if self._session is None:
            raise RuntimeError("this knowledge service has no request session")
        return self._session


def _source_has_tag(tag: str, session: Session) -> object:
    """Match a note tag with dialect-specific JSON operators under one API contract."""
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        tag_matches = cast(KnowledgeNote.tags_json, JSONB).contains(cast([tag], JSONB))
    else:
        json_values = func.json_each(KnowledgeNote.tags_json).table_valued("value")
        tag_matches = exists(
            select(1).select_from(json_values).where(json_values.c.value == tag)
        )
    return exists(
        select(1)
        .select_from(KnowledgeNote)
        .where(KnowledgeNote.source_id == Source.id, tag_matches)
    )


def _blocked_error(reason: str | None) -> str:
    """Map connector-private failure detail to a small documented public taxonomy."""
    if reason == "provider_not_configured":
        return "provider_not_configured"
    if reason in _UNSUPPORTED_REASONS:
        return "unsupported_url"
    if reason in _RESTRICTED_REASONS:
        return "restricted_source"
    if reason in _UNAVAILABLE_REASONS:
        return "source_unavailable"
    return "source_unavailable"


def _source_metadata(source: NormalizedSource) -> dict[str, object]:
    """Convert immutable connector mappings into JSON values accepted by SQLAlchemy."""
    metadata = _json_value(source.metadata)
    provenance = _json_value(source.provenance)
    assert isinstance(metadata, dict)
    assert isinstance(provenance, dict)
    return {**metadata, "provenance": provenance}


def _json_value(value: object) -> object:
    """Thaw connector metadata while retaining JSON-only shape guarantees."""
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value

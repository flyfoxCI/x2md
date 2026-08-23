"""Revision-pinned, bounded source-file collection for public GitHub repositories."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import httpx

from app.services.connectors.github import SafeHttpClientProtocol
from app.services.connectors.response_policy import validate_response_body
from app.services.research.collectors.base import ResearchableSource
from app.services.research.contracts import (
    CollectedEvidence,
    CollectionResult,
    collection_budget,
)
from app.services.url_safety import RateLimitExceededError, UnsafeUrlError

_JSON_MIME_TYPES = {"application/json"}
_TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "application/markdown",
    "application/json",
    "application/yaml",
    "text/yaml",
    "text/x-python",
    "text/x-c",
}
_MANIFEST_FILENAMES = {
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "requirements.txt",
    "poetry.lock",
    "uv.lock",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "dockerfile",
    "compose.yaml",
    "docker-compose.yml",
    "makefile",
}
_ENTRYPOINT_FILENAMES = {
    "main.py",
    "main.ts",
    "main.tsx",
    "main.js",
    "main.go",
    "main.rs",
    "app.py",
    "manage.py",
    "server.py",
    "index.ts",
    "index.tsx",
    "index.js",
}
_TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".kt",
    ".md",
    ".mjs",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
_VENDOR_PARTS = {".git", "bower_components", "node_modules", "vendor"}
_GENERATED_PARTS = {"build", "coverage", "dist", "target"}
_MAX_EXCLUSION_RECORDS = 200


class GitHubResearchCollector:
    """Study selected text files from one immutable Git commit, not just its README."""

    def __init__(self, client: SafeHttpClientProtocol, *, token: str | None = None) -> None:
        self._client = client
        self._token = token

    async def collect(self, source: ResearchableSource) -> CollectionResult:
        """Collect at most twenty eligible files and preserve honest coverage signals."""
        budget = collection_budget("github")
        repository = _repository_from_source(source)
        if repository is None:
            return _failure_result("invalid_repository")
        headers = {"accept": "application/vnd.github+json"}
        if self._token:
            headers["authorization"] = f"Bearer {self._token}"
        api_url = f"https://api.github.com/repos/{repository}"
        metadata_response, error = await _get_json(self._client, api_url, headers=headers)
        if error is not None:
            return _failure_result(error)
        branch = _string(metadata_response.get("default_branch"))
        if branch is None:
            return _failure_result("default_branch_unavailable")

        ref_url = f"{api_url}/git/ref/heads/{quote(branch, safe='')}"
        ref_response, error = await _get_json(self._client, ref_url, headers=headers)
        if error is not None:
            return _failure_result(error)
        reference = ref_response.get("object")
        sha = _string(reference.get("sha")) if isinstance(reference, Mapping) else None
        if sha is None:
            return _failure_result("revision_unavailable")

        tree_url = f"{api_url}/git/trees/{quote(sha, safe='')}?recursive=1"
        tree_response, error = await _get_json(self._client, tree_url, headers=headers)
        if error is not None:
            return _failure_result(error, source_revision=sha)
        raw_tree = tree_response.get("tree")
        if not isinstance(raw_tree, list):
            return _failure_result("invalid_tree_response", source_revision=sha)
        tree_truncated = tree_response.get("truncated") is True
        entries = _tree_entries(raw_tree)
        evidence, requests_used, exclusions_omitted = await self._collect_files(
            repository=repository,
            revision=sha,
            entries=entries,
            headers=headers,
        )
        excluded_count = sum(item.decision == "excluded" for item in evidence) + exclusions_omitted
        complete = not tree_truncated and excluded_count == 0
        coverage: dict[str, object] = {
            "complete": complete,
            "tree_truncated": tree_truncated,
            "tree_entry_count": len(entries),
            "included_count": sum(item.decision == "included" for item in evidence),
            "excluded_count": excluded_count,
            "exclusions_omitted_count": exclusions_omitted,
            "requests_used": requests_used,
            "request_limit": budget.max_requests,
        }
        if tree_truncated:
            coverage["reason"] = "tree_truncated"
        elif not complete:
            coverage["reason"] = "material_excluded"
        return CollectionResult(
            platform="github", source_revision=sha, evidence=tuple(evidence), coverage=coverage
        )

    async def _collect_files(
        self,
        *,
        repository: str,
        revision: str,
        entries: tuple[_TreeEntry, ...],
        headers: Mapping[str, str],
    ) -> tuple[list[CollectedEvidence], int, int]:
        """Select deterministic paths, keeping request and combined byte budgets strict."""
        budget = collection_budget("github")
        evidence: list[CollectedEvidence] = []
        exclusions_omitted = 0
        candidates: list[_TreeEntry] = []
        for entry in entries:
            reason = _exclusion_reason(entry.path)
            if reason is None:
                candidates.append(entry)
                continue
            exclusions_omitted += _append_exclusion(
                evidence,
                _excluded_evidence(repository, revision, entry, reason, len(evidence)),
            )
        candidates.sort(key=lambda item: (_priority(item.path), item.path.casefold(), item.path))

        bytes_used = 0
        file_requests = 0
        for entry in candidates:
            if file_requests >= budget.max_items:
                exclusions_omitted += _append_exclusion(
                    evidence,
                    _excluded_evidence(
                        repository, revision, entry, "item_limit", len(evidence)
                    ),
                )
                continue
            if entry.size is not None and entry.size > budget.max_content_bytes - bytes_used:
                exclusions_omitted += _append_exclusion(
                    evidence,
                    _excluded_evidence(
                        repository, revision, entry, "content_budget", len(evidence)
                    ),
                )
                continue
            if 3 + file_requests >= budget.max_requests:
                exclusions_omitted += _append_exclusion(
                    evidence,
                    _excluded_evidence(
                        repository, revision, entry, "request_budget", len(evidence)
                    ),
                )
                continue

            file_requests += 1
            raw_url = _raw_url(repository, revision, entry.path)
            try:
                response = await self._client.get_public(
                    raw_url, headers={"accept": "text/plain, text/markdown, application/json"}
                )
            except RateLimitExceededError:
                reason = "rate_limited"
            except UnsafeUrlError:
                reason = "unsafe_url"
            except httpx.RequestError:
                reason = "network_error"
            else:
                policy = validate_response_body(
                    response, allowed_mime_types=_TEXT_MIME_TYPES
                )
                if policy.reason is not None:
                    reason = policy.reason
                elif not 200 <= response.status_code < 300:
                    reason = "github_http_status"
                elif len(response.content) > budget.max_content_bytes - bytes_used:
                    reason = "content_budget"
                else:
                    try:
                        content = response.content.decode("utf-8")
                    except UnicodeDecodeError:
                        reason = "invalid_text_encoding"
                    else:
                        if not content.strip():
                            reason = "empty_content"
                        else:
                            evidence.append(
                                CollectedEvidence(
                                    locator=_locator(repository, revision, entry.path),
                                    kind="repository_file",
                                    ordinal=len(evidence),
                                    decision="included",
                                    title=entry.path,
                                    content=content,
                                    source_revision=revision,
                                )
                            )
                            bytes_used += len(response.content)
                            continue
            exclusions_omitted += _append_exclusion(
                evidence,
                _excluded_evidence(repository, revision, entry, reason, len(evidence)),
            )
        return evidence, 3 + file_requests, exclusions_omitted


@dataclass(frozen=True, slots=True)
class _TreeEntry:
    path: str
    size: int | None


async def _get_json(
    client: SafeHttpClientProtocol, url: str, *, headers: Mapping[str, str]
) -> tuple[Mapping[str, object], str | None]:
    """Fetch one GitHub API object and translate transport details into safe coverage."""
    try:
        response = await client.get_public(url, headers=dict(headers))
    except RateLimitExceededError:
        return {}, "rate_limited"
    except UnsafeUrlError:
        return {}, "unsafe_url"
    except httpx.RequestError:
        return {}, "network_error"
    policy = validate_response_body(response, allowed_mime_types=_JSON_MIME_TYPES)
    if policy.reason is not None:
        return {}, policy.reason
    if response.status_code in {401, 403, 404}:
        return {}, "restricted_repository"
    if not 200 <= response.status_code < 300:
        return {}, "github_http_status"
    try:
        payload = json.loads(response.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, "invalid_github_response"
    return (payload, None) if isinstance(payload, Mapping) else ({}, "invalid_github_response")


def _repository_from_source(source: ResearchableSource) -> str | None:
    metadata_repository = source.metadata_json.get("repository")
    if isinstance(metadata_repository, str) and _valid_repository(metadata_repository):
        return metadata_repository
    try:
        parsed = urlsplit(source.canonical_url)
    except ValueError:
        return None
    if parsed.hostname not in {"github.com", "www.github.com"}:
        return None
    parts = tuple(part for part in parsed.path.split("/") if part)
    repository = "/".join(parts) if len(parts) == 2 else ""
    return repository if _valid_repository(repository) else None


def _valid_repository(value: str) -> bool:
    parts = value.split("/")
    return len(parts) == 2 and all(part and part not in {".", ".."} for part in parts)


def _tree_entries(raw_tree: list[object]) -> tuple[_TreeEntry, ...]:
    entries: list[_TreeEntry] = []
    for value in raw_tree:
        if not isinstance(value, Mapping) or value.get("type") != "blob":
            continue
        path = _string(value.get("path"))
        if path is None or path.startswith("/") or ".." in path.split("/"):
            continue
        size = value.get("size")
        entries.append(_TreeEntry(path=path, size=size if isinstance(size, int) and size >= 0 else None))
    return tuple(entries)


def _exclusion_reason(path: str) -> str | None:
    parts = tuple(part.casefold() for part in path.split("/"))
    filename = parts[-1]
    if any(part in _VENDOR_PARTS for part in parts):
        return "vendor_or_dependency"
    if any(part in _GENERATED_PARTS for part in parts) or filename.endswith(".min.js"):
        return "minified_or_generated"
    if filename in _MANIFEST_FILENAMES or filename in _ENTRYPOINT_FILENAMES:
        return None
    if filename in {"readme", "readme.md", "readme.rst", "readme.txt"}:
        return None
    if "architecture" in filename or "design" in filename:
        return None
    if any(filename.endswith(suffix) for suffix in _TEXT_SUFFIXES):
        return None
    return "binary_or_unsupported"


def _priority(path: str) -> tuple[int, str]:
    filename = path.rsplit("/", 1)[-1].casefold()
    if filename in {"readme", "readme.md", "readme.rst", "readme.txt"}:
        return 0, path.casefold()
    if filename in _MANIFEST_FILENAMES:
        return 1, path.casefold()
    if filename in _ENTRYPOINT_FILENAMES:
        return 2, path.casefold()
    if "architecture" in filename or "design" in filename:
        return 3, path.casefold()
    return 4, path.casefold()


def _raw_url(repository: str, revision: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repository}/{revision}/{quote(path, safe='/')}"


def _locator(repository: str, revision: str, path: str) -> str:
    return f"github://{repository}@{revision}/{quote(path, safe='/')}"


def _excluded_evidence(
    repository: str,
    revision: str,
    entry: _TreeEntry,
    reason: str,
    ordinal: int,
) -> CollectedEvidence:
    return CollectedEvidence(
        locator=_locator(repository, revision, entry.path),
        kind="repository_file",
        ordinal=ordinal,
        decision="excluded",
        title=entry.path,
        source_revision=revision,
        exclusion_reason=reason,
    )


def _append_exclusion(evidence: list[CollectedEvidence], item: CollectedEvidence) -> int:
    """Bound stored exclusion detail while retaining its total in coverage metadata."""
    if sum(existing.decision == "excluded" for existing in evidence) >= _MAX_EXCLUSION_RECORDS:
        return 1
    evidence.append(item)
    return 0


def _failure_result(reason: str, *, source_revision: str | None = None) -> CollectionResult:
    return CollectionResult(
        platform="github",
        source_revision=source_revision,
        evidence=(),
        coverage={"complete": False, "reason": reason, "requests_used": 0},
    )


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None

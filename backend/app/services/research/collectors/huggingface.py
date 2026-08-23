"""Bounded configuration and source-file collection from public Hugging Face Hub repos."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import httpx

from app.services.connectors.huggingface import SafeHttpClientProtocol
from app.services.connectors.response_policy import validate_response_body
from app.services.research.collectors.base import ResearchableSource
from app.services.research.contracts import (
    CollectedEvidence,
    CollectionResult,
    collection_budget,
)
from app.services.url_safety import RateLimitExceededError, UnsafeUrlError

_TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "application/markdown",
    "application/json",
    "application/yaml",
    "text/yaml",
    "text/x-python",
}
_CONFIG_FILENAMES = {
    "config.json",
    "generation_config.json",
    "preprocessor_config.json",
    "tokenizer_config.json",
}
_TEXT_SUFFIXES = {".json", ".md", ".py", ".toml", ".yaml", ".yml"}
_PAYLOAD_SUFFIXES = {
    ".arrow",
    ".bin",
    ".ckpt",
    ".csv",
    ".gguf",
    ".h5",
    ".onnx",
    ".parquet",
    ".pt",
    ".pth",
    ".safetensors",
    ".tar",
    ".zip",
}
_MAX_EXCLUSION_RECORDS = 200


class HuggingFaceResearchCollector:
    """Read only card/config/source material, never Hub model weights or dataset payloads."""

    def __init__(self, client: SafeHttpClientProtocol) -> None:
        self._client = client

    async def collect(self, source: ResearchableSource) -> CollectionResult:
        """Fetch a revision-pinned siblings list then at most twelve small text files."""
        target = _target_from_source(source)
        if target is None:
            return _failure_result("invalid_huggingface_repository")
        repository_type, repository = target
        api_url = f"https://huggingface.co/api/{repository_type}s/{repository}"
        try:
            response = await self._client.get_public(
                api_url, headers={"accept": "application/json"}
            )
        except RateLimitExceededError:
            return _failure_result("rate_limited")
        except UnsafeUrlError:
            return _failure_result("unsafe_url")
        except httpx.RequestError:
            return _failure_result("network_error")
        policy = validate_response_body(response, allowed_mime_types={"application/json"})
        if policy.reason is not None:
            return _failure_result(policy.reason)
        if response.status_code in {401, 403, 404}:
            return _failure_result("restricted_repository")
        if not 200 <= response.status_code < 300:
            return _failure_result("huggingface_http_status")
        try:
            payload = json.loads(response.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _failure_result("invalid_repository_response")
        if not isinstance(payload, Mapping):
            return _failure_result("invalid_repository_response")
        gated = payload.get("gated")
        if payload.get("private") is True or not (
            gated is None
            or gated is False
            or (isinstance(gated, str) and gated in {"", "false", "False"})
        ):
            return _failure_result("restricted_repository")
        revision = _string(payload.get("sha"))
        if revision is None:
            return _failure_result("revision_unavailable")
        siblings = _siblings(payload.get("siblings"))
        evidence, exclusions_omitted, file_requests = await self._collect_files(
            repository_type=repository_type,
            repository=repository,
            revision=revision,
            siblings=siblings,
        )
        excluded_count = sum(item.decision == "excluded" for item in evidence) + exclusions_omitted
        complete = excluded_count == 0
        coverage: dict[str, object] = {
            "complete": complete,
            "included_count": sum(item.decision == "included" for item in evidence),
            "excluded_count": excluded_count,
            "exclusions_omitted_count": exclusions_omitted,
            "requests_used": 1 + file_requests,
            "sibling_count": len(siblings),
        }
        if not complete:
            coverage["reason"] = "material_excluded"
        return CollectionResult(
            platform="huggingface",
            source_revision=revision,
            evidence=tuple(evidence),
            coverage=coverage,
        )

    async def _collect_files(
        self,
        *,
        repository_type: str,
        repository: str,
        revision: str,
        siblings: tuple[_Sibling, ...],
    ) -> tuple[list[CollectedEvidence], int, int]:
        budget = collection_budget("huggingface")
        evidence: list[CollectedEvidence] = []
        exclusions_omitted = 0
        eligible: list[_Sibling] = []
        for sibling in siblings:
            reason = _exclusion_reason(sibling.filename)
            if reason is None:
                eligible.append(sibling)
                continue
            exclusions_omitted += _append_exclusion(
                evidence,
                _excluded_evidence(repository_type, repository, revision, sibling, reason, len(evidence)),
            )
        eligible.sort(key=lambda item: (_priority(item.filename), item.filename.casefold(), item.filename))
        bytes_used = 0
        requests_used = 0
        for sibling in eligible:
            if requests_used >= budget.max_items:
                exclusions_omitted += _append_exclusion(
                    evidence,
                    _excluded_evidence(repository_type, repository, revision, sibling, "item_limit", len(evidence)),
                )
                continue
            if sibling.size is not None and sibling.size > budget.max_content_bytes - bytes_used:
                exclusions_omitted += _append_exclusion(
                    evidence,
                    _excluded_evidence(repository_type, repository, revision, sibling, "content_budget", len(evidence)),
                )
                continue
            requests_used += 1
            raw_url = _raw_url(repository_type, repository, revision, sibling.filename)
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
                    response,
                    allowed_mime_types=_TEXT_MIME_TYPES,
                    max_response_bytes=budget.max_content_bytes - bytes_used,
                )
                if policy.reason is not None:
                    reason = policy.reason
                elif not 200 <= response.status_code < 300:
                    reason = "huggingface_http_status"
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
                                    locator=_locator(repository_type, repository, revision, sibling.filename),
                                    kind="hub_file",
                                    ordinal=len(evidence),
                                    decision="included",
                                    title=sibling.filename,
                                    content=content,
                                    source_revision=revision,
                                )
                            )
                            bytes_used += len(response.content)
                            continue
            exclusions_omitted += _append_exclusion(
                evidence,
                _excluded_evidence(repository_type, repository, revision, sibling, reason, len(evidence)),
            )
        return evidence, exclusions_omitted, requests_used


@dataclass(frozen=True, slots=True)
class _Sibling:
    filename: str
    size: int | None


def _target_from_source(source: ResearchableSource) -> tuple[str, str] | None:
    metadata_type = source.metadata_json.get("repository_type")
    metadata_id = source.metadata_json.get("id")
    if metadata_type in {"model", "dataset"} and isinstance(metadata_id, str) and _valid_repository(metadata_id):
        return metadata_type, metadata_id
    try:
        parsed = urlsplit(source.canonical_url)
    except ValueError:
        return None
    if parsed.hostname not in {"huggingface.co", "www.huggingface.co"}:
        return None
    parts = tuple(part for part in parsed.path.split("/") if part)
    if len(parts) == 2:
        repository = "/".join(parts)
        return ("model", repository) if _valid_repository(repository) else None
    if len(parts) == 3 and parts[0] == "datasets":
        repository = "/".join(parts[1:])
        return ("dataset", repository) if _valid_repository(repository) else None
    return None


def _valid_repository(value: str) -> bool:
    parts = value.split("/")
    return len(parts) == 2 and all(part and part not in {".", ".."} for part in parts)


def _siblings(value: object) -> tuple[_Sibling, ...]:
    if not isinstance(value, list):
        return ()
    siblings: list[_Sibling] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        filename = _string(item.get("rfilename"))
        if filename is None or filename.startswith("/") or ".." in filename.split("/"):
            continue
        size = item.get("size")
        siblings.append(_Sibling(filename, size if isinstance(size, int) and size >= 0 else None))
    return tuple(siblings)


def _exclusion_reason(filename: str) -> str | None:
    lowered = filename.casefold()
    basename = lowered.rsplit("/", 1)[-1]
    if any(lowered.endswith(suffix) for suffix in _PAYLOAD_SUFFIXES) or lowered.endswith(".jsonl"):
        return "weight_or_payload"
    if basename == "readme.md" or basename in _CONFIG_FILENAMES:
        return None
    if any(lowered.endswith(suffix) for suffix in _TEXT_SUFFIXES):
        return None
    return "binary_or_unsupported"


def _priority(filename: str) -> int:
    basename = filename.casefold().rsplit("/", 1)[-1]
    if basename == "readme.md":
        return 0
    if basename in _CONFIG_FILENAMES:
        return 1
    if basename.endswith(".py"):
        return 2
    return 3


def _raw_url(repository_type: str, repository: str, revision: str, filename: str) -> str:
    prefix = "datasets/" if repository_type == "dataset" else ""
    return f"https://huggingface.co/{prefix}{repository}/raw/{quote(revision, safe='')}/{quote(filename, safe='/')}"


def _locator(repository_type: str, repository: str, revision: str, filename: str) -> str:
    return f"huggingface://{repository_type}/{repository}@{revision}/{quote(filename, safe='/')}"


def _excluded_evidence(
    repository_type: str,
    repository: str,
    revision: str,
    sibling: _Sibling,
    reason: str,
    ordinal: int,
) -> CollectedEvidence:
    return CollectedEvidence(
        locator=_locator(repository_type, repository, revision, sibling.filename),
        kind="hub_file",
        ordinal=ordinal,
        decision="excluded",
        title=sibling.filename,
        source_revision=revision,
        exclusion_reason=reason,
    )


def _append_exclusion(evidence: list[CollectedEvidence], item: CollectedEvidence) -> int:
    if sum(existing.decision == "excluded" for existing in evidence) >= _MAX_EXCLUSION_RECORDS:
        return 1
    evidence.append(item)
    return 0


def _failure_result(reason: str) -> CollectionResult:
    return CollectionResult(
        platform="huggingface",
        source_revision=None,
        evidence=(),
        coverage={"complete": False, "reason": reason, "requests_used": 0},
    )


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None

"""Fixture tests for constrained public YouTube source handling."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from app.services.connectors.router import ConnectorRouter
from app.services.connectors.web import WebConnector
from app.services.connectors.youtube import (
    YouTubeConnector,
    YouTubeTimedTextTranscriptProvider,
)
from app.services.url_safety import RateLimitExceededError, UnsafeUrlError


@dataclass(frozen=True)
class FakeResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes


class FakeSafeHttpClient:
    def __init__(self, responses: Mapping[str, FakeResponse | BaseException]) -> None:
        self._responses = responses
        self.requests: list[tuple[str, Mapping[str, object]]] = []

    async def get_public(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append((url, kwargs))
        response = self._responses[url]
        if isinstance(response, BaseException):
            raise response
        return response


class FakeTranscriptProvider:
    def __init__(self, transcript: str | None | BaseException) -> None:
        self._transcript = transcript
        self.requests: list[str] = []

    async def get_public_transcript(self, video_id: str) -> str | None:
        self.requests.append(video_id)
        if isinstance(self._transcript, BaseException):
            raise self._transcript
        return self._transcript


def _fixture_bytes(name: str) -> bytes:
    return (Path(__file__).parents[1] / "fixtures" / name).read_bytes()


def _oembed_url(video_id: str) -> str:
    return (
        "https://www.youtube.com/oembed?url=https%3A%2F%2Fwww.youtube.com%2Fwatch"
        f"%3Fv%3D{video_id}&format=json"
    )


def _timedtext_url(video_id: str, language: str = "en") -> str:
    return f"https://www.youtube.com/api/timedtext?v={video_id}&lang={language}"


@pytest.mark.asyncio
async def test_youtube_connector_normalizes_only_an_injected_public_transcript() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    provider = FakeTranscriptProvider(_fixture_bytes("youtube_transcript.txt").decode())
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("youtube_oembed.json"),
            )
        }
    )

    source = await YouTubeConnector(client, transcript_provider=provider).fetch(
        f"https://www.youtube.com/watch?v={video_id}&feature=shared"
    )

    transcript = _fixture_bytes("youtube_transcript.txt").decode()
    assert source.status == "ready"
    assert source.platform == "youtube"
    assert source.canonical_url == f"https://www.youtube.com/watch?v={video_id}"
    assert source.title == "Inspectable Reasoning in Practice"
    assert source.author == "Expert Studio"
    assert source.text == transcript
    assert (
        source.markdown
        == f"# Inspectable Reasoning in Practice\n\n## Transcript\n\n{transcript}"
    )
    assert source.metadata == {
        "author_url": "https://www.youtube.com/@expertstudio",
        "provider": "YouTube",
        "video_id": video_id,
    }
    assert source.provenance == {
        "metadata": "youtube_oembed",
        "transcript": "public_provider",
    }
    assert provider.requests == [video_id]
    assert client.requests == [
        (_oembed_url(video_id), {"headers": {"accept": "application/json"}})
    ]


@pytest.mark.asyncio
async def test_youtube_connector_returns_metadata_only_partial_when_captions_are_unavailable() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    provider = FakeTranscriptProvider(None)
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("youtube_oembed.json"),
            )
        }
    )

    source = await YouTubeConnector(client, transcript_provider=provider).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )

    assert source.status == "partial"
    assert source.reason == "transcript_unavailable"
    assert source.title == "Inspectable Reasoning in Practice"
    assert source.text == ""
    assert source.markdown == ""
    assert source.metadata["video_id"] == video_id
    assert provider.requests == [video_id]


@pytest.mark.asyncio
async def test_youtube_connector_default_provider_keeps_metadata_only_when_no_public_captions_exist() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("youtube_oembed.json"),
            ),
            _timedtext_url(video_id): FakeResponse(
                200,
                {"content-type": "text/xml; charset=utf-8"},
                _fixture_bytes("youtube_timedtext_empty.xml"),
            ),
        }
    )

    source = await YouTubeConnector(client).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )

    assert source.status == "partial"
    assert source.reason == "transcript_unavailable"
    assert source.text == ""
    assert source.provenance == {
        "metadata": "youtube_oembed",
        "transcript": "public_provider",
    }
    assert client.requests[-1] == (
        _timedtext_url(video_id),
        {"headers": {"accept": "application/xml, text/xml;q=0.9"}},
    )


@pytest.mark.asyncio
async def test_youtube_timed_text_provider_normalizes_only_public_xml_text_nodes() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    client = FakeSafeHttpClient(
        {
            _timedtext_url(video_id): FakeResponse(
                200,
                {"content-type": "text/xml; charset=utf-8"},
                _fixture_bytes("youtube_timedtext.xml"),
            )
        }
    )

    transcript = await YouTubeTimedTextTranscriptProvider(client).get_public_transcript(
        video_id
    )

    assert transcript == "Welcome & hello. Second public caption."
    assert client.requests == [
        (
            _timedtext_url(video_id),
            {"headers": {"accept": "application/xml, text/xml;q=0.9"}},
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "caption_xml",
    [
        b"<!DOCTYPE transcript [<!ENTITY nested 'must-not-expand'>]><transcript><text>&nested;</text></transcript>",
        b"<error><text>not a transcript</text></error>",
    ],
)
async def test_youtube_timed_text_provider_rejects_entities_and_non_transcript_roots(
    caption_xml: bytes,
) -> None:
    video_id = "dQw4w9WgXcQ"
    client = FakeSafeHttpClient(
        {
            _timedtext_url(video_id): FakeResponse(
                200, {"content-type": "text/xml"}, caption_xml
            )
        }
    )

    transcript = await YouTubeTimedTextTranscriptProvider(client).get_public_transcript(
        video_id
    )

    assert transcript is None


@pytest.mark.asyncio
async def test_youtube_timed_text_provider_rejects_utf16_internal_entities_without_expansion() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    caption_xml = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        "<!DOCTYPE transcript [<!ENTITY nested 'must-not-expand'>]>"
        "<transcript><text>&nested;</text></transcript>"
    ).encode("utf-16")
    client = FakeSafeHttpClient(
        {
            _timedtext_url(video_id): FakeResponse(
                200, {"content-type": "text/xml"}, caption_xml
            )
        }
    )

    transcript = await YouTubeTimedTextTranscriptProvider(client).get_public_transcript(
        video_id
    )

    assert transcript is None


@pytest.mark.asyncio
async def test_youtube_timed_text_provider_honors_xml_declared_encoding() -> None:
    video_id = "dQw4w9WgXcQ"
    caption_xml = (
        b'<?xml version="1.0" encoding="ISO-8859-1"?>'
        b"<transcript><text>Caf\xe9 caption.</text></transcript>"
    )
    client = FakeSafeHttpClient(
        {
            _timedtext_url(video_id): FakeResponse(
                200, {"content-type": "text/xml"}, caption_xml
            )
        }
    )

    transcript = await YouTubeTimedTextTranscriptProvider(client).get_public_transcript(
        video_id
    )

    assert transcript == "Café caption."


@pytest.mark.asyncio
async def test_youtube_connector_treats_unknown_timed_text_xml_codec_as_unavailable() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    caption_xml = (
        b'<?xml version="1.0" encoding="unknown-xml-codec"?>'
        b"<transcript><text>Unparseable caption.</text></transcript>"
    )
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("youtube_oembed.json"),
            ),
            _timedtext_url(video_id): FakeResponse(
                200, {"content-type": "text/xml"}, caption_xml
            ),
        }
    )

    source = await YouTubeConnector(client).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )

    assert source.status == "partial"
    assert source.reason == "transcript_unavailable"
    assert source.text == ""


@pytest.mark.asyncio
async def test_youtube_timed_text_provider_returns_none_for_empty_or_malformed_public_caption_documents() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    client = FakeSafeHttpClient(
        {
            _timedtext_url(video_id): FakeResponse(
                200,
                {"content-type": "text/xml"},
                _fixture_bytes("youtube_timedtext_empty.xml"),
            )
        }
    )

    transcript = await YouTubeTimedTextTranscriptProvider(client).get_public_transcript(
        video_id
    )

    assert transcript is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "headers", "content"),
    [
        (404, {"content-type": "text/xml"}, b"missing"),
        (200, {"content-type": "text/html"}, b"<html>not captions</html>"),
        (200, {"content-type": "text/xml"}, b"<transcript><text>broken"),
    ],
)
async def test_youtube_timed_text_provider_returns_none_for_unavailable_or_invalid_caption_responses(
    status_code: int, headers: Mapping[str, str], content: bytes
) -> None:
    video_id = "dQw4w9WgXcQ"
    client = FakeSafeHttpClient(
        {_timedtext_url(video_id): FakeResponse(status_code, headers, content)}
    )

    transcript = await YouTubeTimedTextTranscriptProvider(client).get_public_transcript(
        video_id
    )

    assert transcript is None


@pytest.mark.asyncio
async def test_youtube_connector_treats_ttml_captions_as_unavailable_until_ttml_is_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_id = "dQw4w9WgXcQ"
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("youtube_oembed.json"),
            ),
            _timedtext_url(video_id): FakeResponse(
                200,
                {"content-type": "application/ttml+xml"},
                b"<tt><body><p>Unsupported caption representation.</p></body></tt>",
            ),
        }
    )
    monkeypatch.setattr(
        "app.services.connectors.youtube.ElementTree.fromstring",
        lambda _: (_ for _ in ()).throw(AssertionError("TTML must not be parsed")),
    )

    source = await YouTubeConnector(client).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )

    assert source.status == "partial"
    assert source.reason == "transcript_unavailable"
    assert source.text == ""


@pytest.mark.asyncio
async def test_youtube_connector_blocks_restricted_oembed_responses_before_transcript_lookup() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    provider = FakeTranscriptProvider("must not be used")
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                403,
                {"content-type": "application/json"},
                json.dumps({"error": "forbidden"}).encode(),
            )
        }
    )

    source = await YouTubeConnector(client, transcript_provider=provider).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )

    assert source.status == "blocked"
    assert source.reason == "restricted_source"
    assert source.text == ""
    assert provider.requests == []
    assert source.metadata == {"content_type": "application/json", "http_status": 403}


@pytest.mark.asyncio
async def test_youtube_connector_maps_oembed_429_to_rate_limited_after_response_policy() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    provider = FakeTranscriptProvider("must not be used")
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                429,
                {"content-type": "application/json"},
                json.dumps({"error": "limited"}).encode(),
            )
        }
    )

    source = await YouTubeConnector(client, transcript_provider=provider).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )

    assert source.status == "blocked"
    assert source.reason == "rate_limited"
    assert provider.requests == []


@pytest.mark.asyncio
async def test_youtube_connector_maps_timed_text_429_to_rate_limited_after_response_policy() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("youtube_oembed.json"),
            ),
            _timedtext_url(video_id): FakeResponse(
                429,
                {"content-type": "text/xml"},
                b"<transcript />",
            ),
        }
    )

    source = await YouTubeConnector(client).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )

    assert source.status == "blocked"
    assert source.reason == "rate_limited"
    assert source.text == ""
    assert source.markdown == ""


@pytest.mark.asyncio
async def test_youtube_connector_blocks_unsafe_timed_text_lookup_after_metadata() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("youtube_oembed.json"),
            ),
            _timedtext_url(video_id): UnsafeUrlError(),
        }
    )

    source = await YouTubeConnector(client).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )

    assert source.status == "blocked"
    assert source.reason == "unsafe_url"
    assert source.text == ""
    assert source.metadata["video_id"] == video_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "reason"),
    [
        ({"content-type": "text/html"}, "unsupported_mime"),
        (
            {
                "content-type": "application/json",
                "content-length": str(5 * 1024 * 1024 + 1),
            },
            "response_too_large",
        ),
    ],
)
async def test_youtube_connector_applies_response_policy_before_caption_lookup(
    headers: Mapping[str, str], reason: str
) -> None:
    video_id = "dQw4w9WgXcQ"
    provider = FakeTranscriptProvider("must not be used")
    client = FakeSafeHttpClient(
        {_oembed_url(video_id): FakeResponse(503, headers, b"unavailable")}
    )

    source = await YouTubeConnector(client, transcript_provider=provider).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )

    assert source.status == "blocked"
    assert source.reason == reason
    assert source.text == ""
    assert provider.requests == []
    assert source.metadata["http_status"] == 503


@pytest.mark.asyncio
async def test_youtube_connector_maps_rate_limits_and_rejects_unsafe_urls_without_reflection() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    client = FakeSafeHttpClient({_oembed_url(video_id): RateLimitExceededError()})

    limited = await YouTubeConnector(client).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )
    unsafe = await YouTubeConnector(FakeSafeHttpClient({})).fetch(
        "https://user:secret@www.youtube.com/watch?v=dQw4w9WgXcQ"
    )

    assert limited.status == "blocked"
    assert limited.reason == "rate_limited"
    assert unsafe.status == "blocked"
    assert unsafe.reason == "unsafe_url"
    assert "secret" not in repr(unsafe)


@pytest.mark.asyncio
async def test_youtube_connector_maps_transcript_provider_rate_limits() -> None:
    video_id = "dQw4w9WgXcQ"
    provider = FakeTranscriptProvider(RateLimitExceededError())
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("youtube_oembed.json"),
            )
        }
    )

    source = await YouTubeConnector(client, transcript_provider=provider).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )

    assert source.status == "blocked"
    assert source.reason == "rate_limited"
    assert source.text == ""


@pytest.mark.asyncio
async def test_youtube_connector_blocks_invalid_or_unsupported_video_urls_without_fetching() -> (
    None
):
    client = FakeSafeHttpClient({})
    connector = YouTubeConnector(client)
    router = ConnectorRouter(
        generic_connector=WebConnector(client), connectors=(connector,)
    )

    source = await router.fetch("https://youtube.com/playlist?list=PL123")

    assert router.select("https://youtube.com/playlist?list=PL123") is connector
    assert source.status == "blocked"
    assert source.reason == "unsupported_youtube_url"
    assert client.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://youtube.com/watch/anything?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&v=AAAAAAAAAAA",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtube.com/embed/dQw4w9WgXcQ",
    ],
)
async def test_youtube_connector_rejects_ambiguous_or_noncanonical_watch_paths_without_fetching(
    url: str,
) -> None:
    client = FakeSafeHttpClient({})

    source = await YouTubeConnector(client).fetch(url)

    assert source.status == "blocked"
    assert source.reason == "unsupported_youtube_url"
    assert client.requests == []


@pytest.mark.asyncio
async def test_youtube_connector_accepts_a_once_decoded_valid_video_id() -> None:
    video_id = "dQw4w9WgXcQ"
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("youtube_oembed.json"),
            )
        }
    )

    source = await YouTubeConnector(
        client, transcript_provider=FakeTranscriptProvider(None)
    ).fetch("https://youtube.com/watch?v=dQw4w9WgXc%51")

    assert source.status == "partial"
    assert source.reason == "transcript_unavailable"
    assert source.canonical_url == f"https://www.youtube.com/watch?v={video_id}"


@pytest.mark.asyncio
async def test_youtube_connector_maps_transcript_transport_failure_to_no_caption_partial() -> (
    None
):
    video_id = "dQw4w9WgXcQ"
    provider = FakeTranscriptProvider(httpx.ConnectError("unavailable"))
    client = FakeSafeHttpClient(
        {
            _oembed_url(video_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("youtube_oembed.json"),
            )
        }
    )

    source = await YouTubeConnector(client, transcript_provider=provider).fetch(
        f"https://www.youtube.com/watch?v={video_id}"
    )

    assert source.status == "partial"
    assert source.reason == "transcript_unavailable"
    assert source.text == ""

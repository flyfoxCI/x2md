import httpx
import pytest

from app.config import Settings
from app.main import create_app


async def get_health_response() -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()),
        base_url="http://testserver",
    ) as client:
        return await client.get("/api/health")


@pytest.mark.asyncio
async def test_health_hides_provider_secret(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_API_KEY", "test-secret")
    monkeypatch.setenv("AI_MODEL", "test-model")

    response = await get_health_response()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "uninitialized",
        "aiConfigured": True,
    }
    assert "test-secret" not in response.text


@pytest.mark.asyncio
async def test_health_does_not_report_key_only_provider_as_configured(monkeypatch):
    """A secret alone cannot make the OpenAI-compatible adapter usable."""
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("APP_AI_BASE_URL", raising=False)
    monkeypatch.setenv("AI_API_KEY", "key-only-secret")
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.delenv("APP_AI_MODEL", raising=False)

    response = await get_health_response()

    assert response.status_code == 200
    assert response.json()["aiConfigured"] is False
    assert "key-only-secret" not in response.text


@pytest.mark.asyncio
async def test_health_reports_unconfigured_provider(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("APP_AI_API_KEY", raising=False)

    response = await get_health_response()

    assert response.status_code == 200
    assert response.json()["aiConfigured"] is False


def test_settings_read_direct_and_prefixed_environment_aliases(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///direct.db")
    monkeypatch.setenv("AI_BASE_URL", "https://ai.example.test/v1")
    monkeypatch.setenv("AI_API_KEY", "direct-key")
    monkeypatch.setenv("AI_MODEL", "direct-model")
    monkeypatch.setenv("X_BEARER_TOKEN", "direct-x-token")
    monkeypatch.setenv("GITHUB_TOKEN", "direct-github-token")

    direct_settings = Settings()

    assert direct_settings.database_url == "sqlite:///direct.db"
    assert direct_settings.ai_base_url == "https://ai.example.test/v1"
    assert direct_settings.ai_api_key.get_secret_value() == "direct-key"
    assert direct_settings.ai_model == "direct-model"
    assert direct_settings.x_bearer_token.get_secret_value() == "direct-x-token"
    assert direct_settings.github_token.get_secret_value() == "direct-github-token"
    assert "direct-github-token" not in repr(direct_settings)

    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.delenv("AI_BASE_URL")
    monkeypatch.delenv("AI_API_KEY")
    monkeypatch.delenv("AI_MODEL")
    monkeypatch.delenv("X_BEARER_TOKEN")
    monkeypatch.delenv("GITHUB_TOKEN")
    monkeypatch.setenv("APP_DATABASE_URL", "sqlite:///prefixed.db")
    monkeypatch.setenv("APP_AI_BASE_URL", "https://prefixed.example.test/v1")
    monkeypatch.setenv("APP_AI_API_KEY", "prefixed-key")
    monkeypatch.setenv("APP_AI_MODEL", "prefixed-model")
    monkeypatch.setenv("APP_X_BEARER_TOKEN", "prefixed-x-token")
    monkeypatch.setenv("APP_GITHUB_TOKEN", "prefixed-github-token")

    prefixed_settings = Settings()

    assert prefixed_settings.database_url == "sqlite:///prefixed.db"
    assert prefixed_settings.ai_base_url == "https://prefixed.example.test/v1"
    assert prefixed_settings.ai_api_key.get_secret_value() == "prefixed-key"
    assert prefixed_settings.ai_model == "prefixed-model"
    assert prefixed_settings.x_bearer_token.get_secret_value() == "prefixed-x-token"
    assert prefixed_settings.github_token.get_secret_value() == "prefixed-github-token"
    assert "prefixed-github-token" not in repr(prefixed_settings)

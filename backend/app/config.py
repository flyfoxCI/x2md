"""Server-side runtime configuration."""

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration sourced exclusively from the process environment."""

    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    app_name: str = "Expert Content Studio API"
    database_url: str = Field(
        default="sqlite:///./expert-content-studio.db",
        validation_alias=AliasChoices("DATABASE_URL", "APP_DATABASE_URL"),
        repr=False,
    )
    ai_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AI_BASE_URL", "APP_AI_BASE_URL"),
    )
    ai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("AI_API_KEY", "APP_AI_API_KEY"),
    )
    ai_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AI_MODEL", "APP_AI_MODEL"),
    )
    x_bearer_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("X_BEARER_TOKEN", "APP_X_BEARER_TOKEN"),
    )
    github_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GITHUB_TOKEN", "APP_GITHUB_TOKEN"),
    )

    @property
    def ai_configured(self) -> bool:
        """Return whether an AI provider key is available without exposing it."""
        return bool(self.ai_api_key and self.ai_api_key.get_secret_value())

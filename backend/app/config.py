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
    auth_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("AUTH_ENABLED", "APP_AUTH_ENABLED"),
    )
    auth_initial_admin_username: str = Field(
        default="admin",
        min_length=1,
        max_length=128,
        validation_alias=AliasChoices(
            "AUTH_INITIAL_ADMIN_USERNAME", "APP_AUTH_INITIAL_ADMIN_USERNAME"
        ),
    )
    auth_initial_admin_password: SecretStr | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "AUTH_INITIAL_ADMIN_PASSWORD", "APP_AUTH_INITIAL_ADMIN_PASSWORD"
        ),
    )
    auth_session_ttl_seconds: int = Field(
        default=43_200,
        ge=900,
        le=2_592_000,
        validation_alias=AliasChoices(
            "AUTH_SESSION_TTL_SECONDS", "APP_AUTH_SESSION_TTL_SECONDS"
        ),
    )
    auth_cookie_secure: bool = Field(
        default=True,
        validation_alias=AliasChoices("AUTH_COOKIE_SECURE", "APP_AUTH_COOKIE_SECURE"),
    )

    @property
    def ai_configured(self) -> bool:
        """Return whether the complete server-only provider contract is usable."""
        return bool(
            self.ai_base_url
            and self.ai_base_url.strip()
            and self.ai_api_key
            and self.ai_api_key.get_secret_value().strip()
            and self.ai_model
            and self.ai_model.strip()
        )

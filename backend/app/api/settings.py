"""Non-secret persisted presentation preferences."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.dependencies import DatabaseSession
from app.models import AppSetting

router = APIRouter(prefix="/api/settings", tags=["settings"])


class PresentationSettings(BaseModel):
    """The only browser-visible application preferences in the first release."""

    model_config = ConfigDict(extra="forbid")

    theme: Literal["system", "light", "dark"] = "system"
    preview_device: Literal["desktop", "mobile"] = "desktop"


class SettingsPatch(BaseModel):
    """Restrict writes to a typed allow-list of non-secret display preferences."""

    model_config = ConfigDict(extra="forbid")

    presentation: PresentationSettings


class SettingsRead(BaseModel):
    """Safe settings response: configuration state, never credential values."""

    ai_configured: bool = Field(serialization_alias="aiConfigured")
    presentation: PresentationSettings


def _presentation(session: Session) -> PresentationSettings:
    """Read one typed preference record with safe defaults for a fresh database."""
    setting = session.get(AppSetting, "presentation")
    if setting is None:
        return PresentationSettings()
    return PresentationSettings.model_validate(setting.value_json)


@router.get("", response_model=SettingsRead)
def get_settings(request: Request, session: DatabaseSession) -> SettingsRead:
    """Return browser-safe display configuration and provider availability only."""
    return SettingsRead(
        ai_configured=request.app.state.settings.ai_configured,
        presentation=_presentation(session),
    )


@router.patch("", response_model=SettingsRead)
def update_settings(
    request: Request, payload: SettingsPatch, session: DatabaseSession
) -> SettingsRead:
    """Persist a complete replacement of the browser-visible presentation settings."""
    setting = session.get(AppSetting, "presentation")
    values = payload.presentation.model_dump()
    if setting is None:
        setting = AppSetting(key="presentation", value_json=values)
        session.add(setting)
    else:
        setting.value_json = values
    session.commit()
    return SettingsRead(
        ai_configured=request.app.state.settings.ai_configured,
        presentation=payload.presentation,
    )

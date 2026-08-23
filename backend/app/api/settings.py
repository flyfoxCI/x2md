"""Non-secret persisted presentation preferences."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import DatabaseSession
from app.models import AppSetting

router = APIRouter(prefix="/api/settings", tags=["settings"])


class PresentationSettings(BaseModel):
    """The only browser-visible application preferences in the first release."""

    model_config = ConfigDict(extra="forbid")

    theme: Literal["system", "light", "dark"] = "system"
    preview_device: Literal["desktop", "mobile"] = "desktop"


class ResearchSettings(BaseModel):
    """An opt-in server-side queue preference exposed without operational details."""

    model_config = ConfigDict(extra="forbid")

    auto_start: bool = Field(
        default=False,
        validation_alias=AliasChoices("auto_start", "autoStart"),
        serialization_alias="autoStart",
    )


class SettingsPatch(BaseModel):
    """Restrict writes to a typed allow-list of non-secret display preferences."""

    model_config = ConfigDict(extra="forbid")

    presentation: PresentationSettings = Field(default_factory=PresentationSettings)
    research: ResearchSettings = Field(default_factory=ResearchSettings)


class SettingsRead(BaseModel):
    """Safe settings response: configuration state, never credential values."""

    ai_configured: bool = Field(serialization_alias="aiConfigured")
    presentation: PresentationSettings
    research: ResearchSettings


def _presentation(session: Session) -> PresentationSettings:
    """Read one typed preference record with safe defaults for a fresh database."""
    setting = session.get(AppSetting, "presentation")
    if setting is None:
        return PresentationSettings()
    return PresentationSettings.model_validate(setting.value_json)


def _research(session: Session) -> ResearchSettings:
    """Read the persistent auto-start preference with a disabled default."""
    setting = session.get(AppSetting, "research.auto_start")
    if setting is None:
        return ResearchSettings()
    return ResearchSettings.model_validate(setting.value_json)


def _save_presentation(session: Session, values: dict[str, str]) -> None:
    """Replace the singleton preference record even during first-write races."""
    setting = session.get(AppSetting, "presentation")
    if setting is not None:
        setting.value_json = values
        session.commit()
        return
    session.add(AppSetting(key="presentation", value_json=values))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        setting = session.get(AppSetting, "presentation")
        if setting is None:
            raise
        setting.value_json = values
        session.commit()


def _save_research(session: Session, values: dict[str, bool]) -> None:
    """Replace the singleton automatic-research preference with the same race safety."""
    setting = session.get(AppSetting, "research.auto_start")
    if setting is not None:
        setting.value_json = values
        session.commit()
        return
    session.add(AppSetting(key="research.auto_start", value_json=values))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        setting = session.get(AppSetting, "research.auto_start")
        if setting is None:
            raise
        setting.value_json = values
        session.commit()


@router.get("", response_model=SettingsRead)
def get_settings(request: Request, session: DatabaseSession) -> SettingsRead:
    """Return browser-safe display configuration and provider availability only."""
    return SettingsRead(
        ai_configured=request.app.state.settings.ai_configured,
        presentation=_presentation(session),
        research=_research(session),
    )


@router.patch("", response_model=SettingsRead)
def update_settings(
    request: Request, payload: SettingsPatch, session: DatabaseSession
) -> SettingsRead:
    """Persist a complete replacement of the browser-visible presentation settings."""
    values = payload.presentation.model_dump()
    _save_presentation(session, values)
    _save_research(session, payload.research.model_dump())
    return SettingsRead(
        ai_configured=request.app.state.settings.ai_configured,
        presentation=payload.presentation,
        research=payload.research,
    )

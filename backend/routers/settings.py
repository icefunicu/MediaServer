"""Application settings API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.logging_config import get_logger
from backend.services.app_settings import get_app_settings, update_app_settings


logger = get_logger("api.settings")

router = APIRouter(prefix="/api/settings", tags=["设置"])


class UiSettingsResponse(BaseModel):
    home_hidden_roots: list[str]
    home_hidden_categories: list[str]
    recent_hidden_roots: list[str]
    recent_hidden_categories: list[str]
    home_featured_enabled: bool
    default_layout: str
    player_autoplay_default: bool
    group_tv_by_default: bool
    home_recent_limit: int
    category_page_limit: int


class SettingsResponse(BaseModel):
    media_root_directory: str
    ui: UiSettingsResponse
    available_filter_categories: list[str]


class UiSettingsUpdateRequest(BaseModel):
    home_hidden_roots: list[str] | None = None
    home_hidden_categories: list[str] | None = None
    recent_hidden_roots: list[str] | None = None
    recent_hidden_categories: list[str] | None = None
    home_featured_enabled: bool | None = None
    default_layout: str | None = Field(default=None, pattern="^(grid|list)$")
    player_autoplay_default: bool | None = None
    group_tv_by_default: bool | None = None
    home_recent_limit: int | None = Field(default=None, ge=1, le=60)
    category_page_limit: int | None = Field(default=None, ge=60, le=500)


class SettingsUpdateRequest(BaseModel):
    media_root_directory: str | None = None
    create_media_root_if_missing: bool = False
    ui: UiSettingsUpdateRequest | None = None


@router.get("", response_model=SettingsResponse)
async def get_settings():
    try:
        payload = get_app_settings()
        return SettingsResponse(**payload)
    except Exception as exc:
        logger.error(f"Failed to get settings: {exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc


@router.patch("", response_model=SettingsResponse)
async def patch_settings(request: SettingsUpdateRequest):
    try:
        ui_updates: dict[str, Any] | None = None
        if request.ui is not None:
            ui_updates = request.ui.model_dump(exclude_none=True)

        payload = update_app_settings(
            media_root_directory=request.media_root_directory,
            create_media_root_if_missing=request.create_media_root_if_missing,
            ui_updates=ui_updates,
        )
        return SettingsResponse(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Failed to update settings: {exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc

"""Application settings persistence and validation."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from backend.config import get_config, get_config_path, save_config
from backend.logging_config import get_logger
from backend.services.media_library import invalidate_media_library_cache


logger = get_logger("app.settings")

AVAILABLE_FILTER_CATEGORIES: tuple[str, ...] = (
    "movies",
    "tv",
    "music",
    "photos",
    "comics",
    "archives",
    "others",
)

DEFAULT_UI_SETTINGS: dict[str, Any] = {
    "home_hidden_roots": ["CM", "JMV"],
    "home_hidden_categories": [],
    "recent_hidden_roots": [],
    "recent_hidden_categories": [],
    "home_featured_enabled": True,
    "default_layout": "grid",
    "player_autoplay_default": True,
    "group_tv_by_default": True,
    "home_recent_limit": 18,
    "category_page_limit": 500,
}

_SETTINGS_LOCK = threading.Lock()


def _settings_file_path() -> Path:
    config_path = get_config_path()
    return config_path.parent / "app_settings.json"


def _unique_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    seen: set[str] = set()
    normalized: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()
        if not trimmed:
            continue
        key = trimmed.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(trimmed)
    return normalized


def _normalize_categories(values: Any) -> list[str]:
    accepted = set(AVAILABLE_FILTER_CATEGORIES)
    return [item for item in _unique_strings(values) if item in accepted]


def _normalize_ui_settings(raw: Any) -> dict[str, Any]:
    payload = dict(DEFAULT_UI_SETTINGS)
    if isinstance(raw, dict):
        payload.update(raw)

    payload["home_hidden_roots"] = _unique_strings(payload.get("home_hidden_roots"))
    payload["recent_hidden_roots"] = _unique_strings(payload.get("recent_hidden_roots"))
    payload["home_hidden_categories"] = _normalize_categories(payload.get("home_hidden_categories"))
    payload["recent_hidden_categories"] = _normalize_categories(payload.get("recent_hidden_categories"))

    default_layout = str(payload.get("default_layout") or "grid").strip().lower()
    payload["default_layout"] = "list" if default_layout == "list" else "grid"

    payload["home_featured_enabled"] = bool(payload.get("home_featured_enabled", True))
    payload["player_autoplay_default"] = bool(payload.get("player_autoplay_default", True))
    payload["group_tv_by_default"] = bool(payload.get("group_tv_by_default", True))

    try:
        payload["home_recent_limit"] = max(1, min(60, int(payload.get("home_recent_limit", 18))))
    except (TypeError, ValueError):
        payload["home_recent_limit"] = 18

    try:
        payload["category_page_limit"] = max(60, min(500, int(payload.get("category_page_limit", 500))))
    except (TypeError, ValueError):
        payload["category_page_limit"] = 500

    return payload


def load_ui_settings() -> dict[str, Any]:
    settings_path = _settings_file_path()
    if not settings_path.exists():
        return dict(DEFAULT_UI_SETTINGS)

    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Failed to read UI settings file {settings_path}: {exc}")
        return dict(DEFAULT_UI_SETTINGS)

    return _normalize_ui_settings(raw)


def save_ui_settings(settings: dict[str, Any]) -> Path:
    normalized = _normalize_ui_settings(settings)
    settings_path = _settings_file_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = settings_path.with_suffix(f"{settings_path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(settings_path)
    return settings_path


def get_app_settings() -> dict[str, Any]:
    with _SETTINGS_LOCK:
        cfg = get_config()
        ui_settings = load_ui_settings()
        return {
            "media_root_directory": str(Path(cfg.media.root_directory).resolve()),
            "ui": ui_settings,
            "available_filter_categories": list(AVAILABLE_FILTER_CATEGORIES),
        }


def update_app_settings(
    media_root_directory: str | None = None,
    create_media_root_if_missing: bool = False,
    ui_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with _SETTINGS_LOCK:
        cfg = get_config()

        if media_root_directory is not None:
            normalized_root = str(media_root_directory).strip()
            if not normalized_root:
                raise ValueError("媒体根目录不能为空")

            root_path = Path(normalized_root).expanduser()
            if not root_path.is_absolute():
                root_path = root_path.resolve()

            if root_path.exists():
                if not root_path.is_dir():
                    raise ValueError("媒体根目录必须是目录")
            elif create_media_root_if_missing:
                root_path.mkdir(parents=True, exist_ok=True)
            else:
                raise ValueError("媒体根目录不存在")

            cfg.media.root_directory = str(root_path)
            save_config(cfg)
            invalidate_media_library_cache()

        current_ui = load_ui_settings()
        if ui_updates:
            current_ui.update(ui_updates)
        save_ui_settings(current_ui)

        return {
            "media_root_directory": str(Path(cfg.media.root_directory).resolve()),
            "ui": _normalize_ui_settings(current_ui),
            "available_filter_categories": list(AVAILABLE_FILTER_CATEGORIES),
        }

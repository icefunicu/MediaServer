"""Configuration loading and persistence helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


class MediaConfig(BaseModel):
    root_directory: str = "./media"
    video_formats: list[str] = [".mp4", ".mkv", ".ts", ".avi", ".mov", ".flv", ".rmvb", ".wmv", ".m4v", ".vob"]
    audio_formats: list[str] = [".mp3", ".flac", ".m4a", ".wav", ".aac", ".ogg", ".wma"]
    image_formats: list[str] = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".avif"]
    comic_formats: list[str] = [
        ".cbz",
        ".cbr",
        ".zip",
        ".cb7",
        ".7z",
        ".cbt",
        ".tar",
        ".tar.gz",
        ".tgz",
        ".tar.bz2",
        ".tbz2",
        ".tar.xz",
        ".txz",
    ]
    archive_formats: list[str] = [".zip", ".rar", ".7z"]


class CacheConfig(BaseModel):
    memory_cache_size: int = 100 * 1024 * 1024
    disk_cache_size: int = 10 * 1024 * 1024 * 1024
    metadata_ttl: int = 3600
    image_ttl: int = 3600
    transcoded_ttl: int = 86400


class SecurityConfig(BaseModel):
    max_concurrent_connections: int = 100
    rate_limit_per_minute: int = 60
    max_file_size: int = 100 * 1024 * 1024
    max_extracted_size: int = 1024 * 1024 * 1024
    compression_ratio_limit: int = 1000


class LogConfig(BaseModel):
    level: str = "INFO"
    format: str = "text"
    file: Optional[str] = "logs/app.log"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


class Config(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    log: LogConfig = Field(default_factory=LogConfig)


_config: Optional[Config] = None
_config_path: Optional[Path] = None


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration once and cache it globally."""
    global _config
    global _config_path

    if _config is not None:
        return _config

    if config_path is None:
        config_path = os.environ.get(
            "MEDIA_SERVER_CONFIG",
            str(Path(__file__).parent.parent / "config" / "config.yaml"),
        )

    default_config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    if not Path(config_path).exists() and default_config_path.exists():
        config_path = str(default_config_path)

    _config_path = Path(config_path).resolve()

    if Path(config_path).exists():
        try:
            with open(config_path, "r", encoding="utf-8") as file_handle:
                config_data = yaml.safe_load(file_handle)
            _config = Config(**config_data) if config_data else Config()
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Warning: failed to load config file, fallback to defaults. error={exc}")
            _config = Config()
    else:
        print(f"Warning: config file not found, fallback to defaults. path={config_path}")
        _config = Config()

    return _config


def get_config() -> Config:
    """Get current in-memory config."""
    if _config is None:
        return load_config()
    return _config


def reload_config(config_path: Optional[str] = None) -> Config:
    """Force reload config from disk."""
    global _config
    _config = None
    return load_config(config_path)


def get_config_path() -> Path:
    """Get active config file path."""
    global _config_path
    if _config is None:
        load_config()
    if _config_path is None:
        _config_path = (Path(__file__).parent.parent / "config" / "config.yaml").resolve()
    return _config_path


def _config_to_dict(config: Config) -> Dict[str, Any]:
    if hasattr(config, "model_dump"):
        return config.model_dump()
    return config.dict()


def save_config(config: Optional[Config] = None, config_path: Optional[str] = None) -> Path:
    """Persist config to yaml and refresh in-memory state."""
    global _config
    global _config_path

    target_config = config or get_config()
    target_path = Path(config_path).resolve() if config_path else get_config_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    payload = _config_to_dict(target_config)
    temp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")
    with open(temp_path, "w", encoding="utf-8") as file_handle:
        yaml.safe_dump(payload, file_handle, allow_unicode=True, sort_keys=False)
    os.replace(temp_path, target_path)

    _config = target_config
    _config_path = target_path
    return target_path

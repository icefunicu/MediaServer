"""
配置管理模块

提供配置加载和管理功能，支持从 YAML 配置文件读取参数。
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel


class ServerConfig(BaseModel):
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


class MediaConfig(BaseModel):
    """媒体文件配置"""
    root_directory: str = "./media"
    video_formats: list[str] = [".mp4", ".mkv", ".ts", ".avi", ".mov"]
    comic_formats: list[str] = [".cbz", ".cbr", ".zip"]
    archive_formats: list[str] = [".zip", ".rar", ".7z"]


class CacheConfig(BaseModel):
    """缓存配置"""
    memory_cache_size: int = 100 * 1024 * 1024  # 100MB
    disk_cache_size: int = 10 * 1024 * 1024 * 1024  # 10GB
    metadata_ttl: int = 3600  # 1小时
    image_ttl: int = 3600  # 1小时
    transcoded_ttl: int = 86400  # 24小时


class SecurityConfig(BaseModel):
    """安全配置"""
    max_concurrent_connections: int = 100
    rate_limit_per_minute: int = 60
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    max_extracted_size: int = 1024 * 1024 * 1024  # 1GB
    compression_ratio_limit: int = 1000


class LogConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    format: str = "text"
    file: Optional[str] = "logs/app.log"
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


class Config(BaseModel):
    """主配置类"""
    server: ServerConfig = ServerConfig()
    media: MediaConfig = MediaConfig()
    cache: CacheConfig = CacheConfig()
    security: SecurityConfig = SecurityConfig()
    log: LogConfig = LogConfig()


_config: Optional[Config] = None


def load_config(config_path: Optional[str] = None) -> Config:
    """
    加载配置文件

    Args:
        config_path: 配置文件路径，如果为 None 则使用默认路径

    Returns:
        配置对象
    """
    global _config

    if _config is not None:
        return _config

    if config_path is None:
        config_path = os.environ.get(
            "MEDIA_SERVER_CONFIG",
            str(Path(__file__).parent.parent / "config" / "config.yaml")
        )

    default_config_path = Path(__file__).parent.parent / "config" / "config.yaml"

    if not Path(config_path).exists() and default_config_path.exists():
        config_path = str(default_config_path)

    if Path(config_path).exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
                if config_data:
                    _config = Config(**config_data)
                else:
                    _config = Config()
        except Exception as e:
            print(f"警告：配置文件加载失败，使用默认配置。错误: {e}")
            _config = Config()
    else:
        print(f"警告：配置文件不存在，使用默认配置。路径: {config_path}")
        _config = Config()

    return _config


def get_config() -> Config:
    """获取当前配置"""
    if _config is None:
        return load_config()
    return _config


def reload_config(config_path: Optional[str] = None) -> Config:
    """重新加载配置"""
    global _config
    _config = None
    return load_config(config_path)

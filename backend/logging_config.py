"""
日志配置模块

提供人性化的日志功能，支持控制台和文件输出。
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from backend.config import get_config


def setup_logging() -> logging.Logger:
    """
    设置日志系统

    Returns:
        根日志记录器
    """
    config = get_config()
    log_config = config.log

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    logger = logging.getLogger("media_server")
    logger.setLevel(getattr(logging, log_config.level.upper()))

    logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    console_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    if log_config.file:
        log_path = Path(log_config.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_config.file,
            maxBytes=log_config.max_bytes,
            backupCount=log_config.backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(getattr(logging, log_config.level.upper()))

        if log_config.format == "json":
            try:
                from .json_formatter import JsonFormatter
                file_handler.setFormatter(JsonFormatter())
            except Exception:
                fallback_formatter = logging.Formatter(
                    "[%(asctime)s] %(levelname)-8s | %(name)-20s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
                file_handler.setFormatter(fallback_formatter)
                logger.warning("JSON 日志格式不可用，已回退为文本格式")
        else:
            file_formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)-8s | %(name)-20s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_formatter)

        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志记录器"""
    return logging.getLogger(f"media_server.{name}")

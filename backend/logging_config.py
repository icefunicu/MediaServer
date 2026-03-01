"""
日志配置模块

提供人性化的日志功能，支持控制台和文件输出。
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from backend.config import get_config


class ColoredFormatter(logging.Formatter):
    """带颜色的控制台日志格式化器"""
    COLORS = {
        'DEBUG': '\033[90m',      # 灰色
        'INFO': '\033[36m',       # 青色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[1;31m', # 粗体红色
    }
    RESET = '\033[0m'
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        time_str = f"\033[90m[{self.formatTime(record, self.datefmt)}]\033[0m"
        level_str = f"{color}{record.levelname:<8}{self.RESET}"
        name_str = f"\033[35m{record.name:<20}\033[0m"  # 紫色模块名
        msg_str = f"{color}{record.getMessage()}{self.RESET}"
        
        return f"{time_str} {level_str} | {name_str} | {msg_str}"

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
    
    console_formatter = ColoredFormatter(datefmt="%H:%M:%S")
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

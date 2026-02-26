"""
缓存管理模块

提供多层缓存架构：内存缓存和磁盘缓存。
"""

import os
import time
from pathlib import Path
from typing import Any, Optional

from cachetools import LRUCache, TTLCache

from backend.config import get_config
from backend.logging_config import get_logger


logger = get_logger("cache")


metadata_cache: TTLCache = TTLCache(maxsize=100, ttl=3600)
image_cache: LRUCache = LRUCache(maxsize=50)


class CacheManager:
    """缓存管理器"""

    def __init__(self):
        self.config = get_config()
        self.disk_cache_dir = Path("cache")
        self.disk_cache_dir.mkdir(parents=True, exist_ok=True)

    def get_metadata(self, key: str) -> Optional[Any]:
        """从缓存获取元数据"""
        return metadata_cache.get(key)

    def set_metadata(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置元数据缓存"""
        if ttl:
            metadata_cacheTTL = TTLCache(maxsize=100, ttl=ttl)
            metadata_cacheTTL[key] = value
        else:
            metadata_cache[key] = value
        logger.debug(f"元数据缓存已设置: {key}")

    def get_image(self, key: str) -> Optional[bytes]:
        """从缓存获取图片"""
        return image_cache.get(key)

    def set_image(self, key: str, value: bytes) -> None:
        """设置图片缓存"""
        if len(image_cache) >= image_cache.maxsize:
            logger.debug("图片缓存已满，淘汰最旧的项")
        image_cache[key] = value
        logger.debug(f"图片缓存已设置: {key}")

    def get_disk_cache(self, key: str) -> Optional[bytes]:
        """从磁盘缓存获取数据"""
        cache_file = self.disk_cache_dir / f"{key}.cache"
        if cache_file.exists():
            try:
                return cache_file.read_bytes()
            except Exception as e:
                logger.warning(f"读取磁盘缓存失败: {key}, 错误: {e}")
        return None

    def set_disk_cache(self, key: str, value: bytes) -> None:
        """设置磁盘缓存"""
        try:
            cache_file = self.disk_cache_dir / f"{key}.cache"
            cache_file.write_bytes(value)
            logger.debug(f"磁盘缓存已设置: {key}")
        except Exception as e:
            logger.warning(f"设置磁盘缓存失败: {key}, 错误: {e}")

    def clear_metadata_cache(self) -> None:
        """清理元数据缓存"""
        metadata_cache.clear()
        logger.info("元数据缓存已清理")

    def clear_image_cache(self) -> None:
        """清理图片缓存"""
        image_cache.clear()
        logger.info("图片缓存已清理")

    def clear_disk_cache(self) -> None:
        """清理磁盘缓存"""
        try:
            for cache_file in self.disk_cache_dir.glob("*.cache"):
                cache_file.unlink()
            logger.info("磁盘缓存已清理")
        except Exception as e:
            logger.warning(f"清理磁盘缓存失败: {e}")

    def clear_all_cache(self) -> None:
        """清理所有缓存"""
        self.clear_metadata_cache()
        self.clear_image_cache()
        self.clear_disk_cache()
        logger.info("所有缓存已清理")


_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取缓存管理器实例"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager

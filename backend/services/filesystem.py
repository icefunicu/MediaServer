"""
文件系统模块

提供文件浏览、搜索、元数据获取和流式读取功能。
包含路径安全验证，防止路径遍历攻击。
"""

import hashlib
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from backend.config import get_config
from backend.logging_config import get_logger


logger = get_logger("filesystem")


class SecurityError(Exception):
    """安全错误异常"""
    pass


class FileNotFoundError(Exception):
    """文件不存在异常"""
    pass


class FileEntry:
    """文件条目数据模型"""

    def __init__(
        self,
        id: str,
        name: str,
        path: str,
        size: int,
        type: str,
        extension: str,
        modified_time: int,
        is_directory: bool,
        thumbnail: Optional[str] = None
    ):
        self.id = id
        self.name = name
        self.path = path
        self.size = size
        self.type = type
        self.extension = extension
        self.modified_time = modified_time
        self.is_directory = is_directory
        self.thumbnail = thumbnail

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "type": self.type,
            "extension": self.extension,
            "modified_time": self.modified_time,
            "is_directory": self.is_directory,
            "thumbnail": self.thumbnail
        }


def generate_file_id(file_path: str) -> str:
    """生成文件唯一标识符（路径的哈希值）"""
    return hashlib.md5(file_path.encode('utf-8')).hexdigest()


def validate_path(requested_path: str) -> str:
    """
    验证路径安全性，防止路径遍历攻击

    Args:
        requested_path: 请求的路径

    Returns:
        规范化后的绝对路径

    Raises:
        SecurityError: 路径包含危险模式或超出根目录范围
    """
    config = get_config()
    root_dir = Path(config.media.root_directory).resolve()

    if not root_dir.exists():
        logger.warning(f"配置的根目录不存在: {root_dir}")
        root_dir.mkdir(parents=True, exist_ok=True)

    requested_path = requested_path.strip()
    if not requested_path:
        requested_path = "/"

    requested_path = requested_path.replace('\\', '/')
    if requested_path.startswith('/'):
        requested_path = requested_path[1:]

    forbidden_patterns = [
        r'\.\.',           # 父目录引用
        r'^etc',           # /etc 目录
        r'^sys',           # /sys 目录
        r'^proc',          # /proc 目录
        r'^root',          # /root 目录
        r'^windows',       # Windows 系统目录
        r'^program\s*files',  # Program Files
        r'^appdata',       # AppData
        r'^programdata',   # ProgramData
    ]

    path_lower = requested_path.lower()
    for pattern in forbidden_patterns:
        if re.search(pattern, path_lower):
            logger.warning(f"路径遍历攻击被阻止: {requested_path}, 匹配模式: {pattern}")
            raise SecurityError("禁止访问：路径包含危险模式")

    try:
        target_path = (root_dir / requested_path).resolve()
    except (OSError, ValueError) as e:
        logger.warning(f"路径解析失败: {requested_path}, 错误: {e}")
        raise SecurityError(f"无效的路径: {requested_path}")

    root_norm = str(root_dir).rstrip("\\/").lower()
    target_norm = str(target_path).rstrip("\\/").lower()
    if not (target_norm == root_norm or target_norm.startswith(root_norm + os.sep)):
        logger.warning(f"路径超出根目录范围: {requested_path}")
        raise SecurityError("禁止访问：路径超出允许范围")

    return str(target_path)


def get_file_type(extension: str) -> str:
    """
    根据文件扩展名获取文件类型

    Args:
        extension: 文件扩展名（包含点号）

    Returns:
        文件类型：video/comic/archive/other
    """
    extension = extension.lower()
    config = get_config()

    if extension in config.media.video_formats:
        return "video"
    elif extension in config.media.comic_formats:
        return "comic"
    elif extension in config.media.archive_formats:
        return "archive"
    else:
        return "other"


def get_file_info(file_path: str) -> FileEntry:
    """
    获取文件元数据

    Args:
        file_path: 文件路径

    Returns:
        FileEntry 对象

    Raises:
        FileNotFoundError: 文件不存在
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        stat = path.stat()
        extension = path.suffix.lower()

        return FileEntry(
            id=generate_file_id(str(path)),
            name=path.name,
            path=str(path),
            size=stat.st_size,
            type=get_file_type(extension),
            extension=extension,
            modified_time=int(stat.st_mtime),
            is_directory=path.is_dir(),
            thumbnail=None
        )
    except FileNotFoundError:
        raise
    except Exception as e:
        logger.error(f"获取文件信息失败: {file_path}, 错误: {e}")
        raise


def list_directory(dir_path: str, recursive: bool = False) -> List[FileEntry]:
    """
    列出目录内容

    Args:
        dir_path: 目录路径
        recursive: 是否递归列出子目录

    Returns:
        FileEntry 列表

    Raises:
        FileNotFoundError: 目录不存在
    """
    try:
        safe_path = validate_path(dir_path)
        path = Path(safe_path)

        if not path.exists():
            raise FileNotFoundError(f"目录不存在: {dir_path}")

        if not path.is_dir():
            raise NotADirectoryError(f"不是目录: {dir_path}")

        entries = []

        if recursive:
            for root, dirs, files in os.walk(path):
                root_path = Path(root)
                for name in dirs:
                    try:
                        entry_path = root_path / name
                        entry = get_file_info(str(entry_path))
                        entries.append(entry)
                    except Exception as e:
                        logger.warning(f"读取目录项失败: {root_path / name}, 错误: {e}")

                for name in files:
                    try:
                        entry_path = root_path / name
                        entry = get_file_info(str(entry_path))
                        entries.append(entry)
                    except Exception as e:
                        logger.warning(f"读取文件项失败: {root_path / name}, 错误: {e}")
        else:
            for item in sorted(path.iterdir()):
                try:
                    entry = get_file_info(str(item))
                    entries.append(entry)
                except Exception as e:
                    logger.warning(f"读取目录项失败: {item}, 错误: {e}")

        return entries

    except FileNotFoundError:
        raise
    except Exception as e:
        logger.error(f"列出目录失败: {dir_path}, 错误: {e}")
        raise


def search_files(query: str, file_types: Optional[List[str]] = None) -> List[FileEntry]:
    """
    搜索文件

    Args:
        query: 搜索关键词
        file_types: 文件类型过滤列表（video/comic/archive/other）

    Returns:
        匹配的 FileEntry 列表
    """
    config = get_config()
    root_dir = Path(config.media.root_directory).resolve()

    if not root_dir.exists():
        return []

    query = query.lower().strip()
    if not query:
        return []

    results = []

    try:
        for root, dirs, files in os.walk(root_dir):
            root_path = Path(root)

            for name in files:
                if query not in name.lower():
                    continue

                try:
                    entry_path = root_path / name
                    entry = get_file_info(str(entry_path))

                    if file_types and entry.type not in file_types:
                        continue

                    results.append(entry)
                except Exception as e:
                    logger.warning(f"搜索文件失败: {entry_path}, 错误: {e}")

    except Exception as e:
        logger.error(f"搜索失败: {query}, 错误: {e}")

    return results


async def get_file_stream(
    file_path: str,
    start: int,
    end: int
) -> bytes:
    """
    获取文件数据流（支持 Range 读取）

    Args:
        file_path: 文件路径
        start: 起始字节位置
        end: 结束字节位置

    Returns:
        文件数据字节

    Raises:
        FileNotFoundError: 文件不存在
    """
    try:
        safe_path = validate_path(file_path)
        path = Path(safe_path)

        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if path.is_dir():
            raise IsADirectoryError(f"是目录而非文件: {file_path}")

        file_size = path.stat().st_size

        if start < 0 or end >= file_size or start > end:
            raise ValueError(f"Range 请求超出文件范围: {start}-{end}, 文件大小: {file_size}")

        with open(path, 'rb') as f:
            f.seek(start)
            chunk_size = end - start + 1
            content = f.read(chunk_size)

        return content

    except (FileNotFoundError, IsADirectoryError, ValueError):
        raise
    except Exception as e:
        logger.error(f"读取文件流失败: {file_path}, 错误: {e}")
        raise


def get_file_size(file_path: str) -> int:
    """获取文件大小"""
    safe_path = validate_path(file_path)
    path = Path(safe_path)

    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    return path.stat().st_size


def get_mime_type(file_path: str) -> str:
    """获取文件的 MIME 类型"""
    extension = Path(file_path).suffix.lower()

    mime_types = {
        '.mp4': 'video/mp4',
        '.mkv': 'video/x-matroska',
        '.ts': 'video/mp2t',
        '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime',
        '.webm': 'video/webm',
        '.cbz': 'application/vnd.comicbook+zip',
        '.cbr': 'application/vnd.comicbook-rar',
        '.zip': 'application/zip',
        '.rar': 'application/x-rar-compressed',
        '.7z': 'application/x-7z-compressed',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
    }

    return mime_types.get(extension, 'application/octet-stream')

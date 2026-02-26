"""
压缩包处理模块

提供通用压缩包（.zip/.rar/.7z）的解压和内容预览功能。
包含压缩炸弹检测功能。
"""

import io
import os
import tempfile
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import List, Optional

import rarfile
import py7zr

from backend.config import get_config
from backend.logging_config import get_logger
from backend.services.filesystem import validate_path


logger = get_logger("archive")


class ArchiveEntry:
    """压缩包条目数据模型"""

    def __init__(
        self,
        filename: str,
        size: int,
        compressed_size: int,
        is_directory: bool
    ):
        self.filename = filename
        self.size = size
        self.compressed_size = compressed_size
        self.is_directory = is_directory

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "size": self.size,
            "compressed_size": self.compressed_size,
            "is_directory": self.is_directory
        }


class ArchiveInfo:
    """压缩包信息数据模型"""

    def __init__(
        self,
        file_id: str,
        format: str,
        file_count: int,
        total_size: int,
        compressed_size: int,
        entries: List[ArchiveEntry]
    ):
        self.file_id = file_id
        self.format = format
        self.file_count = file_count
        self.total_size = total_size
        self.compressed_size = compressed_size
        self.entries = entries

    def to_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "format": self.format,
            "file_count": self.file_count,
            "total_size": self.total_size,
            "compressed_size": self.compressed_size,
            "entries": [e.to_dict() for e in self.entries]
        }


class ExtractionError(Exception):
    """解压错误异常"""
    pass


class ZipBombError(ExtractionError):
    """压缩炸弹检测错误"""
    pass


def _ensure_safe_archive_entry(entry_name: str) -> None:
    """校验压缩包内路径，防止路径穿越。"""
    normalized = entry_name.replace("\\", "/")
    entry_path = PurePosixPath(normalized)
    if entry_path.is_absolute() or ".." in entry_path.parts:
        raise ExtractionError(f"压缩包内路径不安全: {entry_name}")


def _read_7z_entry(archive_path: Path, entry_name: str) -> bytes:
    """从 7z 文件读取单个条目。"""
    _ensure_safe_archive_entry(entry_name)
    with tempfile.TemporaryDirectory(prefix="media_server_7z_") as temp_dir:
        temp_path = Path(temp_dir)
        with py7zr.SevenZipFile(archive_path, 'r') as szf:
            szf.extract(path=temp_path, targets=[entry_name])
        extracted_path = temp_path / entry_name
        if not extracted_path.exists() or extracted_path.is_dir():
            raise FileNotFoundError(f"压缩包内文件不存在: {entry_name}")
        return extracted_path.read_bytes()


def check_zip_bomb(archive_path: str) -> bool:
    """
    检测压缩炸弹

    Args:
        archive_path: 压缩包路径

    Returns:
        是否通过检测

    Raises:
        ZipBombError: 检测到压缩炸弹
    """
    config = get_config()
    max_ratio = config.security.compression_ratio_limit
    max_size = config.security.max_extracted_size

    path = Path(archive_path)
    compressed_size = path.stat().st_size

    if compressed_size == 0:
        raise ZipBombError("压缩包为空")

    uncompressed_size = 0

    try:
        if archive_path.endswith(('.cbz', '.zip')):
            with zipfile.ZipFile(path, 'r') as zf:
                for info in zf.infolist():
                    uncompressed_size += info.file_size
        elif archive_path.endswith('.cbr'):
            with rarfile.RarFile(path, 'r') as rf:
                for info in rf.infolist():
                    uncompressed_size += info.file_size
        elif archive_path.endswith('.7z'):
            with py7zr.SevenZipFile(path, 'r') as szf:
                for info in szf.list():
                    uncompressed_size += getattr(info, "uncompressed", 0) or 0

        ratio = uncompressed_size / compressed_size if compressed_size > 0 else 0

        if ratio > max_ratio:
            logger.warning(
                f"检测到压缩炸弹: {archive_path}, "
                f"压缩比: {ratio:.1f}:1, 超过限制: {max_ratio}:1"
            )
            raise ZipBombError(
                f"压缩比过高 ({ratio:.1f}:1)，可能为压缩炸弹"
            )

        if uncompressed_size > max_size:
            logger.warning(
                f"解压后文件过大: {archive_path}, "
                f"大小: {uncompressed_size} bytes, 超过限制: {max_size} bytes"
            )
            raise ZipBombError(
                f"解压后总大小超过限制 ({uncompressed_size / 1024 / 1024:.1f}MB)"
            )

        logger.debug(
            f"压缩炸弹检测通过: {archive_path}, "
            f"压缩比: {ratio:.1f}:1, 大小: {uncompressed_size} bytes"
        )
        return True

    except ZipBombError:
        raise
    except Exception as e:
        logger.warning(f"压缩炸弹检测失败: {archive_path}, 错误: {e}")
        return True


def list_archive_contents(archive_path: str) -> ArchiveInfo:
    """
    列出压缩包内容

    Args:
        archive_path: 压缩包路径

    Returns:
        ArchiveInfo 对象

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 不支持的格式
    """
    try:
        safe_path = validate_path(archive_path)
        path = Path(safe_path)

        if not path.exists():
            raise FileNotFoundError(f"压缩包不存在: {archive_path}")

        file_format = path.suffix.lower()
        file_id = path.stem

        if file_format not in ['.zip', '.cbz', '.rar', '.cbr', '.7z']:
            raise ValueError(f"不支持的压缩包格式: {file_format}")

        check_zip_bomb(archive_path)

        entries = []
        total_size = 0

        if file_format in ['.zip', '.cbz']:
            with zipfile.ZipFile(path, 'r') as zf:
                for info in zf.infolist():
                    if info.filename.startswith('__MACOSX'):
                        continue
                    is_dir = info.filename.endswith('/')
                    entry = ArchiveEntry(
                        filename=info.filename,
                        size=info.file_size,
                        compressed_size=info.compress_size,
                        is_directory=is_dir
                    )
                    if not is_dir:
                        total_size += info.file_size
                    entries.append(entry)

        elif file_format in ['.rar', '.cbr']:
            with rarfile.RarFile(path, 'r') as rf:
                for info in rf.infolist():
                    if info.filename.startswith('__MACOSX'):
                        continue
                    is_dir = info.is_dir()
                    entry = ArchiveEntry(
                        filename=info.filename,
                        size=info.file_size,
                        compressed_size=info.compress_size,
                        is_directory=is_dir
                    )
                    if not is_dir:
                        total_size += info.file_size
                    entries.append(entry)

        elif file_format == '.7z':
            with py7zr.SevenZipFile(path, 'r') as szf:
                for info in szf.list():
                    size = getattr(info, "uncompressed", 0) or 0
                    compressed = getattr(info, "compressed", 0) or 0
                    entry = ArchiveEntry(
                        filename=info.filename,
                        size=size,
                        compressed_size=compressed,
                        is_directory=info.is_directory
                    )
                    if not info.is_directory:
                        total_size += size
                    entries.append(entry)

        entries.sort(key=lambda e: e.filename)

        return ArchiveInfo(
            file_id=file_id,
            format=file_format[1:],
            file_count=len([e for e in entries if not e.is_directory]),
            total_size=total_size,
            compressed_size=path.stat().st_size,
            entries=entries
        )

    except (FileNotFoundError, ValueError):
        raise
    except Exception as e:
        logger.error(f"列出压缩包内容失败: {archive_path}, 错误: {e}")
        raise


def extract_file(archive_path: str, entry_path: str) -> bytes:
    """
    从压缩包中解压单个文件

    Args:
        archive_path: 压缩包路径
        entry_path: 压缩包内文件路径

    Returns:
        文件数据字节

    Raises:
        FileNotFoundError: 压缩包或文件不存在
        ValueError: 不支持的格式
        ExtractionError: 解压失败
    """
    config = get_config()
    max_file_size = config.security.max_file_size

    try:
        safe_path = validate_path(archive_path)
        path = Path(safe_path)

        if not path.exists():
            raise FileNotFoundError(f"压缩包不存在: {archive_path}")

        file_format = path.suffix.lower()

        if file_format not in ['.zip', '.cbz', '.rar', '.cbr', '.7z']:
            raise ValueError(f"不支持的压缩包格式: {file_format}")

        data = None

        if file_format in ['.zip', '.cbz']:
            with zipfile.ZipFile(path, 'r') as zf:
                if entry_path not in zf.namelist():
                    raise FileNotFoundError(f"压缩包内文件不存在: {entry_path}")

                info = zf.getinfo(entry_path)
                if info.file_size > max_file_size:
                    raise ExtractionError(
                        f"文件过大 ({info.file_size / 1024 / 1024:.1f}MB)，"
                        f"超过限制 ({max_file_size / 1024 / 1024:.1f}MB)"
                    )

                data = zf.read(entry_path)

        elif file_format in ['.rar', '.cbr']:
            with rarfile.RarFile(path, 'r') as rf:
                if entry_path not in rf.namelist():
                    raise FileNotFoundError(f"压缩包内文件不存在: {entry_path}")

                info = rf.getinfo(entry_path)
                if info.file_size > max_file_size:
                    raise ExtractionError(
                        f"文件过大 ({info.file_size / 1024 / 1024:.1f}MB)，"
                        f"超过限制 ({max_file_size / 1024 / 1024:.1f}MB)"
                    )

                data = rf.read(entry_path)

        elif file_format == '.7z':
            with py7zr.SevenZipFile(path, 'r') as szf:
                archive_entries = {i.filename: i for i in szf.list()}
                if entry_path not in archive_entries:
                    raise FileNotFoundError(f"压缩包内文件不存在: {entry_path}")

                info = archive_entries[entry_path]
                entry_size = getattr(info, "uncompressed", 0) or 0
                if entry_size > max_file_size:
                    raise ExtractionError(
                        f"文件过大 ({entry_size / 1024 / 1024:.1f}MB)，"
                        f"超过限制 ({max_file_size / 1024 / 1024:.1f}MB)"
                    )

                data = _read_7z_entry(path, entry_path)

        if data is None:
            raise ExtractionError(f"无法读取文件: {entry_path}")

        logger.debug(f"解压文件成功: {archive_path}/{entry_path}, 大小: {len(data)} bytes")
        return data

    except (FileNotFoundError, ValueError, ExtractionError):
        raise
    except Exception as e:
        logger.error(f"解压文件失败: {archive_path}/{entry_path}, 错误: {e}")
        raise ExtractionError(f"解压失败: {e}")

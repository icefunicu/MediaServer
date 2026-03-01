"""
漫画阅读模块

提供漫画文件（.cbz/.cbr/.zip）的解压和图片提取功能。
"""

import io
import os
import tempfile
import tarfile
import zipfile
import hashlib
from pathlib import Path
from typing import List, Optional, Tuple
from pathlib import PurePosixPath

import rarfile
import py7zr

try:
    from PIL import Image, UnidentifiedImageError
    PIL_AVAILABLE = True
except Exception:
    Image = None
    PIL_AVAILABLE = False

    class UnidentifiedImageError(Exception):
        """Pillow 不可用时的占位异常类型。"""
        pass

from backend.config import get_config
from backend.logging_config import get_logger
from backend.services.filesystem import (
    FileEntry,
    generate_file_id,
    get_file_info,
    validate_path
)
from cachetools import LRUCache


logger = get_logger("comic_reader")


metadata_cache = LRUCache(maxsize=100)
page_cache = LRUCache(maxsize=50)
optimized_page_cache = LRUCache(maxsize=120)
cover_binary_cache = LRUCache(maxsize=160)
_pil_warning_emitted = False

IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.jpe', '.jfif', '.jfi', '.jif',
    '.png', '.gif', '.webp', '.bmp', '.dib',
    '.tif', '.tiff', '.avif', '.heic', '.pbm', '.pgm', '.ppm'
}
COMIC_ARCHIVE_FORMATS = {
    '.cbz', '.zip',
    '.cbr', '.rar',
    '.cb7', '.7z',
    '.cbt', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz',
}
_ARCHIVE_EXTENSION_TO_KIND = {
    '.cbz': 'zip',
    '.zip': 'zip',
    '.cbr': 'rar',
    '.rar': 'rar',
    '.cb7': '7z',
    '.7z': '7z',
    '.cbt': 'tar',
    '.tar': 'tar',
    '.tar.gz': 'tar',
    '.tgz': 'tar',
    '.tar.bz2': 'tar',
    '.tbz2': 'tar',
    '.tar.xz': 'tar',
    '.txz': 'tar',
}
_ARCHIVE_KIND_PRIORITY = ("zip", "rar", "7z", "tar")
_KNOWN_COMIC_SUFFIXES = tuple(sorted(COMIC_ARCHIVE_FORMATS, key=len, reverse=True))
COVER_CACHE_DIR = Path(__file__).resolve().parents[2] / "cache" / "comic_covers"


def _detect_declared_extension(path: Path) -> str:
    """Detect extension from filename, prioritizing composite suffixes."""
    name = path.name.lower()
    for suffix in _KNOWN_COMIC_SUFFIXES:
        if name.endswith(suffix):
            return suffix
    return path.suffix.lower()


def _build_file_signature(path: Path) -> tuple[str, int]:
    """Build stable file signature for cache keys."""
    safe_path = str(path)
    file_mtime_ns = path.stat().st_mtime_ns
    return safe_path, file_mtime_ns


def _build_cover_cache_identity(
    file_path: str,
    file_mtime_ns: int,
    max_width: int,
    quality: int,
    output_format: str,
) -> tuple[str, Path]:
    raw_key = f"cover:{file_path}:{file_mtime_ns}:{max_width}:{quality}:{output_format}"
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()
    file_ext = {
        "jpeg": ".jpg",
        "png": ".png",
        "webp": ".webp",
    }[output_format]
    return raw_key, COVER_CACHE_DIR / f"{digest}{file_ext}"


def _ensure_safe_archive_entry(entry_name: str) -> None:
    """校验压缩包内路径，防止路径穿越。"""
    normalized = entry_name.replace("\\", "/")
    entry_path = PurePosixPath(normalized)
    if entry_path.is_absolute() or ".." in entry_path.parts:
        raise ValueError(f"压缩包内路径不安全: {entry_name}")


def _read_7z_entry(archive_path: Path, entry_name: str) -> bytes:
    """
    从 7z 文件中读取单个条目。

    当前 py7zr 版本不提供 read/readall，采用临时目录提取指定文件。
    """
    _ensure_safe_archive_entry(entry_name)
    with tempfile.TemporaryDirectory(prefix="media_server_7z_") as temp_dir:
        temp_path = Path(temp_dir)
        with py7zr.SevenZipFile(archive_path, 'r') as szf:
            szf.extract(path=temp_path, targets=[entry_name])
        extracted_path = temp_path / entry_name
        if not extracted_path.exists() or extracted_path.is_dir():
            raise FileNotFoundError(f"7z 条目不存在: {entry_name}")
        return extracted_path.read_bytes()


def infer_image_content_type(filename: str) -> str:
    """根据文件名推断图片 MIME 类型。"""
    name = filename.lower()
    if name.endswith('.png'):
        return "image/png"
    if name.endswith('.gif'):
        return "image/gif"
    if name.endswith('.webp'):
        return "image/webp"
    if name.endswith('.bmp'):
        return "image/bmp"
    return "image/jpeg"


def optimize_page_image_for_delivery(
    cache_key: str,
    image_data: bytes,
    source_filename: str,
    max_width: Optional[int] = None,
    quality: int = 85,
    output_format: Optional[str] = None
) -> Tuple[bytes, str]:
    """
    为移动端/LAN 场景优化漫画图片体积。

    - 仅在请求缩放或格式转换时触发图像处理
    - 使用内存缓存避免重复转码开销
    """
    if cache_key in optimized_page_cache:
        return optimized_page_cache[cache_key]

    default_content_type = infer_image_content_type(source_filename)
    global _pil_warning_emitted
    if not PIL_AVAILABLE:
        if not _pil_warning_emitted:
            logger.warning("Pillow 未安装，漫画图片优化功能已降级为原图传输")
            _pil_warning_emitted = True
        result = (image_data, default_content_type)
        optimized_page_cache[cache_key] = result
        return result

    if max_width is None and output_format is None:
        result = (image_data, default_content_type)
        optimized_page_cache[cache_key] = result
        return result

    target_format = (output_format or "").lower()
    if target_format not in {"jpeg", "png", "webp"}:
        target_format = ""

    try:
        with Image.open(io.BytesIO(image_data)) as image:
            working = image.copy()

        if max_width and working.width > max_width:
            ratio = max_width / float(working.width)
            new_height = max(1, int(working.height * ratio))
            resampling_ns = getattr(Image, "Resampling", Image)
            resample_lanczos = getattr(resampling_ns, "LANCZOS", 1)
            working = working.resize((max_width, new_height), resample_lanczos)

        if not target_format:
            if default_content_type == "image/png":
                target_format = "png"
            elif default_content_type == "image/webp":
                target_format = "webp"
            else:
                target_format = "jpeg"

        save_kwargs: dict = {}
        if target_format == "jpeg":
            if working.mode not in ("RGB", "L"):
                working = working.convert("RGB")
            save_format = "JPEG"
            save_kwargs = {"quality": quality, "optimize": True, "progressive": True}
            content_type = "image/jpeg"
        elif target_format == "png":
            if working.mode == "P":
                working = working.convert("RGBA")
            save_format = "PNG"
            save_kwargs = {"optimize": True}
            content_type = "image/png"
        else:
            if working.mode not in ("RGB", "RGBA"):
                working = working.convert("RGB")
            save_format = "WEBP"
            save_kwargs = {"quality": quality, "method": 4}
            content_type = "image/webp"

        buffer = io.BytesIO()
        working.save(buffer, format=save_format, **save_kwargs)
        payload = buffer.getvalue()

        result = (payload, content_type)
        optimized_page_cache[cache_key] = result
        return result
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.warning(f"图片优化失败，回退原图: {source_filename}, 错误: {exc}")
        result = (image_data, default_content_type)
        optimized_page_cache[cache_key] = result
        return result


class PageInfo:
    """页面信息数据模型"""

    def __init__(
        self,
        page_num: int,
        filename: str,
        width: int = 0,
        height: int = 0,
        size: int = 0
    ):
        self.page_num = page_num
        self.filename = filename
        self.width = width
        self.height = height
        self.size = size

    def to_dict(self) -> dict:
        return {
            "page_num": self.page_num,
            "filename": self.filename,
            "width": self.width,
            "height": self.height,
            "size": self.size
        }


class ComicMetadata:
    """漫画元数据数据模型"""

    def __init__(
        self,
        file_id: str,
        page_count: int,
        format: str,
        file_size: int,
        pages: List[PageInfo]
    ):
        self.file_id = file_id
        self.page_count = page_count
        self.format = format
        self.file_size = file_size
        self.pages = pages

    def to_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "page_count": self.page_count,
            "format": self.format,
            "file_size": self.file_size,
            "pages": [p.to_dict() for p in self.pages]
        }


def natural_sort_key(filename: str) -> List:
    """
    生成自然排序键

    用于实现自然排序，使得 "page1.jpg" < "page2.jpg" < "page10.jpg"
    """
    import re
    parts = re.split(r'(\d+)', filename)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def _read_image_entries_from_zip(path: Path) -> list[str]:
    image_files: list[str] = []
    with zipfile.ZipFile(path, 'r') as zf:
        for name in zf.namelist():
            _ensure_safe_archive_entry(name)
            if name.startswith('__MACOSX'):
                continue
            ext = Path(name).suffix.lower()
            if ext in IMAGE_EXTENSIONS and not name.endswith('/'):
                image_files.append(name)
    return image_files


def _read_image_entries_from_rar(path: Path) -> list[str]:
    image_files: list[str] = []
    with rarfile.RarFile(path, 'r') as rf:
        for name in rf.namelist():
            _ensure_safe_archive_entry(name)
            if name.startswith('__MACOSX'):
                continue
            ext = Path(name).suffix.lower()
            if ext in IMAGE_EXTENSIONS and not name.endswith('/'):
                image_files.append(name)
    return image_files


def _read_image_entries_from_7z(path: Path) -> list[str]:
    image_files: list[str] = []
    with py7zr.SevenZipFile(path, 'r') as szf:
        for info in szf.list():
            name = info.filename
            _ensure_safe_archive_entry(name)
            if name.startswith('__MACOSX') or info.is_directory:
                continue
            ext = Path(name).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                image_files.append(name)
    return image_files


def _read_image_entries_from_tar(path: Path) -> list[str]:
    image_files: list[str] = []
    with tarfile.open(path, "r:*") as tf:
        for member in tf.getmembers():
            name = member.name
            _ensure_safe_archive_entry(name)
            if name.startswith('__MACOSX') or member.isdir():
                continue
            ext = Path(name).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                image_files.append(name)
    return image_files


def _detect_archive_candidates(path: Path, declared_extension: str) -> list[str]:
    candidates: list[str] = []
    declared_kind = _ARCHIVE_EXTENSION_TO_KIND.get(declared_extension)
    if declared_kind:
        candidates.append(declared_kind)

    try:
        if zipfile.is_zipfile(path) and 'zip' not in candidates:
            candidates.append('zip')
    except OSError:
        pass

    try:
        if rarfile.is_rarfile(path) and 'rar' not in candidates:
            candidates.append('rar')
    except OSError:
        pass

    try:
        if py7zr.is_7zfile(path) and '7z' not in candidates:
            candidates.append('7z')
    except OSError:
        pass

    try:
        if tarfile.is_tarfile(path) and 'tar' not in candidates:
            candidates.append('tar')
    except OSError:
        pass

    for kind in _ARCHIVE_KIND_PRIORITY:
        if kind not in candidates:
            candidates.append(kind)
    return candidates


def _resolve_comic_archive(
    path: Path,
    declared_extension: str,
) -> tuple[str, list[str]]:
    candidates = _detect_archive_candidates(path, declared_extension)
    if not candidates:
        raise ValueError("压缩包格式不可识别或已损坏")

    first_error: Exception | None = None
    for kind in candidates:
        try:
            if kind == 'zip':
                image_files = _read_image_entries_from_zip(path)
            elif kind == 'rar':
                image_files = _read_image_entries_from_rar(path)
            elif kind == '7z':
                image_files = _read_image_entries_from_7z(path)
            elif kind == 'tar':
                image_files = _read_image_entries_from_tar(path)
            else:
                continue

            image_files.sort(key=natural_sort_key)
            if not image_files:
                continue
            return kind, image_files
        except (
            zipfile.BadZipFile,
            rarfile.Error,
            py7zr.exceptions.Bad7zFile,
            py7zr.exceptions.PasswordRequired,
            tarfile.TarError,
            RuntimeError,
            UnicodeError,
            OSError,
            ValueError,
        ) as exc:
            if first_error is None:
                first_error = exc
            continue

    if first_error is not None:
        raise ValueError(f"压缩包不可读取: {first_error}") from first_error
    raise ValueError("未在压缩包中发现可读图片页面")


def _read_page_data(path: Path, archive_kind: str, entry_name: str) -> bytes:
    _ensure_safe_archive_entry(entry_name)
    if archive_kind == 'zip':
        with zipfile.ZipFile(path, 'r') as zf:
            return zf.read(entry_name)
    if archive_kind == 'rar':
        with rarfile.RarFile(path, 'r') as rf:
            return rf.read(entry_name)
    if archive_kind == '7z':
        return _read_7z_entry(path, entry_name)
    if archive_kind == 'tar':
        with tarfile.open(path, "r:*") as tf:
            member = tf.getmember(entry_name)
            file_handle = tf.extractfile(member)
            if file_handle is None:
                raise FileNotFoundError(f"tar 条目不存在: {entry_name}")
            return file_handle.read()
    raise ValueError(f"不支持的压缩格式: {archive_kind}")


def get_comic_metadata(file_path: str) -> ComicMetadata:
    """
    获取漫画元数据

    Args:
        file_path: 漫画文件路径

    Returns:
        ComicMetadata 对象

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 不支持的格式
    """
    try:
        safe_path = validate_path(file_path)
        path = Path(safe_path)

        if not path.exists():
            raise FileNotFoundError(f"漫画文件不存在: {file_path}")

        signature_path, file_mtime_ns = _build_file_signature(path)
        cache_key = f"metadata:{signature_path}:{file_mtime_ns}"
        if cache_key in metadata_cache:
            logger.debug(f"从缓存获取漫画元数据: {safe_path}")
            return metadata_cache[cache_key]

        file_size = path.stat().st_size
        file_format = _detect_declared_extension(path)
        file_id = generate_file_id(str(path))

        if file_format not in COMIC_ARCHIVE_FORMATS:
            raise ValueError(f"不支持的漫画格式: {file_format}")

        resolved_kind, image_files = _resolve_comic_archive(path, file_format)

        pages = []
        for i, filename in enumerate(image_files):
            pages.append(PageInfo(
                page_num=i + 1,
                filename=filename
            ))

        metadata = ComicMetadata(
            file_id=file_id,
            page_count=len(pages),
            format=resolved_kind,
            file_size=file_size,
            pages=pages
        )

        metadata_cache[cache_key] = metadata
        logger.info(f"漫画元数据加载成功: {file_path}, 页数: {len(pages)}")

        return metadata

    except (FileNotFoundError, ValueError):
        raise
    except Exception as e:
        logger.error(f"获取漫画元数据失败: {file_path}, 错误: {e}")
        raise


def get_page_image(file_path: str, page_num: int) -> bytes:
    """
    获取指定页面的图片数据

    Args:
        file_path: 漫画文件路径
        page_num: 页码（从1开始）

    Returns:
        图片数据字节

    Raises:
        FileNotFoundError: 文件不存在
        IndexError: 页码超出范围
    """
    if page_num < 1:
        raise IndexError(f"页码必须大于0: {page_num}")

    try:
        safe_path = validate_path(file_path)
        path = Path(safe_path)
        if not path.exists():
            raise FileNotFoundError(f"漫画文件不存在: {file_path}")

        signature_path, file_mtime_ns = _build_file_signature(path)
        cache_key = f"page:{signature_path}:{file_mtime_ns}:{page_num}"
        if cache_key in page_cache:
            logger.debug(f"从缓存获取漫画页面: {safe_path}, 页码: {page_num}")
            return page_cache[cache_key]

        metadata = get_comic_metadata(safe_path)

        if page_num > metadata.page_count:
            raise IndexError(f"页码超出范围: {page_num} > {metadata.page_count}")

        page_info = metadata.pages[page_num - 1]

        image_data = None

        image_data = _read_page_data(path, metadata.format, page_info.filename)

        if not image_data:
            raise ValueError(f"无法读取页面图片: {page_info.filename}")

        page_cache[cache_key] = image_data

        return image_data

    except (
        FileNotFoundError,
        IndexError,
        ValueError,
        zipfile.BadZipFile,
        rarfile.Error,
        py7zr.exceptions.Bad7zFile,
        py7zr.exceptions.PasswordRequired,
        tarfile.TarError,
    ) as exc:
        if isinstance(
            exc,
            (
                zipfile.BadZipFile,
                rarfile.Error,
                py7zr.exceptions.Bad7zFile,
                py7zr.exceptions.PasswordRequired,
                tarfile.TarError,
            ),
        ):
            raise ValueError(f"压缩包不可读取: {exc}") from exc
        raise
    except Exception as e:
        logger.error(f"获取漫画页面失败: {file_path}, 页码: {page_num}, 错误: {e}")
        raise


def get_cached_comic_cover(
    file_path: str,
    max_width: int = 420,
    quality: int = 72,
    output_format: str = "webp",
) -> tuple[bytes, str, str]:
    """
    读取或生成漫画封面（默认第 1 页），并持久化到磁盘缓存。
    """
    safe_path = validate_path(file_path)
    path = Path(safe_path)

    if not path.exists():
        raise FileNotFoundError(f"漫画文件不存在: {file_path}")

    normalized_format = (output_format or "webp").lower()
    if normalized_format not in {"jpeg", "png", "webp"}:
        normalized_format = "webp"

    signature_path, file_mtime_ns = _build_file_signature(path)
    cache_identity, cache_path = _build_cover_cache_identity(
        file_path=signature_path,
        file_mtime_ns=file_mtime_ns,
        max_width=max_width,
        quality=quality,
        output_format=normalized_format,
    )
    etag = f"W/\"{hashlib.md5(cache_identity.encode('utf-8')).hexdigest()}\""

    if cache_identity in cover_binary_cache:
        data, content_type = cover_binary_cache[cache_identity]
        return data, content_type, etag

    if cache_path.exists():
        data = cache_path.read_bytes()
        content_type = infer_image_content_type(cache_path.name)
        cover_binary_cache[cache_identity] = (data, content_type)
        return data, content_type, etag

    metadata = get_comic_metadata(safe_path)
    if metadata.page_count <= 0:
        raise ValueError("漫画没有可读取页面")

    source_name = metadata.pages[0].filename
    image_data = get_page_image(safe_path, 1)
    optimized_data, content_type = optimize_page_image_for_delivery(
        cache_key=cache_identity,
        image_data=image_data,
        source_filename=source_name,
        max_width=max_width,
        quality=quality,
        output_format=normalized_format,
    )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
    temp_path.write_bytes(optimized_data)
    os.replace(temp_path, cache_path)

    cover_binary_cache[cache_identity] = (optimized_data, content_type)
    return optimized_data, content_type, etag


def preload_page(file_path: str, page_num: int) -> None:
    """
    预加载指定页面（异步）

    Args:
        file_path: 漫画文件路径
        page_num: 页码
    """
    import threading

    def _preload():
        try:
            get_page_image(file_path, page_num)
            logger.debug(f"页面预加载完成: {file_path}, 页码: {page_num}")
        except Exception as e:
            logger.warning(f"页面预加载失败: {file_path}, 页码: {page_num}, 错误: {e}")

    thread = threading.Thread(target=_preload, daemon=True)
    thread.start()


def preload_pages(file_path: str, page_nums: List[int]) -> None:
    """
    预加载多个页面

    Args:
        file_path: 漫画文件路径
        page_nums: 页码列表
    """
    for page_num in page_nums:
        preload_page(file_path, page_num)


def clear_comic_cache(file_path: Optional[str] = None) -> None:
    """
    清理漫画缓存

    Args:
        file_path: 如果指定，则只清理该文件的缓存；否则清理所有缓存
    """
    global metadata_cache, page_cache, optimized_page_cache, cover_binary_cache

    if file_path:
        target_paths = {file_path}
        try:
            target_paths.add(validate_path(file_path))
        except Exception:
            pass

        for target in target_paths:
            metadata_prefix = f"metadata:{target}:"
            page_prefix = f"page:{target}:"
            cover_prefix = f"cover:{target}:"

            keys_to_remove = [k for k in metadata_cache.keys() if k.startswith(metadata_prefix)]
            for key in keys_to_remove:
                del metadata_cache[key]

            keys_to_remove = [k for k in page_cache.keys() if k.startswith(page_prefix)]
            for key in keys_to_remove:
                del page_cache[key]

            keys_to_remove = [k for k in optimized_page_cache.keys() if str(k).startswith(target)]
            for key in keys_to_remove:
                del optimized_page_cache[key]

            keys_to_remove = [k for k in cover_binary_cache.keys() if str(k).startswith(cover_prefix)]
            for key in keys_to_remove:
                del cover_binary_cache[key]

        logger.info(f"清理漫画缓存: {file_path}")
    else:
        metadata_cache.clear()
        page_cache.clear()
        optimized_page_cache.clear()
        cover_binary_cache.clear()
        logger.info("清理所有漫画缓存")

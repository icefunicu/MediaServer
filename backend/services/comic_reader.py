"""
漫画阅读模块

提供漫画文件（.cbz/.cbr/.zip）的解压和图片提取功能。
"""

import io
import os
import tempfile
import zipfile
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
_pil_warning_emitted = False


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
    cache_key = f"metadata:{file_path}"
    if cache_key in metadata_cache:
        logger.debug(f"从缓存获取漫画元数据: {file_path}")
        return metadata_cache[cache_key]

    try:
        safe_path = validate_path(file_path)
        path = Path(safe_path)

        if not path.exists():
            raise FileNotFoundError(f"漫画文件不存在: {file_path}")

        file_size = path.stat().st_size
        file_format = path.suffix.lower()
        file_id = generate_file_id(str(path))

        if file_format not in ['.cbz', '.cbr', '.zip', '.7z']:
            raise ValueError(f"不支持的漫画格式: {file_format}")

        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        image_files = []

        if file_format in ['.cbz', '.zip']:
            with zipfile.ZipFile(path, 'r') as zf:
                for name in zf.namelist():
                    if name.startswith('__MACOSX'):
                        continue
                    ext = Path(name).suffix.lower()
                    if ext in image_extensions and not name.endswith('/'):
                        image_files.append(name)
        elif file_format == '.cbr':
            with rarfile.RarFile(path, 'r') as rf:
                for name in rf.namelist():
                    if name.startswith('__MACOSX'):
                        continue
                    ext = Path(name).suffix.lower()
                    if ext in image_extensions and not name.endswith('/'):
                        image_files.append(name)
        elif file_format == '.7z':
            with py7zr.SevenZipFile(path, 'r') as szf:
                for info in szf.list():
                    name = info.filename
                    if name.startswith('__MACOSX') or info.is_directory:
                        continue
                    ext = Path(name).suffix.lower()
                    if ext in image_extensions:
                        image_files.append(name)

        image_files.sort(key=natural_sort_key)

        pages = []
        for i, filename in enumerate(image_files):
            pages.append(PageInfo(
                page_num=i + 1,
                filename=filename
            ))

        metadata = ComicMetadata(
            file_id=file_id,
            page_count=len(pages),
            format=file_format[1:],
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

    cache_key = f"page:{file_path}:{page_num}"
    if cache_key in page_cache:
        logger.debug(f"从缓存获取漫画页面: {file_path}, 页码: {page_num}")
        return page_cache[cache_key]

    try:
        metadata = get_comic_metadata(file_path)

        if page_num > metadata.page_count:
            raise IndexError(f"页码超出范围: {page_num} > {metadata.page_count}")

        page_info = metadata.pages[page_num - 1]
        safe_path = validate_path(file_path)
        path = Path(safe_path)

        image_data = None

        if metadata.format in ['cbz', 'zip']:
            with zipfile.ZipFile(path, 'r') as zf:
                image_data = zf.read(page_info.filename)
        elif metadata.format == 'cbr':
            with rarfile.RarFile(path, 'r') as rf:
                image_data = rf.read(page_info.filename)
        elif metadata.format == '7z':
            image_data = _read_7z_entry(path, page_info.filename)

        if not image_data:
            raise ValueError(f"无法读取页面图片: {page_info.filename}")

        page_cache[cache_key] = image_data

        return image_data

    except (FileNotFoundError, IndexError, ValueError):
        raise
    except Exception as e:
        logger.error(f"获取漫画页面失败: {file_path}, 页码: {page_num}, 错误: {e}")
        raise


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
    global metadata_cache, page_cache

    if file_path:
        keys_to_remove = [k for k in metadata_cache.keys() if k == f"metadata:{file_path}"]
        for key in keys_to_remove:
            del metadata_cache[key]

        keys_to_remove = [k for k in page_cache.keys() if k.startswith(f"page:{file_path}:")]
        for key in keys_to_remove:
            del page_cache[key]

        logger.info(f"清理漫画缓存: {file_path}")
    else:
        metadata_cache.clear()
        page_cache.clear()
        logger.info("清理所有漫画缓存")

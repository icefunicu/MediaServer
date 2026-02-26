"""
Comic reader API routes.
"""

import hashlib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from backend.logging_config import get_logger
from backend.services.comic_reader import (
    get_comic_metadata,
    get_page_image,
    infer_image_content_type,
    optimize_page_image_for_delivery,
)
from backend.services.filesystem import (
    FileNotFoundError,
    SecurityError,
    get_file_info,
    validate_path,
)


logger = get_logger("api.comic")

router = APIRouter(prefix="/api/comic", tags=["漫画阅读"])


class ComicMetadataResponse(BaseModel):
    """Comic metadata response."""

    file_id: str
    page_count: int
    format: str
    file_size: int
    pages: list


@router.get("/metadata", response_model=ComicMetadataResponse)
async def get_comic_info(path: str = Query(..., description="文件路径")):
    """Get comic metadata."""
    try:
        safe_path = validate_path(path)
        entry = get_file_info(safe_path)

        if entry.type != "comic":
            raise HTTPException(status_code=400, detail="不是漫画文件")

        metadata = get_comic_metadata(safe_path)
        return ComicMetadataResponse(**metadata.to_dict())

    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecurityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"获取漫画元数据失败: {path}, 错误: {exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc


@router.get("/page")
async def get_page(
    request: Request,
    path: str = Query(..., description="文件路径"),
    page: int = Query(..., description="页码"),
    max_width: Optional[int] = Query(None, ge=640, le=4096, description="最大宽度"),
    quality: int = Query(85, ge=50, le=95, description="压缩质量"),
    format: Optional[str] = Query(
        None,
        pattern="^(jpeg|png|webp)$",
        description="输出格式（jpeg/png/webp）",
    ),
):
    """Get image bytes for a single comic page."""
    try:
        if page < 1:
            raise HTTPException(status_code=400, detail="页码必须大于 0")

        safe_path = validate_path(path)
        entry = get_file_info(safe_path)

        if entry.type != "comic":
            raise HTTPException(status_code=400, detail="不是漫画文件")

        metadata = get_comic_metadata(safe_path)
        source_name = metadata.pages[page - 1].filename
        image_data = get_page_image(safe_path, page)

        mtime = int(Path(safe_path).stat().st_mtime)
        optimize_key = (
            f"{safe_path}:{mtime}:{page}:"
            f"{max_width or 0}:{quality}:{format or 'src'}"
        )
        etag = f"W/\"{hashlib.md5(optimize_key.encode('utf-8')).hexdigest()}\""

        response_headers = {
            "Cache-Control": "public, max-age=86400",
            "Accept-Ranges": "bytes",
            "ETag": etag,
            "Vary": "Accept, User-Agent",
        }
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=response_headers)

        optimized_data, content_type = optimize_page_image_for_delivery(
            cache_key=optimize_key,
            image_data=image_data,
            source_filename=source_name,
            max_width=max_width,
            quality=quality,
            output_format=format,
        )
        if not content_type:
            content_type = infer_image_content_type(source_name)

        return Response(
            content=optimized_data,
            media_type=content_type,
            headers=response_headers,
        )

    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecurityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"获取漫画页面失败: {path}, 页码: {page}, 错误: {exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc


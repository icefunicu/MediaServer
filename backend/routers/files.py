"""
文件浏览 API 路由

提供文件系统访问和搜索功能。
"""

from typing import List, Optional
import re

from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.logging_config import get_logger
from backend.services.filesystem import (
    FileEntry,
    FileNotFoundError,
    SecurityError,
    get_file_info,
    get_mime_type,
    list_directory,
    search_files,
    generate_file_id,
    validate_path,
)


logger = get_logger("api.files")

router = APIRouter(prefix="/api/files", tags=["文件管理"])


class FileInfoResponse(BaseModel):
    """文件信息响应"""

    id: str
    name: str
    path: str
    size: int
    type: str
    extension: str
    modified_time: int
    is_directory: bool
    thumbnail: Optional[str] = None


class DirectoryListResponse(BaseModel):
    """目录列表响应"""

    path: str
    files: List[FileInfoResponse]


@router.get("", response_model=DirectoryListResponse)
async def get_files(
    path: str = Query("/", description="目录路径"),
    recursive: bool = Query(False, description="是否递归列出子目录"),
):
    """列出目录内容。"""

    try:
        entries = list_directory(path, recursive)
        return DirectoryListResponse(
            path=path,
            files=[FileInfoResponse(**e.to_dict()) for e in entries],
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SecurityError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"列出目录失败: {path}, 错误: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s.name)]


@router.get("/videos", response_model=DirectoryListResponse)
async def get_video_files(path: str = Query("/", description="目录路径")):
    """列出目录内的视频文件并按自然排序返回。"""

    try:
        entries = list_directory(path, recursive=False)
        video_entries = [e for e in entries if e.type == "video"]
        video_entries.sort(key=natural_sort_key)
        return DirectoryListResponse(
            path=path,
            files=[FileInfoResponse(**e.to_dict()) for e in video_entries],
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SecurityError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"列出视频目录失败: {path}, 错误: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/search", response_model=DirectoryListResponse)
async def search(
    query: str = Query(..., description="搜索关键词"),
    types: Optional[str] = Query(None, description="文件类型过滤（逗号分隔）"),
):
    """搜索文件。"""

    try:
        file_types = None
        if types:
            file_types = [t.strip() for t in types.split(",")]

        entries = search_files(query, file_types)
        return DirectoryListResponse(
            path="/search",
            files=[FileInfoResponse(**e.to_dict()) for e in entries],
        )
    except Exception as e:
        logger.error(f"搜索失败: {query}, 错误: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/info", response_model=FileInfoResponse)
async def get_file_information(path: str = Query(..., description="文件路径")):
    """获取文件信息。"""

    try:
        entry = get_file_info(path)
        return FileInfoResponse(**entry.to_dict())
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SecurityError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"获取文件信息失败: {path}, 错误: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/raw")
async def get_raw_media(path: str = Query(..., description="媒体文件路径")):
    """
    输出媒体原始文件流（图片/音频/其它文件下载）。
    """

    try:
        safe_path = validate_path(path)
        entry = get_file_info(safe_path)
        if entry.is_directory:
            raise HTTPException(status_code=400, detail="目录不能作为媒体文件输出")

        return FileResponse(
            path=safe_path,
            media_type=get_mime_type(safe_path),
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",
            },
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecurityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"输出媒体文件失败: {path}, 错误: {exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc

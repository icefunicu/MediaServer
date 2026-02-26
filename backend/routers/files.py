"""
鏂囦欢娴忚 API 璺敱

鎻愪緵鏂囦欢绯荤粺璁块棶鍜屾悳绱㈠姛鑳姐€?"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from pydantic import BaseModel

from backend.logging_config import get_logger
from backend.services.filesystem import (
    FileEntry,
    FileNotFoundError,
    SecurityError,
    get_file_info,
    list_directory,
    search_files,
    generate_file_id
)


logger = get_logger("api.files")

router = APIRouter(prefix="/api/files", tags=["鏂囦欢绠＄悊"])


class FileInfoResponse(BaseModel):
    """鏂囦欢淇℃伅鍝嶅簲"""
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
    """鐩綍鍒楄〃鍝嶅簲"""
    path: str
    files: List[FileInfoResponse]


@router.get("", response_model=DirectoryListResponse)
async def get_files(
    path: str = Query("/", description="鐩綍璺緞"),
    recursive: bool = Query(False, description="是否递归列出子目录")
):
    """
    鍒楀嚭鐩綍鍐呭
    """
    try:
        entries = list_directory(path, recursive)
        return DirectoryListResponse(
            path=path,
            files=[FileInfoResponse(**e.to_dict()) for e in entries]
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SecurityError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"鍒楀嚭鐩綍澶辫触: {path}, 閿欒: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/search", response_model=DirectoryListResponse)
async def search(
    query: str = Query(..., description="搜索关键词"),
    types: Optional[str] = Query(None, description="文件类型过滤（逗号分隔）")
):
    """
    鎼滅储鏂囦欢
    """
    try:
        file_types = None
        if types:
            file_types = [t.strip() for t in types.split(',')]

        entries = search_files(query, file_types)
        return DirectoryListResponse(
            path="/search",
            files=[FileInfoResponse(**e.to_dict()) for e in entries]
        )
    except Exception as e:
        logger.error(f"鎼滅储澶辫触: {query}, 閿欒: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/info", response_model=FileInfoResponse)
async def get_file_information(
    path: str = Query(..., description="鏂囦欢璺緞")
):
    """
    鑾峰彇鏂囦欢淇℃伅
    """
    try:
        entry = get_file_info(path)
        return FileInfoResponse(**entry.to_dict())
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SecurityError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"鑾峰彇鏂囦欢淇℃伅澶辫触: {path}, 閿欒: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")

"""
Media library API routes.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from pydantic import BaseModel

from backend.logging_config import get_logger
from backend.services.media_library import (
    SUPPORTED_CATEGORIES,
    get_library_overview,
    list_library_items,
)


logger = get_logger("api.library")

router = APIRouter(prefix="/api/library", tags=["媒体库"])


class LibraryItemResponse(BaseModel):
    id: str
    name: str
    path: str
    size: int
    type: str
    category: str
    genre: Optional[str] = None
    root_folder: Optional[str] = None
    extension: str
    modified_time: int
    thumbnail: Optional[str] = None
    stream_url: Optional[str] = None
    is_group: Optional[bool] = None
    episode_count: Optional[int] = None
    season_count: Optional[int] = None
    episode_no: Optional[int] = None
    season_no: Optional[int] = None
    episode_label: Optional[str] = None
    episodes: Optional[List[Dict[str, Any]]] = None
    sections: Optional[List[Dict[str, Any]]] = None
    autoplay_supported: Optional[bool] = None


class LibraryOverviewResponse(BaseModel):
    total_items: int
    counts: Dict[str, int]
    storage_used_bytes: int
    storage_total_bytes: int
    recent_items: List[LibraryItemResponse]
    featured_item: Optional[LibraryItemResponse] = None
    generated_at: int


class LibraryListResponse(BaseModel):
    category: str
    query: str
    sort: str
    total: int
    items: List[LibraryItemResponse]


class CategoriesResponse(BaseModel):
    categories: List[str]


@router.get("/categories", response_model=CategoriesResponse)
async def get_categories():
    return CategoriesResponse(categories=list(SUPPORTED_CATEGORIES))


@router.get("/overview", response_model=LibraryOverviewResponse)
async def get_overview(
    recent_limit: int = Query(12, ge=1, le=60, description="最近新增返回数量"),
    refresh: bool = Query(False, description="是否强制刷新扫描缓存"),
    group_tv: bool = Query(True, description="是否将剧集按系列聚合"),
):
    try:
        payload = get_library_overview(
            recent_limit=recent_limit,
            force_refresh=refresh,
            group_tv=group_tv,
        )
        return LibraryOverviewResponse(**payload)
    except Exception as exc:
        logger.error(f"Failed to build library overview: {exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc


@router.get("/category/{category}", response_model=LibraryListResponse)
async def get_category_items(
    category: str = PathParam(..., description="分类标识"),
    query: str = Query("", description="搜索关键词"),
    sort: str = Query("recent", pattern="^(recent|name|size)$", description="排序方式"),
    limit: int = Query(120, ge=1, le=500, description="返回数量上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
    refresh: bool = Query(False, description="是否强制刷新扫描缓存"),
    group_tv: bool = Query(True, description="是否将剧集按系列聚合"),
):
    try:
        payload = list_library_items(
            category=category,
            query=query,
            sort_by=sort,
            limit=limit,
            offset=offset,
            force_refresh=refresh,
            group_tv=group_tv,
        )
        return LibraryListResponse(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Failed to list library category {category}: {exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc

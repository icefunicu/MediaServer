"""
压缩包 API 路由

提供压缩包内容列表和文件解压功能。
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from pathlib import Path

from backend.logging_config import get_logger
from backend.services.archive import (
    ArchiveInfo,
    ExtractionError,
    ZipBombError,
    extract_file,
    list_archive_contents
)
from backend.services.filesystem import (
    FileNotFoundError,
    SecurityError,
    get_file_info,
    validate_path
)


logger = get_logger("api.archive")

router = APIRouter(prefix="/api/archive", tags=["压缩包管理"])
SUPPORTED_ARCHIVE_EXTENSIONS = {".zip", ".cbz", ".rar", ".cbr", ".7z"}


class ArchiveInfoResponse(BaseModel):
    """压缩包信息响应"""
    file_id: str
    format: str
    file_count: int
    total_size: int
    compressed_size: int
    entries: list


@router.get("/contents", response_model=ArchiveInfoResponse)
async def get_archive_contents(
    path: str = Query(..., description="文件路径")
):
    """
    获取压缩包内容列表
    """
    try:
        safe_path = validate_path(path)
        get_file_info(safe_path)
        suffix = Path(safe_path).suffix.lower()
        if suffix not in SUPPORTED_ARCHIVE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="不是压缩包文件")

        info = list_archive_contents(safe_path)
        return ArchiveInfoResponse(**info.to_dict())

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SecurityError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except ZipBombError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取压缩包内容失败: {path}, 错误: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/extract")
async def extract_archive_file(
    path: str = Query(..., description="压缩包路径"),
    entry: str = Query(..., description="压缩包内文件路径")
):
    """
    解压单个文件
    """
    try:
        safe_path = validate_path(path)
        get_file_info(safe_path)
        suffix = Path(safe_path).suffix.lower()
        if suffix not in SUPPORTED_ARCHIVE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="不是压缩包文件")

        data = extract_file(safe_path, entry)

        filename = entry.split('/')[-1]
        content_type = "application/octet-stream"
        if filename.endswith('.jpg') or filename.endswith('.jpeg'):
            content_type = "image/jpeg"
        elif filename.endswith('.png'):
            content_type = "image/png"
        elif filename.endswith('.gif'):
            content_type = "image/gif"
        elif filename.endswith('.txt'):
            content_type = "text/plain"
        elif filename.endswith('.json'):
            content_type = "application/json"
        elif filename.endswith('.xml'):
            content_type = "application/xml"

        return Response(
            content=data,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SecurityError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except ZipBombError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解压文件失败: {path}/{entry}, 错误: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")

"""
Video streaming API routes.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from backend.logging_config import get_logger
from backend.services.filesystem import (
    FileNotFoundError,
    SecurityError,
    get_file_info,
    get_mime_type,
    validate_path,
)
from backend.services.video_stream import (
    create_ios_compatible_stream,
    get_video_metadata,
    needs_ios_compatible_transcoding,
)


logger = get_logger("api.video")

router = APIRouter(prefix="/api/video", tags=["视频播放"])


def _is_ios_family_client(user_agent: str) -> bool:
    """Return True when request comes from iOS / iPadOS browsers."""
    ua = (user_agent or "").lower()
    if "iphone" in ua or "ipad" in ua or "ipod" in ua:
        return True
    return "macintosh" in ua and "mobile/" in ua


class VideoMetadataResponse(BaseModel):
    """Video metadata response."""

    file_id: str
    duration: float
    width: int
    height: int
    codec: str
    audio_codec: str
    bitrate: int
    fps: float
    format: str
    file_size: int


@router.get("/metadata", response_model=VideoMetadataResponse)
async def get_video_info(path: str = Query(..., description="文件路径")):
    """Get metadata for a video file."""
    try:
        safe_path = validate_path(path)
        entry = get_file_info(safe_path)

        if entry.type != "video":
            raise HTTPException(status_code=400, detail="不是视频文件")

        metadata = get_video_metadata(entry.id, safe_path)
        return VideoMetadataResponse(**metadata.to_dict())

    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecurityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"获取视频元数据失败: {path}, 错误: {exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc


@router.get("/stream")
async def stream_video_file(
    request: Request,
    path: str = Query(..., description="文件路径"),
    ios_compat: Optional[bool] = Query(
        default=None,
        description="是否强制启用 iOS 兼容实时转码，默认自动判断",
    ),
):
    """
    Stream a video file.
    Returns passthrough file response by default; when iOS compatibility
    is required, returns a transcoded MP4 stream.
    """
    try:
        safe_path = validate_path(path)
        entry = get_file_info(safe_path)

        if entry.type != "video":
            raise HTTPException(status_code=400, detail="不是视频文件")

        user_agent = request.headers.get("user-agent", "")
        is_ios_client = _is_ios_family_client(user_agent)
        force_ios_compat = ios_compat is True
        auto_ios_compat = (
            ios_compat is None
            and is_ios_client
            and needs_ios_compatible_transcoding(safe_path)
        )

        if force_ios_compat or auto_ios_compat:
            transcode_reason = "forced" if force_ios_compat else "auto"
            try:
                stream_iter = create_ios_compatible_stream(safe_path)
            except RuntimeError as exc:
                logger.error(f"iOS 兼容转码不可用: {safe_path}, 错误: {exc}")
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            return StreamingResponse(
                content=stream_iter,
                media_type="video/mp4",
                headers={
                    "Cache-Control": "no-store",
                    "X-Transcode-Mode": "ios-compat",
                    "X-Transcode-Reason": transcode_reason,
                },
            )

        return FileResponse(
            path=safe_path,
            media_type=get_mime_type(safe_path),
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",
                "X-Transcode-Mode": "passthrough",
            },
        )

    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecurityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"视频流传输失败: {path}, 错误: {exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc


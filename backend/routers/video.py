"""Video streaming API routes."""

from pathlib import Path
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
    ensure_compatible_mp4,
    generate_video_thumbnail,
    get_transcoded_cache_path,
    get_video_metadata,
    needs_compatible_transcoding,
)


logger = get_logger("api.video")

router = APIRouter(prefix="/api/video", tags=["视频播放"])
LIVE_COMPAT_STREAM_EXTENSIONS = {".ts", ".m2ts", ".mts"}


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
        logger.error(f"Failed to load video metadata: {path}, error={exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc


@router.get("/stream")
async def stream_video_file(
    request: Request,
    path: str = Query(..., description="文件路径"),
    ios_compat: Optional[bool] = Query(
        default=None,
        description="是否强制启用兼容转码（默认自动判断）",
    ),
    start: Optional[float] = Query(default=None, ge=0),
):
    """
    Stream a video file.

    - Default: passthrough when browser can natively play the container.
    - Auto mode: use compatible MP4 cache when container is not natively playable.
    - Forced mode (`ios_compat=1`): always use compatibility mode.
    """
    try:
        safe_path = validate_path(path)
        entry = get_file_info(safe_path)

        if entry.type != "video":
            raise HTTPException(status_code=400, detail="不是视频文件")

        user_agent = request.headers.get("user-agent", "")
        is_ios_client = _is_ios_family_client(user_agent)

        force_compat = ios_compat is True
        auto_compat = (
            ios_compat is None
            and needs_compatible_transcoding(safe_path, is_ios_client=is_ios_client)
        )

        if force_compat or auto_compat:
            transcode_reason = "forced" if force_compat else "auto"
            source_extension = Path(safe_path).suffix.lower()

            if start is not None:
                start_seconds = max(0.0, float(start))
                duration = 0.0
                try:
                    metadata = get_video_metadata(entry.id, safe_path)
                    duration = float(metadata.duration)
                except Exception as exc:
                    logger.warning(
                        f"Failed to probe duration for compat live stream: {safe_path}, error={exc}"
                    )

                if duration > 0 and start_seconds >= duration:
                    start_seconds = max(0.0, duration - 0.5)

                live_stream = create_ios_compatible_stream(
                    safe_path,
                    start_seconds=start_seconds,
                )
                headers = {
                    "Accept-Ranges": "none",
                    "Cache-Control": "no-store",
                    "X-Transcode-Mode": "compat-live",
                    "X-Transcode-Reason": transcode_reason,
                    "X-Stream-Start": f"{start_seconds:.3f}",
                }
                if duration > 0:
                    headers["X-Media-Duration"] = f"{duration:.3f}"

                return StreamingResponse(
                    content=live_stream,
                    media_type="video/mp4",
                    headers=headers,
                )

            if source_extension in LIVE_COMPAT_STREAM_EXTENSIONS:
                cache_path = Path(get_transcoded_cache_path(entry.id, "mp4"))
                if cache_path.exists() and cache_path.stat().st_size > 0:
                    return FileResponse(
                        path=str(cache_path),
                        media_type="video/mp4",
                        headers={
                            "Accept-Ranges": "bytes",
                            "Cache-Control": "public, max-age=3600",
                            "X-Transcode-Mode": "compat-cache",
                            "X-Transcode-Reason": transcode_reason,
                        },
                    )

                live_stream = create_ios_compatible_stream(safe_path)
                return StreamingResponse(
                    content=live_stream,
                    media_type="video/mp4",
                    headers={
                        "Accept-Ranges": "none",
                        "Cache-Control": "no-store",
                        "X-Transcode-Mode": "compat-live",
                        "X-Transcode-Reason": transcode_reason,
                    },
                )

            try:
                compat_path = ensure_compatible_mp4(safe_path, entry.id)
            except RuntimeError as exc:
                logger.error(f"Compatible transcoding unavailable: {safe_path}, error={exc}")
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            return FileResponse(
                path=compat_path,
                media_type="video/mp4",
                headers={
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "public, max-age=3600",
                    "X-Transcode-Mode": "compat-cache",
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
        logger.error(f"Failed to stream video: {path}, error={exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc


@router.get("/thumbnail")
async def get_video_thumbnail(
    path: str = Query(..., description="文件路径"),
    timestamp: Optional[str] = Query(None, description="截图时间(HH:MM:SS 或秒数)")
):
    """获取视频在指定时间点的缩略图。"""
    try:
        safe_path = validate_path(path)
        entry = get_file_info(safe_path)

        if entry.type != "video":
            raise HTTPException(status_code=400, detail="不是视频文件")

        calc_timestamp = timestamp
        if not calc_timestamp:
            try:
                metadata = get_video_metadata(entry.id, safe_path)
                duration = metadata.duration
                if duration > 0:
                    target_time = duration * 0.2
                    calc_timestamp = f"{target_time:.3f}"
                else:
                    calc_timestamp = "10.000"
            except Exception as exc:
                logger.warning(f"Failed to detect video duration, fallback timestamp used: {exc}")
                calc_timestamp = "10.000"

        thumbnail_path = generate_video_thumbnail(safe_path, entry.id, calc_timestamp)

        return FileResponse(
            path=thumbnail_path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=86400",
            },
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SecurityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error(f"Failed to generate video thumbnail: {path}, error={exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get video thumbnail: {path}, error={exc}")
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc

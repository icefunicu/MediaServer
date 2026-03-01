"""
视频流媒体模块

提供视频元数据获取、流式传输、转码等功能。
"""

import os
import shutil
import subprocess
import hashlib
from pathlib import Path
from typing import Iterator, Optional

import ffmpeg

from backend.config import get_config
from backend.logging_config import get_logger
from backend.services.filesystem import (
    FileEntry,
    get_file_info,
    get_file_size,
    get_mime_type,
    validate_path
)
from backend.services.range_parser import (
    RangeParseError,
    build_range_response_headers,
    parse_range_header
)


logger = get_logger("video_stream")

IOS_NATIVE_CONTAINERS = {".mp4", ".m4v", ".mov"}
BROWSER_NATIVE_CONTAINERS = {".mp4", ".m4v", ".mov", ".webm", ".ogg"}
REMUX_RISKY_CONTAINERS = {".ts", ".m2ts", ".mts", ".vob", ".mpg", ".mpeg", ".tp"}
BROWSER_COMPAT_VIDEO_CODECS = {"h264"}
BROWSER_COMPAT_AUDIO_CODECS = {"aac", "mp3"}
BROWSER_COMPAT_PIXEL_FORMAT_PREFIXES = ("yuv420",)


class VideoMetadata:
    """视频元数据数据模型"""

    def __init__(
        self,
        file_id: str,
        duration: float,
        width: int,
        height: int,
        codec: str,
        audio_codec: str,
        bitrate: int,
        fps: float,
        format: str,
        file_size: int
    ):
        self.file_id = file_id
        self.duration = duration
        self.width = width
        self.height = height
        self.codec = codec
        self.audio_codec = audio_codec
        self.bitrate = bitrate
        self.fps = fps
        self.format = format
        self.file_size = file_size

    def to_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "codec": self.codec,
            "audio_codec": self.audio_codec,
            "bitrate": self.bitrate,
            "fps": self.fps,
            "format": self.format,
            "file_size": self.file_size
        }


class StreamResponse:
    """流响应数据模型"""

    def __init__(
        self,
        content: bytes,
        status_code: int,
        headers: dict,
        content_range: Optional[str],
        content_length: int,
        content_type: str
    ):
        self.content = content
        self.status_code = status_code
        self.headers = headers
        self.content_range = content_range
        self.content_length = content_length
        self.content_type = content_type


def get_video_metadata(file_id: str, file_path: str) -> VideoMetadata:
    """
    获取视频元数据

    Args:
        file_id: 文件唯一标识符
        file_path: 文件路径

    Returns:
        VideoMetadata 对象
    """
    try:
        safe_path = validate_path(file_path)
        path = Path(safe_path)

        if not path.exists():
            raise FileNotFoundError(f"视频文件不存在: {file_path}")

        file_size = path.stat().st_size

        try:
            probe = ffmpeg.probe(str(path))
            video_stream = next(
                (s for s in probe['streams'] if s['codec_type'] == 'video'),
                None
            )
            audio_stream = next(
                (s for s in probe['streams'] if s['codec_type'] == 'audio'),
                None
            )

            if video_stream is None:
                raise ValueError("未找到视频流")

            duration = float(probe['format'].get('duration', 0))
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))
            codec = video_stream.get('codec_name', 'unknown')
            fps_str = video_stream.get('r_frame_rate', '0/1')
            if '/' in fps_str:
                num, den = fps_str.split('/')
                fps = float(num) / float(den) if float(den) != 0 else 0
            else:
                fps = float(fps_str)

            audio_codec = audio_stream.get('codec_name', 'unknown') if audio_stream else 'unknown'

            bitrate = int(probe['format'].get('bit_rate', 0))

            return VideoMetadata(
                file_id=file_id,
                duration=duration,
                width=width,
                height=height,
                codec=codec,
                audio_codec=audio_codec,
                bitrate=bitrate,
                fps=fps,
                format=path.suffix[1:].lower(),
                file_size=file_size
            )

        except ffmpeg.Error as e:
            logger.warning(f"FFmpeg 获取元数据失败，使用基本元数据: {e}")
            return VideoMetadata(
                file_id=file_id,
                duration=0,
                width=0,
                height=0,
                codec='unknown',
                audio_codec='unknown',
                bitrate=0,
                fps=0,
                format=path.suffix[1:].lower(),
                file_size=file_size
            )

    except Exception as e:
        logger.error(f"获取视频元数据失败: {file_path}, 错误: {e}")
        raise


def stream_video(file_id: str, file_path: str, range_header: Optional[str] = None) -> StreamResponse:
    """
    流式传输视频数据

    Args:
        file_id: 文件唯一标识符
        file_path: 文件路径
        range_header: HTTP Range 请求头（可选）

    Returns:
        StreamResponse 对象
    """
    try:
        safe_path = validate_path(file_path)
        path = Path(safe_path)

        if not path.exists():
            raise FileNotFoundError(f"视频文件不存在: {file_path}")

        file_size = path.stat().st_size
        content_type = get_mime_type(str(path))

        if range_header:
            try:
                start, end = parse_range_header(range_header, file_size)
                status_code = 206
                content_range = f"bytes {start}-{end}/{file_size}"
            except RangeParseError as e:
                logger.warning(f"Range 请求解析失败: {e}")
                start = 0
                end = file_size - 1
                status_code = 200
                content_range = None
        else:
            start = 0
            end = file_size - 1
            status_code = 200
            content_range = None

        with open(path, 'rb') as f:
            f.seek(start)
            chunk_size = end - start + 1
            content = f.read(chunk_size)

        headers = {
            "Content-Type": content_type,
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(content))
        }

        if content_range:
            headers["Content-Range"] = content_range

        return StreamResponse(
            content=content,
            status_code=status_code,
            headers=headers,
            content_range=content_range,
            content_length=len(content),
            content_type=content_type
        )

    except FileNotFoundError:
        raise
    except Exception as e:
        logger.error(f"视频流传输失败: {file_path}, 错误: {e}")
        raise


def needs_transcoding(file_path: str) -> bool:
    """
    判断是否需要转码

    Args:
        file_path: 文件路径

    Returns:
        是否需要转码
    """
    supported_formats = ['mp4', 'webm', 'ogg']
    extension = Path(file_path).suffix[1:].lower()
    return extension not in supported_formats


def transcode_video(
    input_path: str,
    output_path: str,
    target_format: str = 'mp4'
) -> bool:
    """
    使用 FFmpeg 转码视频

    Args:
        input_path: 输入视频路径
        output_path: 输出视频路径
        target_format: 目标格式（mp4/webm）

    Returns:
        转码是否成功
    """
    try:
        input_safe = validate_path(input_path)
        input_file = Path(input_safe)

        if not input_file.exists():
            logger.error(f"转码输入文件不存在: {input_path}")
            return False

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if target_format == 'mp4':
            codec = 'libx264'
            audio_codec = 'aac'
        elif target_format == 'webm':
            codec = 'libvpx-vp9'
            audio_codec = 'libopus'
        else:
            codec = 'copy'
            audio_codec = 'copy'

        try:
            stream = ffmpeg.input(str(input_file))
            stream = ffmpeg.output(
                stream,
                str(output_file),
                vcodec=codec,
                acodec=audio_codec,
                movflags='+faststart',
                y=None
            )
            ffmpeg.run(stream, capture_stdout=True, capture_stderr=True, timeout=3600)

            if output_file.exists() and output_file.stat().st_size > 0:
                logger.info(f"视频转码成功: {input_path} -> {output_path}")
                return True
            else:
                logger.error(f"转码输出文件无效: {output_path}")
                return False

        except ffmpeg.Error as e:
            logger.error(f"FFmpeg 转码失败: {e.stderr.decode() if e.stderr else str(e)}")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"转码超时（1小时）: {input_path}")
            return False
        except Exception as e:
            logger.error(f"转码失败: {input_path}, 错误: {e}")
            return False

    except Exception as e:
        logger.error(f"转码失败: {input_path}, 错误: {e}")
        return False


def get_transcoded_cache_path(file_id: str, target_format: str) -> str:
    """获取转码缓存文件路径"""
    cache_dir = Path(__file__).resolve().parents[2] / "cache" / "transcoded"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return str(cache_dir / f"{file_id}.{target_format}")


def _probe_primary_av_streams(file_path: Path) -> tuple[Optional[dict], Optional[dict], str]:
    """Return primary video/audio stream metadata with format name."""
    try:
        probe = ffmpeg.probe(str(file_path))
    except ffmpeg.Error:
        return None, None, ""

    streams = probe.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    format_name = str((probe.get("format") or {}).get("format_name", "")).lower()
    return video_stream, audio_stream, format_name


def _has_browser_compatible_codecs(file_path: Path) -> bool:
    """Check whether codecs are natively decodable by mainstream browsers."""
    video_stream, audio_stream, _ = _probe_primary_av_streams(file_path)
    if not video_stream:
        return False

    video_codec = str(video_stream.get("codec_name", "")).lower()
    if video_codec not in BROWSER_COMPAT_VIDEO_CODECS:
        return False

    pixel_format = str(video_stream.get("pix_fmt", "")).lower()
    if pixel_format and not pixel_format.startswith(BROWSER_COMPAT_PIXEL_FORMAT_PREFIXES):
        return False

    if audio_stream:
        audio_codec = str(audio_stream.get("codec_name", "")).lower()
        if audio_codec not in BROWSER_COMPAT_AUDIO_CODECS:
            return False

    return True


def _is_browser_compatible_mp4(file_path: Path) -> bool:
    """Check whether file is MP4 container + browser-compatible codecs."""
    _, _, format_name = _probe_primary_av_streams(file_path)
    if "mp4" not in format_name:
        return False
    return _has_browser_compatible_codecs(file_path)


def _can_fast_remux_to_compatible_mp4(file_path: Path) -> bool:
    """
    Decide whether copy-remux is safe enough.
    Risky source containers (ts/m2ts/vob/...) go through re-encode directly.
    """
    if file_path.suffix.lower() in REMUX_RISKY_CONTAINERS:
        return False
    return _has_browser_compatible_codecs(file_path)


def ensure_compatible_mp4(file_path: str, file_id: str) -> str:
    """
    Build (or reuse) a cached MP4 file for broad browser compatibility.
    The generated file is seekable via HTTP Range and exposes full duration.
    """
    safe_path = validate_path(file_path)
    input_file = Path(safe_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Video file not found: {file_path}")

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("FFmpeg is not installed or unavailable")

    output_file = Path(get_transcoded_cache_path(file_id, "mp4"))
    if output_file.exists() and output_file.stat().st_size > 0:
        if (
            output_file.stat().st_mtime >= input_file.stat().st_mtime
            and _is_browser_compatible_mp4(output_file)
        ):
            return str(output_file)
        logger.warning(f"Discarding stale or incompatible cache file: {output_file}")
        output_file.unlink(missing_ok=True)

    tmp_file = output_file.with_name(f"{output_file.name}.tmp")
    if tmp_file.exists():
        tmp_file.unlink()

    output_file.parent.mkdir(parents=True, exist_ok=True)

    remux_cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_file),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(tmp_file),
    ]

    reencode_cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_file),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(tmp_file),
    ]

    try:
        remux_ok = False
        if _can_fast_remux_to_compatible_mp4(input_file):
            try:
                subprocess.run(
                    remux_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    timeout=3600,
                )
                remux_ok = tmp_file.exists() and tmp_file.stat().st_size > 0 and _is_browser_compatible_mp4(tmp_file)
                if not remux_ok:
                    logger.warning(f"Remux output is not browser-compatible, fallback to re-encode: {input_file}")
                    tmp_file.unlink(missing_ok=True)
            except Exception:
                remux_ok = False
                tmp_file.unlink(missing_ok=True)

        if not remux_ok:
            subprocess.run(
                reencode_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=7200,
            )

        if (
            not tmp_file.exists()
            or tmp_file.stat().st_size <= 0
            or not _is_browser_compatible_mp4(tmp_file)
        ):
            raise RuntimeError("Failed to generate compatible MP4 cache file")

        tmp_file.replace(output_file)
        return str(output_file)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Compatible MP4 conversion timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Compatible MP4 conversion failed") from exc
    finally:
        if tmp_file.exists():
            tmp_file.unlink(missing_ok=True)


def needs_ios_compatible_transcoding(file_path: str) -> bool:
    """判断视频是否需要 iOS 兼容转码。"""
    return needs_compatible_transcoding(file_path, is_ios_client=True)


def needs_compatible_transcoding(file_path: str, is_ios_client: bool = False) -> bool:
    """Determine whether a file should use compatibility transcoding."""
    extension = Path(file_path).suffix.lower()
    native_containers = IOS_NATIVE_CONTAINERS if is_ios_client else BROWSER_NATIVE_CONTAINERS
    return extension not in native_containers


def create_ios_compatible_stream(
    file_path: str,
    chunk_size: int = 256 * 1024,
    start_seconds: float = 0.0,
) -> Iterator[bytes]:
    """
    将任意视频实时转码为 iOS 兼容的 fragmented MP4（H264/AAC）。

    注意：
    - 这是实时转码流，不支持 Range/随机定位
    - 主要用于 iOS 对 mkv/ts 等容器的兼容播放
    """
    safe_path = validate_path(file_path)
    path = Path(safe_path)
    if not path.exists():
        raise FileNotFoundError(f"视频文件不存在: {file_path}")

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("FFmpeg 未安装或不可用，无法进行 iOS 兼容转码")

    normalized_start = 0.0
    try:
        parsed_start = float(start_seconds)
        if parsed_start > 0:
            normalized_start = parsed_start
    except (TypeError, ValueError):
        normalized_start = 0.0

    command = [
        ffmpeg_bin,
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
    ]

    if normalized_start > 0:
        # Place -ss before input for fast seek on open/drag operations.
        command.extend(["-ss", f"{normalized_start:.3f}"])

    command.extend([
        "-i", str(path),
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "zerolatency",
        "-threads", "0",
        "-profile:v", "high",
        "-level", "4.1",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-ac", "2",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof+faststart",
        "-f", "mp4",
        "pipe:1",
    ])

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        bufsize=0,
    )

    def _iter_stream() -> Iterator[bytes]:
        try:
            if not process.stdout:
                return
            while True:
                chunk = process.stdout.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            if process.poll() is None:
                process.kill()
            if process.stdout:
                process.stdout.close()

    return _iter_stream()


def get_thumbnail_cache_path(file_id: str, timestamp_str: str) -> Path:
    """获取缩略图缓存文件路径"""
    cache_dir = Path(__file__).resolve().parents[2] / "cache" / "thumbnails"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # 用哈希避免文件名在不同系统中的非法字符问题
    hash_key = hashlib.md5(f"{file_id}_{timestamp_str}".encode('utf-8')).hexdigest()
    return cache_dir / f"{hash_key}.jpg"


def generate_video_thumbnail(file_path: str, file_id: str, timestamp_str: str = "00:00:05") -> str:
    """
    生成视频指定时间点的缩略图，并返回缓存的文件路径
    """
    safe_path = validate_path(file_path)
    path = Path(safe_path)
    if not path.exists():
        raise FileNotFoundError(f"视频文件不存在: {file_path}")

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("FFmpeg 未安装或不可用")

    cache_path = get_thumbnail_cache_path(file_id, timestamp_str)
    
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return str(cache_path)

    # 用临时文件生成，避免并发读取到未完成的文件
    tmp_path = cache_path.with_suffix(".tmp")

    command = [
        ffmpeg_bin,
        "-y",               # 覆盖输出
        "-ss", timestamp_str,
        "-i", str(path),
        "-vframes", "1",    # 只提取 1 帧
        "-q:v", "2",        # 高质量 JPEG
        "-f", "image2",
        str(tmp_path)
    ]

    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=30 # 超时时间 30s
        )
        
        # 原子性重命名
        if tmp_path.exists() and tmp_path.stat().st_size > 0:
            tmp_path.replace(cache_path)
            return str(cache_path)
        else:
            raise RuntimeError("ffmpeg 生成缩略图失败(文件为空)")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg 生成缩略图失败: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"生成缩略图失败由于 ffmpeg 错误: {e}")
    except subprocess.TimeoutExpired:
        logger.error(f"ffmpeg 生成缩略图超时: {file_path}")
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError("生成缩略图超时")
    except Exception as e:
        logger.error(f"生成缩略图发生意外错误: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        raise

"""
API 集成测试

覆盖核心接口：
- 健康检查
- 文件列表
- 视频流（含 Range 请求）
- 压缩包内容与提取
"""

import zipfile
import io
import base64
from pathlib import Path

import pytest
import py7zr
import yaml
from fastapi.testclient import TestClient

from backend.config import reload_config
from backend.main import create_app


def _build_test_config(media_root: Path) -> dict:
    return {
        "server": {
            "host": "127.0.0.1",
            "port": 8001,
            "debug": False,
        },
        "media": {
            "root_directory": str(media_root),
            "video_formats": [".mp4", ".mkv", ".ts", ".avi", ".mov"],
            "comic_formats": [".cbz", ".cbr", ".zip", ".7z"],
            "archive_formats": [".zip", ".rar", ".7z"],
        },
        "cache": {
            "memory_cache_size": 104857600,
            "disk_cache_size": 10737418240,
            "metadata_ttl": 3600,
            "image_ttl": 3600,
            "transcoded_ttl": 86400,
        },
        "security": {
            "max_concurrent_connections": 100,
            "rate_limit_per_minute": 60,
            "max_file_size": 104857600,
            "max_extracted_size": 1073741824,
            "compression_ratio_limit": 1000,
        },
        "log": {
            "level": "INFO",
            "format": "text",
            "file": None,
            "max_bytes": 10485760,
            "backup_count": 5,
        },
    }


@pytest.fixture
def client(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    (media_dir / "sample.mp4").write_bytes(b"0123456789" * 200)
    (media_dir / "sample.mkv").write_bytes(b"mkv-test-data" * 200)

    with zipfile.ZipFile(media_dir / "sample.zip", "w") as zf:
        zf.writestr("hello.txt", b"hello archive")

    with zipfile.ZipFile(media_dir / "comic.zip", "w") as zf:
        zf.writestr("001.jpg", b"fake-jpeg-1")
        zf.writestr("002.jpg", b"fake-jpeg-2")

    valid_png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO5nYQAAAABJRU5ErkJggg=="
    )
    with zipfile.ZipFile(media_dir / "comic_valid.zip", "w") as zf:
        zf.writestr("001.png", valid_png_data)

    seed_dir = media_dir / "_seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    (seed_dir / "hello.txt").write_bytes(b"hello from 7z")
    (seed_dir / "001.jpg").write_bytes(b"fake-7z-jpeg-1")
    (seed_dir / "002.jpg").write_bytes(b"fake-7z-jpeg-2")

    with py7zr.SevenZipFile(media_dir / "sample.7z", "w") as szf:
        szf.write(seed_dir / "hello.txt", "hello.txt")

    with py7zr.SevenZipFile(media_dir / "comic.7z", "w") as szf:
        szf.write(seed_dir / "001.jpg", "001.jpg")
        szf.write(seed_dir / "002.jpg", "002.jpg")

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(_build_test_config(media_dir), allow_unicode=True),
        encoding="utf-8",
    )

    reload_config(str(cfg_path))
    app = create_app()

    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_list_files(client: TestClient):
    resp = client.get("/api/files", params={"path": "/"})
    assert resp.status_code == 200
    names = {item["name"] for item in resp.json()["files"]}
    assert "sample.mp4" in names
    assert "sample.zip" in names


def test_video_stream_range(client: TestClient):
    resp = client.get(
        "/api/video/stream",
        params={"path": "/sample.mp4"},
        headers={"Range": "bytes=0-99"},
    )
    assert resp.status_code == 206
    assert resp.headers["content-range"].startswith("bytes 0-99/")
    assert len(resp.content) == 100


def test_video_stream_ios_compat_forced(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import backend.routers.video as video_router

    def fake_ios_stream(_path: str):
        yield b"ios-"
        yield b"compat"

    monkeypatch.setattr(video_router, "create_ios_compatible_stream", fake_ios_stream)

    resp = client.get(
        "/api/video/stream",
        params={"path": "/sample.mp4", "ios_compat": 1},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("video/mp4")
    assert resp.headers["x-transcode-mode"] == "ios-compat"
    assert resp.headers["x-transcode-reason"] == "forced"
    assert resp.content == b"ios-compat"


def test_video_stream_ios_auto_for_mkv(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import backend.routers.video as video_router

    def fake_ios_stream(_path: str):
        yield b"auto-ios"

    monkeypatch.setattr(video_router, "create_ios_compatible_stream", fake_ios_stream)

    resp = client.get(
        "/api/video/stream",
        params={"path": "/sample.mkv"},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            )
        },
    )
    assert resp.status_code == 200
    assert resp.headers["x-transcode-mode"] == "ios-compat"
    assert resp.headers["x-transcode-reason"] == "auto"
    assert resp.content == b"auto-ios"


def test_archive_contents_and_extract(client: TestClient):
    contents = client.get("/api/archive/contents", params={"path": "/sample.zip"})
    assert contents.status_code == 200
    data = contents.json()
    assert data["file_count"] == 1

    extracted = client.get(
        "/api/archive/extract",
        params={"path": "/sample.zip", "entry": "hello.txt"},
    )
    assert extracted.status_code == 200
    assert extracted.content == b"hello archive"


def test_comic_zip_metadata_and_page(client: TestClient):
    metadata = client.get("/api/comic/metadata", params={"path": "/comic.zip"})
    assert metadata.status_code == 200
    assert metadata.json()["page_count"] == 2

    page = client.get("/api/comic/page", params={"path": "/comic.zip", "page": 1})
    assert page.status_code == 200
    assert page.content == b"fake-jpeg-1"


def test_archive_7z_contents_and_extract(client: TestClient):
    contents = client.get("/api/archive/contents", params={"path": "/sample.7z"})
    assert contents.status_code == 200
    assert contents.json()["file_count"] == 1

    extracted = client.get(
        "/api/archive/extract",
        params={"path": "/sample.7z", "entry": "hello.txt"},
    )
    assert extracted.status_code == 200
    assert extracted.content == b"hello from 7z"


def test_comic_7z_metadata_and_page(client: TestClient):
    metadata = client.get("/api/comic/metadata", params={"path": "/comic.7z"})
    assert metadata.status_code == 200
    assert metadata.json()["page_count"] == 2

    page = client.get("/api/comic/page", params={"path": "/comic.7z", "page": 1})
    assert page.status_code == 200
    assert page.content == b"fake-7z-jpeg-1"


def test_comic_page_optimized_and_etag(client: TestClient):
    pil = pytest.importorskip("PIL")
    image_module = pil.Image

    params = {
        "path": "/comic_valid.zip",
        "page": 1,
        "max_width": 900,
        "quality": 80,
        "format": "jpeg",
    }
    first = client.get("/api/comic/page", params=params)
    assert first.status_code == 200
    assert first.headers["etag"]
    assert first.headers["cache-control"] == "public, max-age=86400"
    assert first.headers["content-type"].startswith("image/jpeg")

    image = image_module.open(io.BytesIO(first.content))
    assert image.width <= 900

    cached = client.get(
        "/api/comic/page",
        params=params,
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert cached.status_code == 304

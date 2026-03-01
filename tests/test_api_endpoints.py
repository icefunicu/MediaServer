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
import tarfile
from pathlib import Path
from types import SimpleNamespace

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
            "video_formats": [".mp4", ".mkv", ".ts", ".avi", ".mov", ".vob"],
            "audio_formats": [".mp3", ".flac", ".m4a", ".wav", ".aac", ".ogg"],
            "image_formats": [".jpg", ".jpeg", ".png", ".webp"],
            "comic_formats": [
                ".cbz",
                ".cbr",
                ".zip",
                ".cb7",
                ".7z",
                ".cbt",
                ".tar",
                ".tar.gz",
                ".tgz",
                ".tar.bz2",
                ".tbz2",
                ".tar.xz",
                ".txz",
            ],
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
    (media_dir / "sample.ts").write_bytes(b"ts-test-data" * 200)
    (media_dir / "sample.vob").write_bytes(b"vob-test-data" * 200)
    (media_dir / "Movie.Night.2025.mp4").write_bytes(b"movie-data" * 100)
    (media_dir / "Cool.Show.S01E01.mkv").write_bytes(b"tv-data" * 100)
    (media_dir / "蜡笔小新" / "第1季").mkdir(parents=True, exist_ok=True)
    (media_dir / "蜡笔小新" / "第1季" / "S01E01.mp4").write_bytes(b"anime-data" * 80)
    (media_dir / "JMV" / "Sample Drama").mkdir(parents=True, exist_ok=True)
    (media_dir / "JMV" / "Sample Drama" / "S01E01.mp4").write_bytes(b"jdrama-data" * 80)
    (media_dir / "JMV" / "Sample Drama" / "S01E02.mp4").write_bytes(b"jdrama-data-2" * 80)
    (media_dir / "song.mp3").write_bytes(b"ID3-song-data" * 80)
    (media_dir / "cover.jpg").write_bytes(b"fake-jpg-data")

    with zipfile.ZipFile(media_dir / "sample.zip", "w") as zf:
        zf.writestr("hello.txt", b"hello archive")

    with zipfile.ZipFile(media_dir / "comic.zip", "w") as zf:
        zf.writestr("001.jpg", b"fake-jpeg-1")
        zf.writestr("002.jpg", b"fake-jpeg-2")
    (media_dir / "comic_broken.zip").write_bytes(b"not-a-real-zip")

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

    with py7zr.SevenZipFile(media_dir / "comic.cb7", "w") as szf:
        szf.write(seed_dir / "001.jpg", "001.jpg")
        szf.write(seed_dir / "002.jpg", "002.jpg")

    # 7z payload with .zip extension, used to verify format fallback.
    with py7zr.SevenZipFile(media_dir / "comic_7z_named_zip.zip", "w") as szf:
        szf.write(seed_dir / "001.jpg", "001.jpg")
        szf.write(seed_dir / "002.jpg", "002.jpg")

    with tarfile.open(media_dir / "comic.cbt", "w") as tf:
        tf.add(seed_dir / "001.jpg", arcname="001.jpg")
        tf.add(seed_dir / "002.jpg", arcname="002.jpg")

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
    assert "sample.vob" in names
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

    def fake_compat_path(path: str, _file_id: str) -> str:
        return path

    monkeypatch.setattr(video_router, "ensure_compatible_mp4", fake_compat_path)

    resp = client.get(
        "/api/video/stream",
        params={"path": "/sample.mp4", "ios_compat": 1},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("video/mp4")
    assert resp.headers["x-transcode-mode"] == "compat-cache"
    assert resp.headers["x-transcode-reason"] == "forced"
    assert len(resp.content) > 0


def test_video_stream_ios_auto_for_mkv(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import backend.routers.video as video_router

    def fake_compat_path(path: str, _file_id: str) -> str:
        return path.replace(".mkv", ".mp4")

    monkeypatch.setattr(video_router, "ensure_compatible_mp4", fake_compat_path)

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
    assert resp.headers["x-transcode-mode"] == "compat-cache"
    assert resp.headers["x-transcode-reason"] == "auto"
    assert len(resp.content) > 0


def test_video_stream_desktop_auto_compat_for_mkv(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import backend.routers.video as video_router

    def fake_compat_path(path: str, _file_id: str) -> str:
        return path.replace(".mkv", ".mp4")

    monkeypatch.setattr(video_router, "ensure_compatible_mp4", fake_compat_path)

    resp = client.get(
        "/api/video/stream",
        params={"path": "/sample.mkv"},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        },
    )
    assert resp.status_code == 200
    assert resp.headers["x-transcode-mode"] == "compat-cache"
    assert resp.headers["x-transcode-reason"] == "auto"
    assert resp.headers["content-type"].startswith("video/mp4")


def test_video_stream_auto_compat_for_vob(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import backend.routers.video as video_router

    def fake_compat_path(path: str, _file_id: str) -> str:
        assert path.endswith(".vob")
        return path.replace(".vob", ".mp4")

    monkeypatch.setattr(video_router, "ensure_compatible_mp4", fake_compat_path)

    resp = client.get(
        "/api/video/stream",
        params={"path": "/sample.vob"},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        },
    )
    assert resp.status_code == 200
    assert resp.headers["x-transcode-mode"] == "compat-cache"
    assert resp.headers["x-transcode-reason"] == "auto"
    assert resp.headers["content-type"].startswith("video/mp4")


def test_video_stream_ts_compat_live(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import backend.routers.video as video_router

    def fake_live_stream(_path: str):
        yield b"mp4-frag-1"
        yield b"mp4-frag-2"

    def fail_cache(*_args, **_kwargs):
        raise AssertionError("ensure_compatible_mp4 should not be called for ts live mode")

    monkeypatch.setattr(video_router, "create_ios_compatible_stream", fake_live_stream)
    monkeypatch.setattr(video_router, "ensure_compatible_mp4", fail_cache)

    resp = client.get(
        "/api/video/stream",
        params={"path": "/sample.ts", "ios_compat": 1},
    )
    assert resp.status_code == 200
    assert resp.headers["x-transcode-mode"] == "compat-live"
    assert resp.headers["x-transcode-reason"] == "forced"
    assert resp.headers["accept-ranges"] == "none"
    assert resp.content == b"mp4-frag-1mp4-frag-2"


def test_video_stream_start_uses_compat_live_chunks(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import backend.routers.video as video_router

    captured = {"start": None}

    def fake_live_stream(_path: str, start_seconds: float = 0.0):
        captured["start"] = start_seconds
        yield b"chunk-1"
        yield b"chunk-2"

    def fail_cache(*_args, **_kwargs):
        raise AssertionError("ensure_compatible_mp4 should not be called when start is provided")

    monkeypatch.setattr(video_router, "create_ios_compatible_stream", fake_live_stream)
    monkeypatch.setattr(video_router, "ensure_compatible_mp4", fail_cache)
    monkeypatch.setattr(
        video_router,
        "get_video_metadata",
        lambda *_args, **_kwargs: SimpleNamespace(duration=120.0),
    )

    resp = client.get(
        "/api/video/stream",
        params={"path": "/sample.mkv", "ios_compat": 1, "start": 42.5},
    )
    assert resp.status_code == 200
    assert resp.headers["x-transcode-mode"] == "compat-live"
    assert resp.headers["x-transcode-reason"] == "forced"
    assert resp.headers["x-stream-start"] == "42.500"
    assert resp.headers["x-media-duration"] == "120.000"
    assert captured["start"] == 42.5
    assert resp.content == b"chunk-1chunk-2"


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


def test_library_overview(client: TestClient):
    resp = client.get("/api/library/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] >= 1
    assert "movies" in data["counts"]
    assert "tv" in data["counts"]
    assert isinstance(data["recent_items"], list)


def test_library_category_filters(client: TestClient):
    tv_resp = client.get("/api/library/category/tv")
    assert tv_resp.status_code == 200
    tv_payload = tv_resp.json()
    tv_names = {item["name"] for item in tv_payload["items"]}
    if "Cool.Show.S01E01.mkv" not in tv_names:
        grouped_episodes = []
        for item in tv_payload["items"]:
            if item.get("type") != "tv_series":
                continue
            grouped_episodes.extend(item.get("episodes") or [])
        episode_names = {episode["name"] for episode in grouped_episodes}
        assert "Cool.Show.S01E01.mkv" in episode_names

    music_resp = client.get("/api/library/category/music")
    assert music_resp.status_code == 200
    music_payload = music_resp.json()
    music_names = {item["name"] for item in music_payload["items"]}
    assert "song.mp3" in music_names


def test_library_category_anime_and_jdrama(client: TestClient):
    anime_resp = client.get("/api/library/category/anime")
    assert anime_resp.status_code == 200
    anime_items = anime_resp.json()["items"]
    assert anime_items
    assert all(item.get("genre") == "anime" for item in anime_items)

    jdrama_resp = client.get("/api/library/category/jdrama")
    assert jdrama_resp.status_code == 200
    jdrama_items = jdrama_resp.json()["items"]
    assert jdrama_items
    assert all(item.get("genre") == "jdrama" for item in jdrama_items)
    assert all(item.get("type") != "tv_series" for item in jdrama_items)
    jdrama_names = {item["name"] for item in jdrama_items}
    assert "S01E01.mp4" in jdrama_names
    assert "S01E02.mp4" in jdrama_names


def test_comic_cards_include_thumbnail_cover(client: TestClient):
    resp = client.get("/api/library/category/comics")
    assert resp.status_code == 200
    items = resp.json()["items"]

    comic_item = next((item for item in items if item["path"] == "/comic.zip"), None)
    assert comic_item is not None
    assert isinstance(comic_item.get("thumbnail"), str)
    assert comic_item["thumbnail"].startswith("/api/comic/cover?")
    assert "max_width=420" in comic_item["thumbnail"]


def test_files_raw_media(client: TestClient):
    resp = client.get("/api/files/raw", params={"path": "/song.mp3"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/")
    assert len(resp.content) > 0


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


def test_comic_cb7_metadata_and_page(client: TestClient):
    metadata = client.get("/api/comic/metadata", params={"path": "/comic.cb7"})
    assert metadata.status_code == 200
    assert metadata.json()["page_count"] == 2
    assert metadata.json()["format"] == "7z"

    page = client.get("/api/comic/page", params={"path": "/comic.cb7", "page": 1})
    assert page.status_code == 200
    assert page.content == b"fake-7z-jpeg-1"


def test_comic_cbt_metadata_and_page(client: TestClient):
    metadata = client.get("/api/comic/metadata", params={"path": "/comic.cbt"})
    assert metadata.status_code == 200
    assert metadata.json()["page_count"] == 2
    assert metadata.json()["format"] == "tar"

    page = client.get("/api/comic/page", params={"path": "/comic.cbt", "page": 1})
    assert page.status_code == 200
    assert page.content == b"fake-7z-jpeg-1"


def test_comic_mislabeled_zip_fallback_to_7z(client: TestClient):
    metadata = client.get("/api/comic/metadata", params={"path": "/comic_7z_named_zip.zip"})
    assert metadata.status_code == 200
    payload = metadata.json()
    assert payload["page_count"] == 2
    assert payload["format"] == "7z"

    page = client.get("/api/comic/page", params={"path": "/comic_7z_named_zip.zip", "page": 1})
    assert page.status_code == 200
    assert page.content == b"fake-7z-jpeg-1"


def test_comic_broken_zip_returns_415_instead_of_500(client: TestClient):
    metadata = client.get("/api/comic/metadata", params={"path": "/comic_broken.zip"})
    assert metadata.status_code == 415
    assert "压缩包" in metadata.json()["detail"]

    page = client.get("/api/comic/page", params={"path": "/comic_broken.zip", "page": 1})
    assert page.status_code == 415
    assert "压缩包" in page.json()["detail"]


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


def test_comic_cover_cached_and_etag(client: TestClient):
    params = {
        "path": "/comic_valid.zip",
        "max_width": 420,
        "quality": 72,
        "format": "webp",
    }
    first = client.get("/api/comic/cover", params=params)
    assert first.status_code == 200
    assert first.headers["etag"]
    assert first.headers["cache-control"] == "public, max-age=604800"
    assert first.headers["content-type"].startswith("image/")
    assert len(first.content) > 0

    cached = client.get(
        "/api/comic/cover",
        params=params,
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert cached.status_code == 304


def test_settings_get_returns_defaults(client: TestClient):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["media_root_directory"]
    assert payload["ui"]["home_hidden_roots"] == ["CM", "JMV"]
    assert payload["ui"]["default_layout"] in {"grid", "list"}
    assert "movies" in payload["available_filter_categories"]


def test_settings_patch_ui_updates(client: TestClient):
    resp = client.patch(
        "/api/settings",
        json={
            "ui": {
                "home_hidden_roots": ["CM", "JMV", "TestRoot"],
                "recent_hidden_categories": ["comics", "archives"],
                "default_layout": "list",
                "player_autoplay_default": False,
                "group_tv_by_default": False,
                "home_recent_limit": 10,
                "category_page_limit": 120,
            }
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    ui = payload["ui"]
    assert ui["home_hidden_roots"] == ["CM", "JMV", "TestRoot"]
    assert ui["recent_hidden_categories"] == ["comics", "archives"]
    assert ui["default_layout"] == "list"
    assert ui["player_autoplay_default"] is False
    assert ui["group_tv_by_default"] is False
    assert ui["home_recent_limit"] == 10
    assert ui["category_page_limit"] == 120


def test_settings_patch_media_root_directory(client: TestClient, tmp_path: Path):
    new_root = tmp_path / "new_media_root"
    assert not new_root.exists()

    resp = client.patch(
        "/api/settings",
        json={
            "media_root_directory": str(new_root),
            "create_media_root_if_missing": True,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert Path(payload["media_root_directory"]).resolve() == new_root.resolve()
    assert new_root.exists() and new_root.is_dir()

    invalid = client.patch(
        "/api/settings",
        json={
            "media_root_directory": str(tmp_path / "missing_root"),
            "create_media_root_if_missing": False,
        },
    )
    assert invalid.status_code == 400

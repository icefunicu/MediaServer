"""
Core unit tests for filesystem and range parsing helpers.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.comic_reader import natural_sort_key
from backend.services.filesystem import (
    SecurityError,
    generate_file_id,
    get_file_info,
    list_directory,
    search_files,
    validate_path,
)
from backend.services.range_parser import (
    RangeParseError,
    build_content_range,
    build_range_response_headers,
    parse_range_header,
)
from backend.services.video_stream import ensure_compatible_mp4


class TestPathValidation:
    def test_normal_path(self):
        path = validate_path("/")
        from backend.config import get_config

        root = get_config().media.root_directory
        expected = os.path.basename(os.path.normpath(root))
        assert path.endswith(expected)

    def test_path_traversal_blocked(self):
        with pytest.raises(SecurityError):
            validate_path("../../../etc/passwd")

    def test_parent_directory_blocked(self):
        with pytest.raises(SecurityError):
            validate_path("test/../config.yaml")

    def test_filename_with_ellipsis_allowed(self):
        path = validate_path("/JMV/sample...video.ts")
        assert path.endswith("sample...video.ts")

    def test_system_directory_blocked(self):
        with pytest.raises(SecurityError):
            validate_path("/etc/passwd")


class TestRangeParser:
    def test_range_start_end(self):
        start, end = parse_range_header("bytes=0-1023", 2048)
        assert start == 0
        assert end == 1023

    def test_range_start_only(self):
        start, end = parse_range_header("bytes=1024-", 2048)
        assert start == 1024
        assert end == 2047

    def test_range_suffix_only(self):
        start, end = parse_range_header("bytes=-1024", 2048)
        assert start == 1024
        assert end == 2047

    def test_invalid_format(self):
        with pytest.raises(RangeParseError):
            parse_range_header("invalid", 2048)

    def test_range_exceeds_file(self):
        start, end = parse_range_header("bytes=0-3000", 2048)
        assert end == 2047

    def test_build_content_range(self):
        result = build_content_range(0, 1023, 2048)
        assert result == "bytes 0-1023/2048"

    def test_build_range_response_headers(self):
        headers = build_range_response_headers(0, 1023, 2048, 1024)
        assert headers["Content-Range"] == "bytes 0-1023/2048"
        assert headers["Accept-Ranges"] == "bytes"
        assert headers["Content-Length"] == "1024"


class TestNaturalSort:
    def test_natural_sort(self):
        files = ["page10.jpg", "page2.jpg", "page1.jpg", "page20.jpg"]
        sorted_files = sorted(files, key=natural_sort_key)
        assert sorted_files == ["page1.jpg", "page2.jpg", "page10.jpg", "page20.jpg"]


class TestFileSystem:
    def test_generate_file_id(self):
        file_id_1 = generate_file_id("/test/path")
        file_id_2 = generate_file_id("/test/path")
        assert file_id_1 == file_id_2

    def test_get_file_info(self):
        info = get_file_info("config/config.yaml")
        assert info.name == "config.yaml"
        assert info.size > 0

    def test_list_directory_returns_list(self):
        entries = list_directory("/")
        assert isinstance(entries, list)

    def test_search_files_returns_list(self):
        entries = search_files("config")
        assert isinstance(entries, list)


class TestCompatibleTranscoding:
    def test_ensure_compatible_mp4_remux_explicit_mp4_format(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        import backend.services.video_stream as video_stream

        input_path = tmp_path / "sample.ts"
        input_path.write_bytes(b"sample-data")
        output_path = tmp_path / "cache" / "sample.mp4"
        commands: list[list[str]] = []

        monkeypatch.setattr(video_stream, "validate_path", lambda p: str(Path(p)))
        monkeypatch.setattr(
            video_stream,
            "get_transcoded_cache_path",
            lambda _file_id, _target: str(output_path),
        )
        monkeypatch.setattr(video_stream.shutil, "which", lambda _bin: "ffmpeg")
        monkeypatch.setattr(video_stream, "_can_fast_remux_to_compatible_mp4", lambda _path: True)
        monkeypatch.setattr(video_stream, "_is_browser_compatible_mp4", lambda _path: True)

        def fake_run(cmd, **_kwargs):
            commands.append(cmd)
            Path(cmd[-1]).write_bytes(b"mp4-cache")

        monkeypatch.setattr(video_stream.subprocess, "run", fake_run)

        cache_path = ensure_compatible_mp4(str(input_path), "id-1")

        assert cache_path == str(output_path)
        assert output_path.exists()
        assert commands
        assert "-f" in commands[0]
        fmt_index = commands[0].index("-f")
        assert commands[0][fmt_index + 1] == "mp4"

    def test_ensure_compatible_mp4_reencode_explicit_mp4_format(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        import backend.services.video_stream as video_stream

        input_path = tmp_path / "sample.ts"
        input_path.write_bytes(b"sample-data")
        output_path = tmp_path / "cache" / "sample.mp4"
        commands: list[list[str]] = []

        monkeypatch.setattr(video_stream, "validate_path", lambda p: str(Path(p)))
        monkeypatch.setattr(
            video_stream,
            "get_transcoded_cache_path",
            lambda _file_id, _target: str(output_path),
        )
        monkeypatch.setattr(video_stream.shutil, "which", lambda _bin: "ffmpeg")
        monkeypatch.setattr(video_stream, "_can_fast_remux_to_compatible_mp4", lambda _path: True)
        monkeypatch.setattr(video_stream, "_is_browser_compatible_mp4", lambda _path: True)

        def fake_run(cmd, **_kwargs):
            commands.append(cmd)
            if len(commands) == 1:
                raise subprocess.CalledProcessError(returncode=1, cmd=cmd)
            Path(cmd[-1]).write_bytes(b"mp4-cache")

        monkeypatch.setattr(video_stream.subprocess, "run", fake_run)

        cache_path = ensure_compatible_mp4(str(input_path), "id-2")

        assert cache_path == str(output_path)
        assert output_path.exists()
        assert len(commands) == 2
        assert "-f" in commands[1]
        fmt_index = commands[1].index("-f")
        assert commands[1][fmt_index + 1] == "mp4"

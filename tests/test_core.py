"""
Core unit tests for filesystem and range parsing helpers.
"""

import os
import sys

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


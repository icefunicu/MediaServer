"""
Media library aggregation service.

Builds category-oriented views for the frontend dashboard.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from backend.config import get_config
from backend.logging_config import get_logger
from backend.services.filesystem import FileEntry, list_directory
from backend.services.library_snapshot import load_snapshot, save_snapshot

logger = get_logger("media.library")

LibraryCategory = Literal[
    "all",
    "movies",
    "tv",
    "anime",
    "jdrama",
    "music",
    "photos",
    "comics",
    "archives",
    "others",
    "recent",
]

SUPPORTED_CATEGORIES: tuple[LibraryCategory, ...] = (
    "all",
    "movies",
    "tv",
    "anime",
    "jdrama",
    "music",
    "photos",
    "comics",
    "archives",
    "others",
    "recent",
)

_SCAN_CACHE_TTL_SECONDS = 15
_PERSISTED_SNAPSHOT_MAX_AGE_SECONDS = 3600
_scan_cache_lock = threading.Lock()
_scan_cache_updated_at = 0.0
_scan_cache_items: list[dict[str, Any]] = []

_TV_PATTERNS = (
    re.compile(r"(?i)\bs\d{1,2}e\d{1,3}\b"),
    re.compile(r"(?i)\b\d{1,2}\s*x\s*\d{1,3}\b"),
    re.compile(r"(?i)\bseason\s*\d+\b"),
    re.compile(r"(?i)\bs\d{2}\b"),
    re.compile(r"(?i)\bsp\s*\d{1,3}\b"),
    re.compile(r"第\s*[0-9一二三四五六七八九十]+\s*[季集话話]"),
    re.compile(r"全\s*\d+\s*集"),
)

_TV_KEYWORDS = (
    "电视剧",
    "剧集",
    "番剧",
    "日剧",
    "韩剧",
    "美剧",
    "特别篇",
    "特别盘",
    "ova",
)

_SEASON_PATTERNS = (
    re.compile(r"(?i)\bs(?P<season>\d{1,2})\b"),
    re.compile(r"(?i)\bseason\s*(?P<season>\d{1,2})\b"),
    re.compile(r"第\s*(?P<season>\d{1,2})\s*季"),
    re.compile(r"第\s*(?P<season_cn>[一二三四五六七八九十]{1,3})\s*季"),
)

_EPISODE_PATTERNS = (
    re.compile(r"(?i)\bs(?P<season>\d{1,2})e(?P<episode>\d{1,3})\b"),
    re.compile(r"(?i)\b(?P<season>\d{1,2})\s*x\s*(?P<episode>\d{1,3})\b"),
    re.compile(r"(?i)\bsp\s*(?P<episode>\d{1,3})\b"),
    re.compile(r"第\s*(?P<episode>\d{1,4})\s*部"),
    re.compile(r"第\s*(?P<episode>\d{1,4})\s*[集话話]"),
    re.compile(r"(?i)\be(?P<episode>\d{1,3})\b"),
)

_SERIES_CLEANUP_PATTERNS = (
    re.compile(r"\[[^\]]+\]"),
    re.compile(r"\([^)]+\)"),
    re.compile(r"（[^）]+）"),
    re.compile(r"【[^】]+】"),
    re.compile(r"(?i)\b(?:4k|1080p|2160p|x264|x265|hevc|flac|aac)\b"),
    re.compile(r"全\s*\d+\s*[季集话話部篇].*$"),
    re.compile(r"第\s*\d+\s*季.*$"),
    re.compile(r"(?i)\bseason\s*\d+.*$"),
    re.compile(r"(?i)\bs\d{1,2}\b"),
    re.compile(r"收藏版"),
)

_ALLOWED_SORTS = {"recent", "name", "size"}

_CHINESE_NUMBERS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def invalidate_media_library_cache() -> None:
    """Clear in-memory scan cache, forcing next request to rescan or load snapshot."""
    global _scan_cache_items
    global _scan_cache_updated_at
    with _scan_cache_lock:
        _scan_cache_items = []
        _scan_cache_updated_at = 0.0


def _to_virtual_path(absolute_path: str) -> str:
    root_dir = Path(get_config().media.root_directory).resolve()
    resolved = Path(absolute_path).resolve()
    try:
        relative_path = resolved.relative_to(root_dir)
        relative_text = relative_path.as_posix()
        return "/" if relative_text in {"", "."} else f"/{relative_text}"
    except ValueError:
        return f"/{resolved.as_posix().lstrip('/')}"


def _extract_root_folder(virtual_path: str) -> str:
    parts = Path(virtual_path.lstrip("/")).parts
    return parts[0] if parts else ""


def _normalize_root_folder(root_folder: str) -> str:
    normalized = root_folder.strip()
    lowered = normalized.casefold()
    if "蜡笔小新" in normalized:
        return "蜡笔小新"
    if "齐木楠雄" in normalized:
        return "齐木楠雄的灾难"
    if lowered == "jmv":
        return "JMV"
    if lowered == "cm":
        return "CM"
    return normalized


def _infer_genre(entry: FileEntry, root_folder: str) -> str | None:
    normalized_root = _normalize_root_folder(root_folder)
    if normalized_root == "JMV":
        return "jdrama"
    if normalized_root in {"蜡笔小新", "齐木楠雄的灾难"}:
        return "anime"
    if normalized_root == "CM" and entry.type in {"comic", "archive"}:
        return "anime_comic"
    return None


def _tail_context(entry: FileEntry) -> str:
    path_parts = Path(entry.path).parts
    tail_parts = path_parts[-4:] if path_parts else [entry.name]
    return " ".join(tail_parts)


def _guess_video_category(entry: FileEntry, root_folder: str) -> LibraryCategory:
    normalized_root = _normalize_root_folder(root_folder)
    if normalized_root in {"JMV", "蜡笔小新", "齐木楠雄的灾难"}:
        return "tv"

    context = _tail_context(entry)
    normalized = context.casefold()
    if any(pattern.search(context) for pattern in _TV_PATTERNS):
        return "tv"
    if any(keyword in normalized for keyword in _TV_KEYWORDS):
        return "tv"
    return "movies"


def _map_to_category(entry: FileEntry, root_folder: str) -> LibraryCategory:
    normalized_root = _normalize_root_folder(root_folder)

    if entry.type == "video":
        return _guess_video_category(entry, root_folder=root_folder)
    if entry.type == "music":
        return "music"
    if entry.type == "photo":
        return "photos"
    if normalized_root == "CM" and entry.type in {"comic", "archive"}:
        return "comics"
    if entry.type == "comic":
        return "comics"
    if entry.type == "archive":
        return "archives"
    return "others"


def _build_urls(file_type: str, virtual_path: str, category: str) -> tuple[str | None, str | None]:
    encoded_path = quote(virtual_path, safe="/")
    if file_type == "video":
        return (
            f"/api/video/thumbnail?path={encoded_path}",
            f"/api/video/stream?path={encoded_path}",
        )
    if file_type == "photo":
        return (
            f"/api/files/raw?path={encoded_path}",
            f"/api/files/raw?path={encoded_path}",
        )
    if file_type == "music":
        return (None, f"/api/files/raw?path={encoded_path}")
    if file_type == "comic" or (file_type == "archive" and category == "comics"):
        # Render a lightweight first-page cover on comic cards.
        thumbnail = f"/api/comic/cover?path={encoded_path}&max_width=420&quality=72&format=webp"
        return (thumbnail, None)
    return (None, None)


def _scan_media_items() -> list[dict[str, Any]]:
    entries = list_directory("/", recursive=True)
    items: list[dict[str, Any]] = []

    for entry in entries:
        if entry.is_directory:
            continue

        virtual_path = _to_virtual_path(entry.path)
        root_folder = _extract_root_folder(virtual_path)
        category = _map_to_category(entry, root_folder=root_folder)
        genre = _infer_genre(entry, root_folder=root_folder)
        thumbnail_url, stream_url = _build_urls(entry.type, virtual_path, category=category)

        items.append(
            {
                "id": entry.id,
                "name": entry.name,
                "path": virtual_path,
                "size": entry.size,
                "type": entry.type,
                "category": category,
                "genre": genre,
                "root_folder": _normalize_root_folder(root_folder),
                "extension": entry.extension,
                "modified_time": entry.modified_time,
                "thumbnail": thumbnail_url,
                "stream_url": stream_url,
            }
        )

    items.sort(key=lambda item: item["modified_time"], reverse=True)
    return items


def _get_scanned_items(force_refresh: bool = False) -> list[dict[str, Any]]:
    now = time.time()
    root_dir = str(Path(get_config().media.root_directory).resolve())
    global _scan_cache_updated_at
    global _scan_cache_items

    with _scan_cache_lock:
        is_cache_valid = (
            not force_refresh
            and _scan_cache_items
            and now - _scan_cache_updated_at <= _SCAN_CACHE_TTL_SECONDS
        )
        if is_cache_valid:
            return [item.copy() for item in _scan_cache_items]

        if not force_refresh:
            persisted_items = load_snapshot(
                root_dir=root_dir,
                max_age_seconds=_PERSISTED_SNAPSHOT_MAX_AGE_SECONDS,
            )
            if persisted_items:
                _scan_cache_items = persisted_items
                _scan_cache_updated_at = now
                return [item.copy() for item in _scan_cache_items]

    scanned_items = _scan_media_items()
    with _scan_cache_lock:
        _scan_cache_items = scanned_items
        _scan_cache_updated_at = time.time()

    try:
        save_snapshot(root_dir=root_dir, items=scanned_items)
    except Exception as exc:
        logger.warning(f"Failed to persist media library snapshot: {exc}")

    return [item.copy() for item in scanned_items]


def _apply_query_filter(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    keyword = query.casefold()
    return [
        item
        for item in items
        if keyword in item["name"].casefold() or keyword in item["path"].casefold()
    ]


def _sort_items(items: list[dict[str, Any]], sort_by: str) -> None:
    if sort_by == "name":
        items.sort(key=lambda item: item["name"].casefold())
        return
    if sort_by == "size":
        items.sort(key=lambda item: item["size"], reverse=True)
        return
    items.sort(key=lambda item: item["modified_time"], reverse=True)


def _select_featured(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for category in ("movies", "tv", "music", "photos", "comics", "archives", "others"):
        candidate = next((item for item in items if item["category"] == category), None)
        if candidate is not None:
            return candidate.copy()
    return None


def _parse_chinese_number(raw: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    if text in _CHINESE_NUMBERS:
        return _CHINESE_NUMBERS[text]
    if "十" not in text:
        return None

    left, right = text.split("十", 1)
    tens = 1 if left == "" else _CHINESE_NUMBERS.get(left)
    if tens is None:
        return None
    ones = 0 if right == "" else _CHINESE_NUMBERS.get(right)
    if ones is None:
        return None
    return tens * 10 + ones


def _normalize_series_title(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""

    quoted = re.search(r"《([^》]+)》", text)
    if quoted:
        text = quoted.group(1)

    for pattern in _SERIES_CLEANUP_PATTERNS:
        text = pattern.sub(" ", text)

    text = re.sub(r"[._-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -_.")


def _contains_season_marker(segment: str) -> bool:
    if any(pattern.search(segment) for pattern in _SEASON_PATTERNS):
        return True
    lowered = segment.casefold()
    return any(token in lowered for token in ("season", "第", "季", "全集"))


def _extract_season(parts: list[str], stem: str) -> int | None:
    for source in list(parts) + [stem]:
        for pattern in _SEASON_PATTERNS:
            match = pattern.search(source)
            if not match:
                continue
            season_text = match.groupdict().get("season")
            if season_text:
                return int(season_text)
            season_cn = match.groupdict().get("season_cn")
            if season_cn:
                parsed = _parse_chinese_number(season_cn)
                if parsed is not None:
                    return parsed
    return None


def _extract_episode(stem: str, context: str) -> tuple[int | None, int | None]:
    season_from_pair: int | None = None
    episode: int | None = None

    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(context)
        if not match:
            continue
        season_text = match.groupdict().get("season")
        if season_text:
            season_from_pair = int(season_text)
        episode_text = match.groupdict().get("episode")
        if episode_text:
            episode = int(episode_text)
            break

    if episode is None:
        match = re.search(r"(?:季|season|s\d{1,2})\D{0,8}(?P<episode>\d{1,4})", stem, re.IGNORECASE)
        if match:
            episode = int(match.group("episode"))

    if episode is None:
        pure_number = re.match(r"^0*(?P<episode>\d{1,4})$", stem.strip())
        if pure_number:
            episode = int(pure_number.group("episode"))

    if episode is None:
        prefixed = re.match(r"^0*(?P<episode>\d{1,4})(?:\D|$)", stem.strip())
        if prefixed:
            episode = int(prefixed.group("episode"))

    return season_from_pair, episode


def _derive_series_title(relative_path: Path) -> str:
    directories = list(relative_path.parts[:-1])
    stem_fallback = _normalize_series_title(relative_path.stem)
    if not directories:
        return stem_fallback

    # Drop the root folder segment so `/JMV/剧名/01.mkv` resolves to `剧名`.
    title_segments = directories[1:] if len(directories) > 1 else directories

    marker_index = next(
        (idx for idx, segment in enumerate(title_segments) if _contains_season_marker(segment)),
        -1,
    )
    if marker_index > 0:
        normalized = _normalize_series_title(title_segments[marker_index - 1])
        if normalized:
            return normalized

    if len(title_segments) >= 2:
        normalized = _normalize_series_title(title_segments[-2])
        if normalized:
            return normalized

    if title_segments:
        normalized = _normalize_series_title(title_segments[-1])
        if normalized:
            return normalized

    for segment in title_segments:
        normalized = _normalize_series_title(segment)
        if normalized:
            return normalized

    return stem_fallback


def _pick_series_title(item: dict[str, Any], relative_path: Path) -> str:
    normalized_root = _normalize_root_folder(str(item.get("root_folder") or ""))
    if normalized_root in {"蜡笔小新", "齐木楠雄的灾难"}:
        return normalized_root

    derived = _derive_series_title(relative_path)
    if derived:
        return derived

    if normalized_root and normalized_root not in {"JMV", "CM"}:
        return normalized_root

    return ""


def _resolve_section(
    relative_path: Path,
    season_no: int | None,
    episode_no: int | None,
) -> dict[str, Any]:
    context_text = relative_path.as_posix()
    path_parts = list(relative_path.parts)
    analyzed_parts = path_parts[1:] if len(path_parts) > 1 else path_parts
    analyzed_text = "/".join(analyzed_parts) if analyzed_parts else context_text
    lowered = analyzed_text.casefold()

    if any(token in analyzed_text for token in ("剧场版", "劇場版")) or "movie" in lowered:
        if episode_no is None:
            movie_match = re.search(r"第\s*(\d{1,4})\s*部", analyzed_text)
            if movie_match:
                episode_no = int(movie_match.group(1))
        return {
            "id": "movies",
            "title": "剧场版",
            "kind": "movies",
            "order": 2_000,
            "episode_no": episode_no,
        }

    if (
        "特别篇" in analyzed_text
        or "特別篇" in analyzed_text
        or "特别盘" in analyzed_text
        or "ova" in lowered
        or re.search(r"(?i)\bsp\s*\d{1,3}\b", analyzed_text)
    ):
        if episode_no is None:
            sp_match = re.search(r"(?i)\bsp\s*(\d{1,3})\b", analyzed_text)
            if sp_match:
                episode_no = int(sp_match.group(1))
        return {
            "id": "specials",
            "title": "特别篇",
            "kind": "specials",
            "order": 2_100,
            "episode_no": episode_no,
        }

    if season_no is not None:
        return {
            "id": f"season-{season_no:02d}",
            "title": f"第 {season_no} 季",
            "kind": "season",
            "order": season_no,
            "episode_no": episode_no,
        }

    tail_folder = relative_path.parts[-2] if len(relative_path.parts) >= 2 else "未分组"
    section_title = _normalize_series_title(tail_folder) or "未分组"
    return {
        "id": f"section-{hashlib.md5(section_title.encode('utf-8')).hexdigest()[:10]}",
        "title": section_title,
        "kind": "section",
        "order": 1_000,
        "episode_no": episode_no,
    }


def _build_episode_label(season_no: int | None, episode_no: int | None) -> str | None:
    if episode_no is None:
        return None
    if season_no is None:
        return f"EP{episode_no:03d}"
    return f"S{season_no:02d}E{episode_no:03d}"


def _group_tv_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []

    for original in items:
        item = original.copy()
        if item.get("category") != "tv" or item.get("type") != "video":
            passthrough.append(item)
            continue

        # J-drama content (typically from JMV) should stay as direct file list,
        # instead of being folded into series cards.
        if item.get("genre") == "jdrama" or _normalize_root_folder(str(item.get("root_folder") or "")) == "JMV":
            passthrough.append(item)
            continue

        relative_path = Path(str(item.get("path", "/")).lstrip("/"))
        if relative_path == Path("."):
            passthrough.append(item)
            continue

        season_no = _extract_season(list(relative_path.parts[:-1]), relative_path.stem)
        season_from_pair, episode_no = _extract_episode(relative_path.stem, relative_path.as_posix())
        if season_no is None and season_from_pair is not None:
            season_no = season_from_pair

        series_title = _pick_series_title(item, relative_path)
        if not series_title:
            passthrough.append(item)
            continue

        section = _resolve_section(relative_path, season_no=season_no, episode_no=episode_no)
        resolved_episode_no = section.get("episode_no")

        item["season_no"] = season_no
        item["episode_no"] = resolved_episode_no
        item["episode_label"] = _build_episode_label(season_no, resolved_episode_no)
        item["section_id"] = section["id"]
        item["section_title"] = section["title"]
        item["section_kind"] = section["kind"]
        item["section_order"] = section["order"]

        group_key = f"{series_title.casefold()}::{item.get('genre') or ''}"
        bucket = grouped.setdefault(
            group_key,
            {
                "title": series_title,
                "episodes": [],
                "genre": item.get("genre"),
                "root_folder": item.get("root_folder"),
            },
        )
        bucket["episodes"].append(item)

    aggregated: list[dict[str, Any]] = []
    for group_key, payload in grouped.items():
        episodes = payload["episodes"]
        episodes.sort(
            key=lambda entry: (
                entry.get("section_order") or 0,
                entry.get("season_no") or 0,
                entry.get("episode_no") if entry.get("episode_no") is not None else 10_000,
                entry.get("name", "").casefold(),
            )
        )

        if len(episodes) < 2:
            passthrough.extend(episodes)
            continue

        section_map: dict[str, dict[str, Any]] = {}
        for episode in episodes:
            section_id = str(episode.get("section_id") or "section-unknown")
            section_payload = section_map.setdefault(
                section_id,
                {
                    "id": section_id,
                    "title": str(episode.get("section_title") or "未分组"),
                    "kind": str(episode.get("section_kind") or "section"),
                    "order": int(episode.get("section_order") or 0),
                    "episodes": [],
                },
            )
            section_payload["episodes"].append(episode)

        ordered_sections = sorted(section_map.values(), key=lambda value: (value["order"], value["title"].casefold()))

        flat_episodes: list[dict[str, Any]] = []
        section_items: list[dict[str, Any]] = []
        for section in ordered_sections:
            section_episodes = section["episodes"]
            section_episodes.sort(
                key=lambda entry: (
                    entry.get("episode_no") if entry.get("episode_no") is not None else 10_000,
                    entry.get("name", "").casefold(),
                )
            )

            compact_episodes: list[dict[str, Any]] = []
            for section_index, episode in enumerate(section_episodes, start=1):
                copied = episode.copy()
                copied["section_index"] = section_index
                compact_episodes.append(copied)
                flat_episodes.append(copied)

            section_items.append(
                {
                    "id": section["id"],
                    "title": section["title"],
                    "kind": section["kind"],
                    "order": section["order"],
                    "episode_count": len(compact_episodes),
                    "episodes": compact_episodes,
                }
            )

        for play_index, episode in enumerate(flat_episodes, start=1):
            episode["play_index"] = play_index

        latest_modified = max(entry["modified_time"] for entry in flat_episodes)
        total_size = sum(entry["size"] for entry in flat_episodes)
        thumbnail = next((entry.get("thumbnail") for entry in flat_episodes if entry.get("thumbnail")), None)
        stream_url = next((entry.get("stream_url") for entry in flat_episodes if entry.get("stream_url")), None)
        season_count = sum(1 for section in section_items if section.get("kind") == "season")

        aggregated.append(
            {
                "id": hashlib.md5(f"series:{group_key}".encode("utf-8")).hexdigest(),
                "name": payload["title"],
                "path": f"/@series/{quote(group_key, safe='')}",
                "size": total_size,
                "type": "tv_series",
                "category": "tv",
                "genre": payload.get("genre"),
                "root_folder": payload.get("root_folder"),
                "extension": "",
                "modified_time": latest_modified,
                "thumbnail": thumbnail,
                "stream_url": stream_url,
                "is_group": True,
                "episode_count": len(flat_episodes),
                "season_count": season_count,
                "sections": section_items,
                "episodes": flat_episodes,
                "autoplay_supported": True,
            }
        )

    merged = passthrough + aggregated
    merged.sort(key=lambda item: item["modified_time"], reverse=True)
    return merged


def _prepare_display_items(items: list[dict[str, Any]], group_tv: bool) -> list[dict[str, Any]]:
    if not group_tv:
        return [item.copy() for item in items]
    return _group_tv_items(items)


def list_library_items(
    category: str = "all",
    query: str = "",
    sort_by: str = "recent",
    limit: int = 120,
    offset: int = 0,
    force_refresh: bool = False,
    group_tv: bool = True,
) -> dict[str, Any]:
    if category not in SUPPORTED_CATEGORIES:
        raise ValueError(f"Unsupported category: {category}")
    if sort_by not in _ALLOWED_SORTS:
        raise ValueError(f"Unsupported sort: {sort_by}")

    items = _get_scanned_items(force_refresh=force_refresh)
    normalized_query = (query or "").strip()

    if category == "recent":
        filtered = items
    elif category == "anime":
        filtered = [
            item
            for item in items
            if item["category"] == "tv" and item.get("genre") == "anime"
        ]
    elif category == "jdrama":
        filtered = [
            item
            for item in items
            if item["category"] == "tv" and item.get("genre") == "jdrama"
        ]
    elif category != "all":
        filtered = [item for item in items if item["category"] == category]
    else:
        filtered = items

    if normalized_query:
        filtered = _apply_query_filter(filtered, normalized_query)

    filtered = _prepare_display_items(filtered, group_tv=group_tv)
    _sort_items(filtered, sort_by)

    total = len(filtered)
    paged_items = filtered[offset: offset + limit]

    return {
        "category": category,
        "query": normalized_query,
        "sort": sort_by,
        "total": total,
        "items": paged_items,
    }


def get_library_overview(
    recent_limit: int = 12,
    force_refresh: bool = False,
    group_tv: bool = True,
) -> dict[str, Any]:
    raw_items = _get_scanned_items(force_refresh=force_refresh)
    display_items = _prepare_display_items(raw_items, group_tv=group_tv)

    limited_recent = max(1, min(60, int(recent_limit)))
    display_items.sort(key=lambda item: item["modified_time"], reverse=True)
    recent_items = display_items[:limited_recent]

    counts: dict[str, int] = {
        "movies": 0,
        "tv": 0,
        "music": 0,
        "photos": 0,
        "comics": 0,
        "archives": 0,
        "others": 0,
    }
    for item in display_items:
        category = item.get("category")
        if category in counts:
            counts[category] += 1

    total_size = sum(item["size"] for item in raw_items)
    root_dir = Path(get_config().media.root_directory).resolve()
    try:
        disk_usage = shutil.disk_usage(root_dir)
        storage_total_bytes = disk_usage.total
    except OSError as exc:
        logger.warning(f"Failed to read disk usage for {root_dir}: {exc}")
        storage_total_bytes = 0

    return {
        "total_items": len(display_items),
        "counts": counts,
        "storage_used_bytes": total_size,
        "storage_total_bytes": storage_total_bytes,
        "recent_items": [item.copy() for item in recent_items],
        "featured_item": _select_featured(display_items),
        "generated_at": int(time.time()),
    }

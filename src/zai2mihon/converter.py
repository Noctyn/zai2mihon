"""Data transformation logic from ZaiManhua API payloads to Mihon backup objects."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Union

from zai2mihon.models import (
    DEFAULT_ZAIMANHUA_SOURCE_ID,
    DEFAULT_ZAIMANHUA_SOURCE_NAME,
    MihonBackup,
    MihonCategory,
    MihonChapter,
    MihonHistory,
    MihonManga,
    MihonSource,
)
from zai2mihon.parser import (
    normalize_chapter_url,
    normalize_comic_url,
    repair_mojibake,
)

logger = logging.getLogger(__name__)


def parse_datetime_to_ms(dt_val: Any) -> int:
    """Parse various datetime representations into milliseconds timestamp."""
    if not dt_val:
        return int(time.time() * 1000)

    if isinstance(dt_val, (int, float)):
        if dt_val < 100_000_000_000:
            return int(dt_val * 1000)
        return int(dt_val)

    if isinstance(dt_val, str):
        val_str = dt_val.strip()
        if val_str.isdigit():
            num = int(val_str)
            if num < 100_000_000_000:
                return num * 1000
            return num

        for fmt in (
            "%Y-%m-%d %H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(val_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1000)
            except ValueError:
                continue

    return int(time.time() * 1000)


def normalize_status(status_val: Any) -> int:
    """Map status to Mihon status int (1=ONGOING, 2=COMPLETED)."""
    if status_val is None:
        return 1

    if isinstance(status_val, (int, float)):
        s_int = int(status_val)
        if s_int in (1, 2):
            return s_int
        return 1

    if isinstance(status_val, str):
        s_lower = status_val.lower()
        if "完结" in s_lower or "completed" in s_lower or "end" in s_lower:
            return 2
        if "连载" in s_lower or "ongoing" in s_lower:
            return 1

    return 1


def create_chapter_and_history(
    comic_id: Any,
    chapter_id: Any,
    chapter_name: Optional[str] = None,
    viewing_time_ms: Optional[int] = None,
) -> tuple[Optional[MihonChapter], Optional[MihonHistory]]:
    """Construct MihonChapter and MihonHistory objects for a given chapter."""
    if not comic_id or not chapter_id:
        return None, None

    chapter_url = normalize_chapter_url(comic_id, chapter_id)
    ch_name = repair_mojibake(chapter_name) or "阅读历史"
    time_ms = viewing_time_ms or int(time.time() * 1000)

    ch_num = 0.0
    num_match = re.search(r"(\d+(\.\d+)?)", ch_name)
    if num_match:
        try:
            ch_num = float(num_match.group(1))
        except Exception:
            ch_num = 0.0

    chapter = MihonChapter(
        url=chapter_url,
        name=ch_name,
        read=True,
        last_page_read=1,
        date_fetch=time_ms,
        date_upload=time_ms,
        chapter_number=ch_num,
        source_order=0,
        memo=[b"{}"],
    )

    history = MihonHistory(
        url=chapter_url,
        last_read=time_ms,
        read_duration=0,
    )

    return chapter, history


def sub_item_to_mihon_manga(
    item: Dict[str, Any],
    source_id: int = DEFAULT_ZAIMANHUA_SOURCE_ID,
    category_ids: Optional[List[int]] = None,
    is_favorite: bool = True,
) -> MihonManga:
    """Convert a ZaiManhua subscription or history payload dictionary to a MihonManga object."""
    comic_id = item.get("id") or item.get("biz_id") or item.get("comic_id")
    url = normalize_comic_url(comic_id)

    title = repair_mojibake(item.get("title") or item.get("name") or "Unknown Comic")
    thumbnail_url = item.get("cover") or item.get("thumbnail_url") or ""
    status = normalize_status(item.get("status"))

    date_added_raw = item.get("last_updatetime") or item.get("viewing_time") or item.get("listTime")
    date_added = parse_datetime_to_ms(date_added_raw)

    categories = (category_ids or []) if is_favorite else []

    manga = MihonManga(
        source=source_id,
        url=url,
        title=title,
        status=status,
        thumbnail_url=thumbnail_url,
        date_added=date_added,
        viewer_flags=0,
        chapter_flags=513,
        update_strategy=0,
        favorite=is_favorite,
        initialized=True,
        categories=categories,
        chapters=[],
        history=[],
        memo=[b"{}"],
    )

    # Check for readingRecord in subscription payload or direct fields in history payload
    rec = item.get("readingRecord")
    if isinstance(rec, dict) and rec.get("chapter_id"):
        ch_id = rec.get("chapter_id")
        ch_name = rec.get("chapter_name")
        view_time = parse_datetime_to_ms(rec.get("viewing_time"))
        ch, hist = create_chapter_and_history(
            comic_id=comic_id,
            chapter_id=ch_id,
            chapter_name=ch_name,
            viewing_time_ms=view_time,
        )
        if ch:
            manga.chapters.append(ch)
        if hist:
            manga.history.append(hist)
    elif item.get("chapter_id"):
        ch_id = item.get("chapter_id")
        ch_name = item.get("chapter_name")
        view_time = parse_datetime_to_ms(item.get("viewing_time"))
        ch, hist = create_chapter_and_history(
            comic_id=comic_id,
            chapter_id=ch_id,
            chapter_name=ch_name,
            viewing_time_ms=view_time,
        )
        if ch:
            manga.chapters.append(ch)
        if hist:
            manga.history.append(hist)

    return manga


def parse_category_names(category_input: Optional[str]) -> List[str]:
    """Parse comma-separated category string into a list of category names."""
    if not category_input:
        return []
    cleaned = category_input.strip()
    if cleaned.lower() in ("none", "null", "no", "无", "false", "0", ""):
        return []
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    return parts


def convert_zaimanhua_all_to_backup(
    subscriptions: List[Dict[str, Any]],
    reading_records: Optional[List[Dict[str, Any]]] = None,
    source_id: int = DEFAULT_ZAIMANHUA_SOURCE_ID,
    source_name: str = DEFAULT_ZAIMANHUA_SOURCE_NAME,
    category_name: Optional[str] = "再漫画",
) -> MihonBackup:
    """Combine subscribed comics and reading history into a MihonBackup structure."""
    category_names = parse_category_names(category_name)
    categories: List[MihonCategory] = []
    category_orders: List[int] = []

    for idx, name in enumerate(category_names):
        cat_order = idx
        cat_id = idx + 1
        category_orders.append(cat_order)
        categories.append(
            MihonCategory(
                name=name,
                id=cat_id,
                order=cat_order,
                flags=0,
            )
        )

    manga_by_url: Dict[str, MihonManga] = {}

    # 1. Add subscriptions as favorite manga
    for item in subscriptions:
        manga = sub_item_to_mihon_manga(
            item=item,
            source_id=source_id,
            category_ids=category_orders,
            is_favorite=True,
        )
        if manga.url:
            manga_by_url[manga.url] = manga

    # 2. Add or update reading records
    if reading_records:
        for r_item in reading_records:
            comic_id = r_item.get("biz_id") or r_item.get("id") or r_item.get("comic_id")
            url = normalize_comic_url(comic_id)
            if not url:
                continue

            ch_id = r_item.get("chapter_id")
            ch_name = r_item.get("chapter_name")
            view_time = parse_datetime_to_ms(r_item.get("viewing_time"))

            if url in manga_by_url:
                existing_manga = manga_by_url[url]
                if ch_id:
                    ch, hist = create_chapter_and_history(
                        comic_id=comic_id,
                        chapter_id=ch_id,
                        chapter_name=ch_name,
                        viewing_time_ms=view_time,
                    )
                    if ch:
                        existing_manga.chapters = [ch]
                    if hist:
                        existing_manga.history = [hist]
            else:
                manga = sub_item_to_mihon_manga(
                    item=r_item,
                    source_id=source_id,
                    category_ids=[],
                    is_favorite=False,
                )
                if manga.url:
                    manga_by_url[manga.url] = manga

    sources = [
        MihonSource(
            source_id=source_id,
            name=source_name,
        )
    ]

    return MihonBackup(
        backup_manga=list(manga_by_url.values()),
        backup_categories=categories,
        backup_sources=sources,
    )


def convert_json_file_to_backup(
    input_path: Union[str, Path],
    source_id: int = DEFAULT_ZAIMANHUA_SOURCE_ID,
    source_name: str = DEFAULT_ZAIMANHUA_SOURCE_NAME,
    category_name: Optional[str] = "再漫画",
) -> MihonBackup:
    """Convert an existing JSON file to MihonBackup."""
    path = Path(input_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        if "data" in data and isinstance(data["data"], dict) and "subList" in data["data"]:
            items = data["data"]["subList"]
        elif "data" in data and isinstance(data["data"], dict) and "recordList" in data["data"]:
            return convert_zaimanhua_all_to_backup(
                subscriptions=[],
                reading_records=data["data"]["recordList"],
                source_id=source_id,
                source_name=source_name,
                category_name=category_name,
            )
        elif "subList" in data:
            items = data["subList"]
        elif "recordList" in data:
            return convert_zaimanhua_all_to_backup(
                subscriptions=[],
                reading_records=data["recordList"],
                source_id=source_id,
                source_name=source_name,
                category_name=category_name,
            )
        elif "backupManga" in data:
            return convert_zaimanhua_all_to_backup(
                subscriptions=data.get("backupManga", []),
                reading_records=None,
                source_id=source_id,
                source_name=source_name,
                category_name=category_name,
            )
        else:
            items = [data]
    else:
        raise ValueError(f"Unsupported JSON structure in {input_path}")

    return convert_zaimanhua_all_to_backup(
        subscriptions=items,
        reading_records=None,
        source_id=source_id,
        source_name=source_name,
        category_name=category_name,
    )

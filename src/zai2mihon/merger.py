"""Merge ZaiManhua cloud subscriptions and reading history into an existing .tachibk backup."""

from __future__ import annotations

import gzip
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from zai2mihon.converter import (
    create_chapter_and_history,
    parse_category_names,
    parse_datetime_to_ms,
    sub_item_to_mihon_manga,
)
from zai2mihon.models import (
    DEFAULT_ZAIMANHUA_SOURCE_ID,
    DEFAULT_ZAIMANHUA_SOURCE_NAME,
    MihonManga,
)
from zai2mihon.parser import (
    normalize_chapter_url,
    normalize_comic_url,
    repair_mojibake,
)
from zai2mihon.proto import schema_mihon_pb2
from zai2mihon.proto.serializer import (
    copy_chapter_model_to_pb,
    copy_history_model_to_pb,
    copy_manga_model_to_pb,
    read_tachibk,
)

logger = logging.getLogger(__name__)


def merge_zaimanhua_into_backup_pb(
    backup_pb: schema_mihon_pb2.Backup,
    subscriptions: List[Dict[str, Any]],
    reading_records: Optional[List[Dict[str, Any]]] = None,
    source_id: int = DEFAULT_ZAIMANHUA_SOURCE_ID,
    category_name: Optional[str] = "再漫画",
) -> Tuple[schema_mihon_pb2.Backup, Dict[str, int]]:
    """Merge ZaiManhua subscribed comics and reading records into an existing Protobuf Backup message."""
    stats = {
        "updated_favorites": 0,
        "new_manga_added": 0,
        "updated_history": 0,
        "chapters_marked_read": 0,
    }

    # 1. Categories
    category_names = parse_category_names(category_name)
    target_category_orders: List[int] = []

    if category_names:
        existing_cat_by_name = {c.name.strip().lower(): c for c in backup_pb.backupCategories}
        current_max_order = max((c.order for c in backup_pb.backupCategories), default=-1)

        for name in category_names:
            key = name.strip().lower()
            if key in existing_cat_by_name:
                target_category_orders.append(existing_cat_by_name[key].order)
            else:
                current_max_order += 1
                new_cat = backup_pb.backupCategories.add()
                new_cat.name = name.strip()
                new_cat.order = current_max_order
                new_cat.id = len(backup_pb.backupCategories)
                new_cat.flags = 0
                existing_cat_by_name[key] = new_cat
                target_category_orders.append(new_cat.order)

    # 2. Repair text in existing backup and index manga by comic ID
    manga_by_comic_id: Dict[str, schema_mihon_pb2.BackupManga] = {}
    for m in backup_pb.backupManga:
        if m.title:
            m.title = repair_mojibake(m.title)
        if m.author:
            m.author = repair_mojibake(m.author)
        if m.artist:
            m.artist = repair_mojibake(m.artist)
        if m.description:
            m.description = repair_mojibake(m.description)
        for ch in m.chapters:
            if ch.name:
                ch.name = repair_mojibake(ch.name)

        if m.source == source_id:
            cid = normalize_comic_url(m.url)
            if cid:
                manga_by_comic_id[cid] = m

    # 3. Merge subscriptions (bookshelf)
    for item in subscriptions:
        comic_id = item.get("id") or item.get("biz_id") or item.get("comic_id")
        cid = normalize_comic_url(comic_id)
        if not cid:
            logger.warning(f"Skipping subscription item due to missing comic ID: {item}")
            continue

        if cid in manga_by_comic_id:
            m = manga_by_comic_id[cid]
            if not m.favorite:
                m.favorite = True
                stats["updated_favorites"] += 1
            if target_category_orders:
                existing_cats = set(m.categories)
                for cat_ord in target_category_orders:
                    if cat_ord not in existing_cats:
                        m.categories.append(cat_ord)
        else:
            new_m = sub_item_to_mihon_manga(
                item=item,
                source_id=source_id,
                category_ids=target_category_orders,
                is_favorite=True,
            )
            m_pb = backup_pb.backupManga.add()
            copy_manga_model_to_pb(m_pb, new_m)
            manga_by_comic_id[cid] = m_pb
            stats["new_manga_added"] += 1

    # 4. Merge reading records (history)
    if reading_records:
        for r_item in reading_records:
            comic_id = r_item.get("biz_id") or r_item.get("id") or r_item.get("comic_id")
            cid = normalize_comic_url(comic_id)
            if not cid:
                logger.warning(f"Skipping reading record item due to missing comic ID: {r_item}")
                continue

            ch_id = r_item.get("chapter_id")
            ch_name = repair_mojibake(r_item.get("chapter_name", ""))
            view_time_ms = parse_datetime_to_ms(r_item.get("viewing_time"))

            if cid in manga_by_comic_id:
                m = manga_by_comic_id[cid]
                stats["updated_history"] += 1

                if len(m.chapters) > 0:
                    matched_idx = -1

                    # 1. Exact match by chapter URL or last segment
                    if ch_id:
                        target_url = normalize_chapter_url(cid, ch_id)
                        target_ch_id_str = str(ch_id).strip()
                        for idx, ch in enumerate(m.chapters):
                            if ch.url == target_url or ch.url.rstrip("/").rsplit("/", 1)[-1] == target_ch_id_str:
                                matched_idx = idx
                                break

                    # 2. Fallback: match by chapter number from repaired name
                    if matched_idx == -1 and ch_name:
                        match = re.search(r"(\d+(\.\d+)?)", ch_name)
                        if match:
                            target_val = float(match.group(1))
                            for idx, ch in enumerate(m.chapters):
                                if abs(ch.chapterNumber - target_val) < 0.01:
                                    matched_idx = idx
                                    break

                    if matched_idx != -1:
                        target_ch = m.chapters[matched_idx]
                        target_url = target_ch.url

                        if not target_ch.read:
                            target_ch.read = True
                            stats["chapters_marked_read"] += 1
                        target_ch.lastPageRead = 1

                        existing_hist = next((h for h in m.history if h.url == target_url), None)
                        if existing_hist:
                            if view_time_ms > 0 and view_time_ms > existing_hist.lastRead:
                                existing_hist.lastRead = view_time_ms
                        else:
                            hist_pb = m.history.add()
                            hist_pb.url = target_url
                            hist_pb.lastRead = view_time_ms
                            hist_pb.readDuration = 0
                else:
                    if ch_id:
                        ch_model, hist_model = create_chapter_and_history(
                            comic_id=cid,
                            chapter_id=ch_id,
                            chapter_name=ch_name,
                            viewing_time_ms=view_time_ms,
                        )
                        if ch_model and hist_model:
                            ch_pb = m.chapters.add()
                            copy_chapter_model_to_pb(ch_pb, ch_model)
                            hist_pb = m.history.add()
                            copy_history_model_to_pb(hist_pb, hist_model)
            else:
                if ch_id:
                    new_m = sub_item_to_mihon_manga(
                        item=r_item,
                        source_id=source_id,
                        category_ids=[],
                        is_favorite=False,
                    )
                    ch_model, hist_model = create_chapter_and_history(
                        comic_id=cid,
                        chapter_id=ch_id,
                        chapter_name=ch_name,
                        viewing_time_ms=view_time_ms,
                    )
                    m_pb = backup_pb.backupManga.add()
                    copy_manga_model_to_pb(m_pb, new_m)

                    if ch_model and hist_model:
                        ch_pb = m_pb.chapters.add()
                        copy_chapter_model_to_pb(ch_pb, ch_model)
                        hist_pb = m_pb.history.add()
                        copy_history_model_to_pb(hist_pb, hist_model)

                    manga_by_comic_id[cid] = m_pb
                    stats["new_manga_added"] += 1
                    stats["updated_history"] += 1

    return backup_pb, stats


def merge_and_export_tachibk(
    input_backup_path: Path,
    output_backup_path: Path,
    subscriptions: List[Dict[str, Any]],
    reading_records: Optional[List[Dict[str, Any]]] = None,
    source_id: int = DEFAULT_ZAIMANHUA_SOURCE_ID,
    category_name: Optional[str] = "再漫画",
) -> Tuple[Path, Dict[str, int]]:
    """Load an existing .tachibk file, merge cloud data into it, and write the output."""
    backup_pb = read_tachibk(input_backup_path)
    modified_pb, stats = merge_zaimanhua_into_backup_pb(
        backup_pb=backup_pb,
        subscriptions=subscriptions,
        reading_records=reading_records,
        source_id=source_id,
        category_name=category_name,
    )

    serialized_bytes = modified_pb.SerializeToString()
    output_backup_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output_backup_path, "wb") as f:
        f.write(serialized_bytes)

    return output_backup_path, stats

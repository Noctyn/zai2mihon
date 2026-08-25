"""Serialization and deserialization between MihonBackup models and .tachibk Protobuf / JSON files."""

from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path
from typing import Any, Dict, Union

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
from zai2mihon.proto import schema_mihon_pb2


def copy_manga_model_to_pb(
    m_pb: schema_mihon_pb2.BackupManga,
    model: MihonManga,
) -> None:
    """Populate a BackupManga Protobuf message with all fields from a MihonManga domain model."""
    m_pb.source = model.source
    m_pb.url = model.url
    if model.title:
        m_pb.title = model.title
    if model.author:
        m_pb.author = model.author
    if model.artist:
        m_pb.artist = model.artist
    if model.description:
        m_pb.description = model.description
    if model.genre:
        m_pb.genre.extend(model.genre)
    m_pb.status = model.status
    if model.thumbnail_url:
        m_pb.thumbnailUrl = model.thumbnail_url
    if model.date_added:
        m_pb.dateAdded = model.date_added
    if model.categories:
        m_pb.categories.extend(model.categories)
    m_pb.favorite = model.favorite
    m_pb.initialized = model.initialized
    m_pb.chapterFlags = model.chapter_flags
    m_pb.viewer_flags = model.viewer_flags
    m_pb.updateStrategy = model.update_strategy
    if model.version:
        m_pb.version = model.version
    if model.memo:
        m_pb.memo.extend(model.memo)


def copy_chapter_model_to_pb(
    ch_pb: schema_mihon_pb2.BackupChapter,
    model: MihonChapter,
) -> None:
    """Populate a BackupChapter Protobuf message with all fields from a MihonChapter domain model."""
    ch_pb.url = model.url
    ch_pb.name = model.name
    if model.scanlator:
        ch_pb.scanlator = model.scanlator
    ch_pb.read = model.read
    ch_pb.bookmark = model.bookmark
    ch_pb.lastPageRead = model.last_page_read
    ch_pb.dateFetch = model.date_fetch
    ch_pb.dateUpload = model.date_upload
    ch_pb.chapterNumber = model.chapter_number
    ch_pb.sourceOrder = model.source_order
    if model.last_modified_at:
        ch_pb.lastModifiedAt = model.last_modified_at
    if model.version:
        ch_pb.version = model.version
    if model.memo:
        ch_pb.memo.extend(model.memo)


def copy_history_model_to_pb(
    h_pb: schema_mihon_pb2.BackupHistory,
    model: MihonHistory,
) -> None:
    """Populate a BackupHistory Protobuf message with all fields from a MihonHistory domain model."""
    h_pb.url = model.url
    h_pb.lastRead = model.last_read
    h_pb.readDuration = model.read_duration


def build_protobuf_backup(backup: MihonBackup) -> schema_mihon_pb2.Backup:
    """Convert MihonBackup domain model into schema_mihon_pb2.Backup message."""
    backup_pb = schema_mihon_pb2.Backup()

    # Sources
    sources_to_add = backup.backup_sources
    if not sources_to_add:
        sources_to_add = [
            MihonSource(
                source_id=DEFAULT_ZAIMANHUA_SOURCE_ID,
                name=DEFAULT_ZAIMANHUA_SOURCE_NAME,
            )
        ]

    for src in sources_to_add:
        src_pb = backup_pb.backupSources.add()
        src_pb.sourceId = src.source_id
        if src.name:
            src_pb.name = src.name

    # Categories
    for cat in backup.backup_categories:
        cat_pb = backup_pb.backupCategories.add()
        cat_pb.name = cat.name
        cat_pb.id = cat.id
        cat_pb.order = cat.order
        cat_pb.flags = cat.flags

    # Manga entries
    for m in backup.backup_manga:
        m_pb = backup_pb.backupManga.add()
        copy_manga_model_to_pb(m_pb, m)

        # Chapters
        for ch in m.chapters:
            ch_pb = m_pb.chapters.add()
            copy_chapter_model_to_pb(ch_pb, ch)

        # History
        for h in m.history:
            h_pb = m_pb.history.add()
            copy_history_model_to_pb(h_pb, h)

    return backup_pb


def serialize_to_protobuf_bytes(backup: MihonBackup) -> bytes:
    """Serialize MihonBackup model to uncompressed Protobuf binary bytes."""
    pb = build_protobuf_backup(backup)
    return pb.SerializeToString()


def export_to_tachibk(backup: MihonBackup, output_path: Union[str, Path]) -> Path:
    """Serialize MihonBackup model and write as a gzip-compressed .tachibk file."""
    path = Path(output_path)
    if not path.suffix:
        path = path.with_suffix(".tachibk")

    path.parent.mkdir(parents=True, exist_ok=True)
    pb_bytes = serialize_to_protobuf_bytes(backup)

    with gzip.open(path, "wb") as f:
        f.write(pb_bytes)

    return path


def read_tachibk(input_path: Union[str, Path]) -> schema_mihon_pb2.Backup:
    """Read and decompress a .tachibk file into a Protobuf Backup message."""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Backup file not found: {path}")

    with gzip.open(path, "rb") as f:
        decompressed_bytes = f.read()

    backup = schema_mihon_pb2.Backup()
    backup.ParseFromString(decompressed_bytes)
    return backup


def export_to_json(backup: MihonBackup, output_path: Union[str, Path]) -> Path:
    """Export MihonBackup to a readable JSON representation."""
    path = Path(output_path)
    if not path.suffix:
        path = path.with_suffix(".json")

    path.parent.mkdir(parents=True, exist_ok=True)

    def _convert_item(obj: Any) -> Any:
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode("ascii")
        if isinstance(obj, list):
            return [_convert_item(i) for i in obj]
        if isinstance(obj, dict):
            return {k: _convert_item(v) for k, v in obj.items()}
        return obj

    data = backup.model_dump(by_alias=True)
    clean_data = _convert_item(data)

    out_dict = {
        "backupManga": clean_data.get("backup_manga", clean_data.get("backupManga", [])),
        "backupCategories": clean_data.get("backup_categories", clean_data.get("backupCategories", [])),
        "backupSources": clean_data.get("backup_sources", clean_data.get("backupSources", [])),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(out_dict, f, ensure_ascii=False, indent=2)

    return path

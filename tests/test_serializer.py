"""Tests for zai2mihon serializer module."""

import json
from zai2mihon.models import (
    DEFAULT_ZAIMANHUA_SOURCE_ID,
    MihonBackup,
    MihonCategory,
    MihonChapter,
    MihonHistory,
    MihonManga,
    MihonSource,
)
from zai2mihon.proto.serializer import (
    build_protobuf_backup,
    export_to_json,
    export_to_tachibk,
    read_tachibk,
)


def test_build_protobuf_and_serialize(tmp_path):
    backup = MihonBackup(
        backup_sources=[MihonSource(source_id=DEFAULT_ZAIMANHUA_SOURCE_ID, name="再漫画")],
        backup_categories=[MihonCategory(name="再漫画", id=1, order=0)],
        backup_manga=[
            MihonManga(
                source=DEFAULT_ZAIMANHUA_SOURCE_ID,
                url="77022",
                title="Test Manga",
                categories=[0],
                chapters=[
                    MihonChapter(
                        url="77022/174034",
                        name="第14话",
                        chapter_number=14.0,
                        read=True,
                    )
                ],
                history=[
                    MihonHistory(
                        url="77022/174034",
                        last_read=1782239549000,
                    )
                ],
            )
        ],
    )

    pb = build_protobuf_backup(backup)
    assert len(pb.backupManga) == 1
    assert pb.backupManga[0].url == "77022"
    assert pb.backupManga[0].chapters[0].name == "第14话"

    out_file = tmp_path / "test_backup.tachibk"
    export_to_tachibk(backup, out_file)
    assert out_file.exists()

    loaded = read_tachibk(out_file)
    assert len(loaded.backupManga) == 1
    assert loaded.backupManga[0].title == "Test Manga"
    assert loaded.backupManga[0].chapters[0].url == "77022/174034"
    assert loaded.backupManga[0].history[0].url == "77022/174034"


def test_export_to_json(tmp_path):
    backup = MihonBackup(
        backup_sources=[MihonSource(source_id=DEFAULT_ZAIMANHUA_SOURCE_ID, name="再漫画")],
        backup_categories=[MihonCategory(name="再漫画", id=1, order=0)],
        backup_manga=[
            MihonManga(
                source=DEFAULT_ZAIMANHUA_SOURCE_ID,
                url="77022",
                title="Test Manga",
                categories=[0],
            )
        ],
    )

    json_path = tmp_path / "test.json"
    export_to_json(backup, json_path)
    assert json_path.exists()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "backupManga" in data
    assert len(data["backupManga"]) == 1

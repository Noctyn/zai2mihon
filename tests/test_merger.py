"""Tests for zai2mihon merger module."""

from zai2mihon.merger import merge_zaimanhua_into_backup_pb
from zai2mihon.models import DEFAULT_ZAIMANHUA_SOURCE_ID
from zai2mihon.proto import schema_mihon_pb2


def test_merge_zaimanhua_into_backup_pb():
    backup_pb = schema_mihon_pb2.Backup()

    # Add existing comic from another source (e.g. MangaDex)
    other_m = backup_pb.backupManga.add()
    other_m.source = 5148895169070562838
    other_m.url = "mangadex-manga-1"
    other_m.title = "MangaDex Comic"
    other_m.favorite = True

    # Add existing ZaiManhua comic without favorite
    existing_zai = backup_pb.backupManga.add()
    existing_zai.source = DEFAULT_ZAIMANHUA_SOURCE_ID
    existing_zai.url = "77022"
    existing_zai.title = "Zai Comic"
    existing_zai.favorite = False

    ch = existing_zai.chapters.add()
    ch.url = "77022/174034"
    ch.name = "第14话"
    ch.read = False

    # New cloud data to merge
    subs = [{"id": 77022, "title": "Zai Comic"}]
    records = [
        {
            "biz_id": 77022,
            "chapter_id": 174034,
            "chapter_name": "第14话",
            "viewing_time": 1782239549,
        },
        {
            "biz_id": 99999,
            "title": "Brand New Zai Comic",
            "chapter_id": 2001,
            "chapter_name": "第1话",
            "viewing_time": 1782239549,
        },
    ]

    merged_pb, stats = merge_zaimanhua_into_backup_pb(
        backup_pb=backup_pb,
        subscriptions=subs,
        reading_records=records,
        category_name="再漫画",
    )

    assert stats["updated_favorites"] == 1
    assert stats["new_manga_added"] == 1
    assert stats["chapters_marked_read"] == 1

    # Total manga: 1 MangaDex + 1 Existing Zai + 1 New History-only Zai = 3
    assert len(merged_pb.backupManga) == 3

    # Other source manga untouched
    assert merged_pb.backupManga[0].url == "mangadex-manga-1"
    assert merged_pb.backupManga[0].source == 5148895169070562838

    # Existing Zai comic updated to favorite & chapter marked read
    zai_m = merged_pb.backupManga[1]
    assert zai_m.favorite is True
    assert zai_m.chapters[0].read is True
    assert len(zai_m.history) == 1
    assert zai_m.history[0].url == "77022/174034"

    # New Zai comic is history-only (favorite=False)
    new_zai = merged_pb.backupManga[2]
    assert new_zai.url == "99999"
    assert new_zai.favorite is False
    assert len(new_zai.chapters) == 1

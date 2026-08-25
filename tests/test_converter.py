"""Tests for zai2mihon converter module."""

from zai2mihon.converter import (
    convert_zaimanhua_all_to_backup,
    create_chapter_and_history,
    normalize_status,
    parse_category_names,
    parse_datetime_to_ms,
    sub_item_to_mihon_manga,
)
from zai2mihon.models import DEFAULT_ZAIMANHUA_SOURCE_ID


def test_parse_datetime_to_ms():
    assert parse_datetime_to_ms(1782239549) == 1782239549000
    assert parse_datetime_to_ms("1782239549") == 1782239549000
    assert parse_datetime_to_ms("2026-08-25 12:00:00") > 0


def test_normalize_status():
    assert normalize_status("连载中") == 1
    assert normalize_status("已完结") == 2
    assert normalize_status("完结") == 2
    assert normalize_status(1) == 1
    assert normalize_status(2) == 2


def test_create_chapter_and_history():
    ch, hist = create_chapter_and_history(
        comic_id=77022,
        chapter_id=174034,
        chapter_name="第14话",
        viewing_time_ms=1782239549000,
    )
    assert ch is not None
    assert ch.url == "77022/174034"
    assert ch.name == "第14话"
    assert ch.chapter_number == 14.0
    assert ch.read is True

    assert hist is not None
    assert hist.url == "77022/174034"
    assert hist.last_read == 1782239549000


def test_sub_item_to_mihon_manga():
    item = {
        "id": 77022,
        "title": "总之就是非常想做",
        "cover": "https://images.zaimanhua.com/cover.png",
        "status": "连载中",
        "readingRecord": {
            "chapter_id": 174034,
            "chapter_name": "第14话",
            "viewing_time": 1782239549,
        },
        "last_updatetime": 1787636535,
    }
    manga = sub_item_to_mihon_manga(item, category_ids=[0], is_favorite=True)
    assert manga.title == "总之就是非常想做"
    assert manga.url == "77022"
    assert manga.source == DEFAULT_ZAIMANHUA_SOURCE_ID
    assert manga.favorite is True
    assert manga.status == 1
    assert len(manga.chapters) == 1
    assert manga.chapters[0].name == "第14话"
    assert len(manga.history) == 1


def test_convert_zaimanhua_all_to_backup():
    subs = [
        {
            "id": 77022,
            "title": "Sub Comic 1",
            "cover": "https://example.com/1.jpg",
        }
    ]
    records = [
        {
            "biz_id": 77022,
            "title": "Sub Comic 1",
            "chapter_id": 174034,
            "chapter_name": "第14话",
            "viewing_time": 1782239549,
        },
        {
            "biz_id": 88888,
            "title": "History-Only Comic",
            "chapter_id": 1001,
            "chapter_name": "第1话",
            "viewing_time": 1782239549,
        },
    ]

    backup = convert_zaimanhua_all_to_backup(
        subscriptions=subs,
        reading_records=records,
        category_name="再漫画",
    )

    assert len(backup.backup_manga) == 2
    assert len(backup.backup_categories) == 1
    assert backup.backup_categories[0].name == "再漫画"

    # Sub comic should be favorite
    sub_m = next(m for m in backup.backup_manga if m.url == "77022")
    assert sub_m.favorite is True
    assert len(sub_m.chapters) == 1
    assert sub_m.chapters[0].url == "77022/174034"

    # History-only comic should NOT be favorite
    hist_m = next(m for m in backup.backup_manga if m.url == "88888")
    assert hist_m.favorite is False
    assert len(hist_m.chapters) == 1
    assert hist_m.chapters[0].url == "88888/1001"

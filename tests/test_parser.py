"""Tests for zai2mihon parser module."""

from zai2mihon.parser import (
    clean_path,
    extract_token,
    normalize_chapter_url,
    normalize_comic_url,
    repair_mojibake,
)


def test_extract_token():
    assert extract_token("Bearer eyJhbGciOi...") == "eyJhbGciOi..."
    assert extract_token("bearer token123") == "token123"
    assert extract_token("Token my_token") == "my_token"
    assert extract_token('"raw_token"') == "raw_token"
    assert extract_token("'raw_token'") == "raw_token"
    assert extract_token("pure_token") == "pure_token"


def test_clean_path():
    assert clean_path('"D:/path/test.tachibk"') == "D:/path/test.tachibk"
    assert clean_path("  'C:/my backup'  ") == "C:/my backup"
    assert clean_path("normal_path") == "normal_path"


def test_normalize_comic_url():
    assert normalize_comic_url(77022) == "77022"
    assert normalize_comic_url("77022") == "77022"
    assert normalize_comic_url("/77022/") == "77022"
    assert normalize_comic_url(None) == ""


def test_normalize_chapter_url():
    assert normalize_chapter_url(77022, 174034) == "77022/174034"
    assert normalize_chapter_url("77022", "174034") == "77022/174034"
    assert normalize_chapter_url("77022", "77022/174034") == "77022/174034"
    assert normalize_chapter_url(None, 123) == ""
    assert normalize_chapter_url(77022, None) == "77022"


def test_repair_mojibake():
    assert repair_mojibake("ç¬¬01å·»") == "第01巻"
    assert repair_mojibake("33è¯\x9då…¬å‘Š") == "33话公告"
    assert repair_mojibake("第01话") == "第01话"

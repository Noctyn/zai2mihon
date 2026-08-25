"""Tests for ZaiManhua API client."""

import pytest
import httpx
from zai2mihon.client import ZaiManhuaClient, normalize_base_url


def test_normalize_base_url():
    assert normalize_base_url("i.zaimanhua.com") == "https://i.zaimanhua.com"
    assert normalize_base_url("http://i.zaimanhua.com/") == "http://i.zaimanhua.com"
    assert normalize_base_url("  https://i.zaimanhua.com/  ") == "https://i.zaimanhua.com"
    assert normalize_base_url("") == "https://i.zaimanhua.com"
    assert normalize_base_url(None) == "https://i.zaimanhua.com"


def test_client_init_headers():
    client = ZaiManhuaClient(token="Bearer sample_jwt_token", base_url="i.zaimanhua.com")
    assert client.token == "sample_jwt_token"
    assert client.base_url == "https://i.zaimanhua.com"
    assert client.client.headers["authorization"] == "Bearer sample_jwt_token"
    assert client.client.headers["platform"] == "pc"


def test_client_fetch_all_subscriptions_pagination(monkeypatch):
    client = ZaiManhuaClient(token="test_token")

    def mock_get(endpoint, params=None):
        page = params.get("page", 1) if params else 1
        if page == 1:
            return httpx.Response(
                status_code=200,
                json={
                    "errno": 0,
                    "errmsg": "",
                    "data": {
                        "subList": [{"id": 101, "title": "Manga 1"}],
                    },
                },
                request=httpx.Request("GET", endpoint),
            )
        else:
            return httpx.Response(
                status_code=200,
                json={
                    "errno": 0,
                    "errmsg": "",
                    "data": {
                        "subList": [],
                    },
                },
                request=httpx.Request("GET", endpoint),
            )

    monkeypatch.setattr(client.client, "get", mock_get)

    results = client.fetch_all_subscriptions(page_size=1, delay_seconds=0)
    assert len(results) == 1
    assert results[0]["title"] == "Manga 1"


def test_client_fetch_all_reading_records_pagination(monkeypatch):
    client = ZaiManhuaClient(token="test_token")

    def mock_get(endpoint, params=None):
        return httpx.Response(
            status_code=200,
            json={
                "errno": 0,
                "errmsg": "",
                "data": {
                    "recordList": [
                        {
                            "biz_id": 202,
                            "title": "History Manga 1",
                            "chapter_id": 501,
                            "chapter_name": "第1话",
                            "viewing_time": 1785887613,
                        }
                    ],
                },
            },
            request=httpx.Request("GET", endpoint),
        )

    monkeypatch.setattr(client.client, "get", mock_get)

    results = client.fetch_all_reading_records(page_size=10, delay_seconds=0)
    assert len(results) == 1
    assert results[0]["title"] == "History Manga 1"


def test_client_unauthorized_error_non_retryable(monkeypatch):
    client = ZaiManhuaClient(token="invalid_token")
    call_count = 0

    def mock_get(endpoint, params=None):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            status_code=401,
            json={"errno": 401, "errmsg": "Invalid token"},
            request=httpx.Request("GET", endpoint),
        )

    monkeypatch.setattr(client.client, "get", mock_get)

    with pytest.raises(PermissionError):
        client.get_subscriptions_page()

    assert call_count == 1


def test_client_bad_request_error_non_retryable(monkeypatch):
    client = ZaiManhuaClient(token="valid_token")
    call_count = 0

    def mock_get(endpoint, params=None):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            status_code=400,
            text="Bad Request",
            request=httpx.Request("GET", endpoint),
        )

    monkeypatch.setattr(client.client, "get", mock_get)

    with pytest.raises(RuntimeError) as exc_info:
        client.get_subscriptions_page()

    assert "Client Error (400)" in str(exc_info.value)
    assert call_count == 1


def test_client_rate_limit_preserves_error(monkeypatch):
    client = ZaiManhuaClient(token="valid_token", max_retries=2)
    call_count = 0

    def mock_get(endpoint, params=None):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            status_code=429,
            headers={"retry-after": "0"},
            request=httpx.Request("GET", endpoint),
        )

    monkeypatch.setattr(client.client, "get", mock_get)

    with pytest.raises(RuntimeError) as exc_info:
        client.get_subscriptions_page()

    assert "Rate limited (429)" in str(exc_info.value)
    assert call_count == 2

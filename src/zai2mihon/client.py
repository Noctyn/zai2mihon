"""ZaiManhua (再漫画) API client for fetching subscriptions and reading history using Bearer JWT authentication."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import httpx

from zai2mihon.parser import extract_token

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = os.environ.get("ZAIMANHUA_BASE_URL", "https://i.zaimanhua.com")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

# Known domain presets
KNOWN_DOMAINS: List[Tuple[str, str]] = [
    ("https://i.zaimanhua.com", "官方接口站 (默认)"),
    ("https://www.zaimanhua.com", "官方主站"),
]


def normalize_base_url(url: Optional[str]) -> str:
    """Normalize base URL with scheme and trimmed slashes."""
    if not url:
        return DEFAULT_BASE_URL
    clean = url.strip().rstrip("/")
    if not clean:
        return DEFAULT_BASE_URL
    if not (clean.startswith("http://") or clean.startswith("https://")):
        clean = f"https://{clean}"
    return clean


class ZaiManhuaClient:
    """HTTP client for ZaiManhua API with Bearer JWT authentication and resilient retry handling."""

    def __init__(
        self,
        token: str,
        base_url: Optional[str] = None,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 5,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        self.token = extract_token(token)
        self.proxy = proxy
        self.timeout = timeout
        self.max_retries = max_retries
        self._init_client()

    def _init_client(self) -> None:
        """Initialize or recreate the httpx client."""
        req_headers = {
            "user-agent": DEFAULT_USER_AGENT,
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "platform": "pc",
            "referer": f"{self.base_url}/",
            "authorization": f"Bearer {self.token}",
        }
        self.client = httpx.Client(
            base_url=self.base_url,
            headers=req_headers,
            proxy=self.proxy,
            timeout=self.timeout,
            follow_redirects=True,
        )

    def set_token(self, token: str) -> None:
        """Update authorization token."""
        self.token = extract_token(token)
        self.client.headers["authorization"] = f"Bearer {self.token}"

    def _get_with_retry(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Perform a GET request, retrying on network drops, timeouts, 429s, or 5xx server errors."""
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.client.get(endpoint, params=params)

                # 1. Deterministic Non-Retryable Client Errors (401, 403, 404)
                if resp.status_code == 401:
                    raise PermissionError("Unauthorized (401): 再漫画 Token/JWT 无效或已过期。")
                if resp.status_code == 403:
                    raise PermissionError("Forbidden (403): 访问被拒绝，请检查 Token 或 IP 限制。")
                if resp.status_code == 404:
                    raise FileNotFoundError(f"Not Found (404): 接口不存在: {endpoint}")

                # 2. Other 4xx Client Errors (e.g. 400 Bad Request) -> Fail fast
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    raise RuntimeError(f"Client Error ({resp.status_code}): {resp.text}")

                # 3. Rate limiting (429) -> Retry with Retry-After header
                if resp.status_code == 429:
                    last_exception = RuntimeError(
                        f"Rate limited (429) on {endpoint} after {self.max_retries} attempts."
                    )
                    retry_after = resp.headers.get("retry-after")
                    sleep_sec = float(retry_after) if retry_after and retry_after.isdigit() else attempt * 2.0
                    logger.warning(
                        f"Rate limited (429). Sleeping {sleep_sec}s before retry ({attempt}/{self.max_retries})..."
                    )
                    time.sleep(sleep_sec)
                    continue

                # 4. Server Errors (5xx) -> Retry with backoff
                if resp.status_code in (500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"Server Error ({resp.status_code})",
                        request=resp.request,
                        response=resp,
                    )

                resp.raise_for_status()

                # 5. Parse JSON payload
                data = resp.json()

                # 6. ZaiManhua Business-Level Error Handling (errno != 0)
                if isinstance(data, dict) and data.get("errno") not in (0, None):
                    errno = data.get("errno")
                    errmsg = data.get("errmsg", "Unknown error")
                    if errno in (-1, 401, 1001):
                        raise PermissionError(f"Unauthorized ({errno}): {errmsg}")
                    raise RuntimeError(f"API Error ({errno}): {errmsg}")

                return data

            except (PermissionError, FileNotFoundError, RuntimeError):
                # Non-retryable errors -> Re-raise immediately
                raise

            except (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError) as net_err:
                last_exception = net_err
                logger.warning(
                    f"Network error on {endpoint} ({attempt}/{self.max_retries}): {net_err}. Retrying..."
                )
                if attempt < self.max_retries:
                    if isinstance(net_err, (httpx.NetworkError, httpx.RemoteProtocolError)):
                        try:
                            self.client.close()
                        except Exception:
                            pass
                        self._init_client()
                    time.sleep(min(attempt * 1.5, 6.0))

            except ValueError as json_err:
                last_exception = json_err
                logger.warning(
                    f"Invalid JSON response on {endpoint} ({attempt}/{self.max_retries}): {json_err}."
                )
                if attempt < self.max_retries:
                    time.sleep(min(attempt * 1.5, 6.0))

        if last_exception:
            raise last_exception
        raise RuntimeError(f"Request to {endpoint} failed after {self.max_retries} attempts.")

    def get_subscriptions_page(
        self,
        page: int = 1,
        size: int = 50,
        status: str = "",
        first_letter: str = "",
    ) -> Dict[str, Any]:
        """Fetch a single page of subscribed comics from ZaiManhua."""
        endpoint = "/api/app/v1/comic/sub/list"
        params = {
            "status": status,
            "firstLetter": first_letter,
            "page": page,
            "size": size,
        }
        return self._get_with_retry(endpoint, params=params)

    def fetch_all_subscriptions(
        self,
        page_size: int = 50,
        delay_seconds: float = 0.2,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Paginate and fetch all subscribed comics."""
        all_items: List[Dict[str, Any]] = []
        page = 1

        while True:
            data = self.get_subscriptions_page(page=page, size=page_size)
            sub_data = data.get("data", {})
            if isinstance(sub_data, dict):
                items = sub_data.get("subList", [])
            elif isinstance(sub_data, list):
                items = sub_data
            else:
                items = []

            if not items:
                break

            all_items.extend(items)

            if progress_callback:
                progress_callback(len(all_items), len(all_items))

            if len(items) < page_size:
                break

            page += 1
            if delay_seconds > 0:
                time.sleep(delay_seconds)

        return all_items

    def get_reading_records_page(
        self,
        page: int = 1,
        page_size: int = 50,
        source: str = "mh",
    ) -> Dict[str, Any]:
        """Fetch a single page of reading records/history from ZaiManhua."""
        endpoint = "/api/app/v1/readingRecord/list"
        params = {
            "source": source,
            "page": page,
            "pageSize": page_size,
        }
        return self._get_with_retry(endpoint, params=params)

    def fetch_all_reading_records(
        self,
        page_size: int = 50,
        delay_seconds: float = 0.2,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Paginate and fetch all reading records/history."""
        all_items: List[Dict[str, Any]] = []
        page = 1

        while True:
            data = self.get_reading_records_page(page=page, page_size=page_size)
            rec_data = data.get("data", {})
            if isinstance(rec_data, dict):
                items = rec_data.get("recordList", [])
            elif isinstance(rec_data, list):
                items = rec_data
            else:
                items = []

            if not items:
                break

            all_items.extend(items)

            if progress_callback:
                progress_callback(len(all_items), len(all_items))

            if len(items) < page_size:
                break

            page += 1
            if delay_seconds > 0:
                time.sleep(delay_seconds)

        return all_items

    def close(self) -> None:
        """Close client connection."""
        self.client.close()

    def __enter__(self) -> "ZaiManhuaClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

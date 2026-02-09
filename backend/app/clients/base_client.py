"""Reusable base for any external HTTP API client."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

import httpx

from app.utils.retry import with_retry

logger = logging.getLogger(__name__)


class BaseHTTPClient:
    """Thin wrapper around httpx with logging, error handling, retry, and optional disk cache.

    Subclasses (FMPClient, etc.) only need to implement domain methods.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        cache_dir: Optional[Path] = None,
        retry_max_attempts: int = 3,
        retry_initial_delay: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(timeout=timeout)
        self._cache_dir = cache_dir
        self._retry_max_attempts = retry_max_attempts
        self._retry_initial_delay = retry_initial_delay
        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ── HTTP helpers ─────────────────────────────────────────────────

    def _cache_key(self, endpoint: str, params: Optional[dict] = None) -> str:
        """Build a deterministic filename from the endpoint + params."""
        safe = endpoint.replace("/", "_")
        if params:
            # Exclude API key from cache key
            filtered = {k: v for k, v in sorted(params.items()) if k != "apikey"}
            suffix = hashlib.md5(json.dumps(filtered).encode()).hexdigest()[:10]
            return f"{safe}_{suffix}.json"
        return f"{safe}.json"

    def _get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """GET request with caching and retry logic.

        Retries on:
        - 5xx server errors
        - 429 rate limit
        - Network errors
        - Timeouts

        Does NOT retry on:
        - 4xx client errors (bad request, auth failure, etc.)
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        params = dict(params or {})
        if self.api_key:
            params["apikey"] = self.api_key

        # Check disk cache first
        if self._cache_dir:
            key = self._cache_key(endpoint, params)
            cache_path = self._cache_dir / key
            if cache_path.exists():
                logger.debug("CACHE HIT %s", cache_path.name)
                return json.loads(cache_path.read_text())

        # Apply retry logic
        data = self._get_with_retry(url, params)

        # Save to disk cache
        if self._cache_dir:
            key = self._cache_key(endpoint, params)
            cache_path = self._cache_dir / key
            cache_path.write_text(json.dumps(data, indent=2))
            logger.debug("CACHE SAVE %s", cache_path.name)

        return data

    def _get_with_retry(self, url: str, params: dict) -> Any:
        """Internal GET with retry decorator applied."""

        @with_retry(
            max_attempts=self._retry_max_attempts,
            initial_delay=self._retry_initial_delay,
            retry_on=(
                httpx.HTTPStatusError,
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.ConnectError,
            ),
            reraise_on=(),  # Let the status code check handle 4xx
        )
        def _do_get():
            logger.debug(
                "GET %s params=%s",
                url,
                {k: v for k, v in params.items() if k != "apikey"},
            )
            resp = self._client.get(url, params=params)

            # Only retry on 5xx and 429
            if resp.status_code >= 500 or resp.status_code == 429:
                logger.warning(
                    "Retryable error %d from %s", resp.status_code, url
                )
                resp.raise_for_status()  # Triggers retry
            elif resp.status_code >= 400:
                # 4xx errors are client errors - don't retry, return None
                logger.warning(
                    "Client error %d for %s - not retrying",
                    resp.status_code,
                    url,
                )
                return None  # Let caller handle missing data

            return resp.json()

        return _do_get()

    # ── lifecycle ────────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

"""Reusable base for any external HTTP API client."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class BaseHTTPClient:
    """Thin wrapper around httpx with logging, error handling, and optional disk cache.

    Subclasses (FMPClient, etc.) only need to implement domain methods.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        cache_dir: Optional[Path] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(timeout=timeout)
        self._cache_dir = cache_dir
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

        logger.debug("GET %s params=%s", url, {k: v for k, v in params.items() if k != "apikey"})
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        # Save to disk cache
        if self._cache_dir:
            key = self._cache_key(endpoint, params)
            cache_path = self._cache_dir / key
            cache_path.write_text(json.dumps(data, indent=2))
            logger.debug("CACHE SAVE %s", cache_path.name)

        return data

    # ── lifecycle ────────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

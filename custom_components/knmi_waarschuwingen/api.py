"""Client for the KNMI Data Platform Open Data API."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import API_BASE_URL, DATASET_NAME, DATASET_VERSION

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class KnmiApiError(Exception):
    """Generic error talking to the KNMI API."""


class KnmiAuthError(KnmiApiError):
    """The API key was rejected."""


class KnmiRateLimitError(KnmiApiError):
    """The API rate limit or quota was exceeded."""


class KnmiWarningsClient:
    """Fetch the newest KNMI public weather warnings snapshot."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        """Initialise the client."""
        self._session = session
        self._api_key = api_key.strip()
        self._base = (
            f"{API_BASE_URL}/datasets/{DATASET_NAME}/versions/{DATASET_VERSION}/files"
        )

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with self._session.get(
                url,
                params=params,
                headers={"Authorization": self._api_key},
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise KnmiAuthError(f"API key rejected (HTTP {resp.status})")
                if resp.status == 429:
                    raise KnmiRateLimitError("KNMI API rate limit exceeded")
                if resp.status >= 400:
                    text = await resp.text()
                    raise KnmiApiError(f"HTTP {resp.status}: {text[:200]}")
                return await resp.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise KnmiApiError(f"Error communicating with KNMI: {err}") from err

    async def async_get_latest_filename(self) -> str | None:
        """Return the filename of the newest snapshot (JSON), or None."""
        data = await self._get_json(
            self._base,
            params={"maxKeys": "25", "orderBy": "created", "sorting": "desc"},
        )
        files = data.get("files") if isinstance(data, dict) else None
        if not files:
            return None
        names = [f.get("filename") for f in files if isinstance(f, dict)]
        # The dataset contains JSON and CAP XML; we only want the JSON snapshot.
        for name in names:
            if isinstance(name, str) and name.lower().endswith(".json"):
                return name
        return None

    async def async_download(self, filename: str) -> dict[str, Any]:
        """Download and decode a snapshot file."""
        data = await self._get_json(f"{self._base}/{filename}/url")
        url = data.get("temporaryDownloadUrl") if isinstance(data, dict) else None
        if not url:
            raise KnmiApiError("No temporaryDownloadUrl in KNMI response")
        try:
            # Presigned URL: no Authorization header needed (or allowed).
            async with self._session.get(url, timeout=REQUEST_TIMEOUT) as resp:
                resp.raise_for_status()
                snapshot = await resp.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            raise KnmiApiError(f"Error downloading {filename}: {err}") from err
        if not isinstance(snapshot, dict):
            raise KnmiApiError(f"Unexpected content in {filename}")
        return snapshot

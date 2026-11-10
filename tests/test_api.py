"""Tests for the API client error mapping."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.knmi_waarschuwingen.api import (
    KnmiApiError,
    KnmiAuthError,
    KnmiRateLimitError,
    KnmiWarningsClient,
)

URL = (
    "https://api.dataplatform.knmi.nl/open-data/v1/datasets/"
    "KNMI-public-weather-warnings/versions/1.0/files"
)


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (401, KnmiAuthError),
        (403, KnmiAuthError),
        (429, KnmiRateLimitError),
        (404, KnmiApiError),
        (500, KnmiApiError),
    ],
)
async def test_http_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int, exc
) -> None:
    aioclient_mock.get(URL, status=status, text='{"message":"nope"}')
    client = KnmiWarningsClient(async_get_clientsession(hass), "key")
    with pytest.raises(exc, match=f"HTTP {status}"):
        await client.async_get_latest_filename()


async def test_latest_json_and_download(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        URL,
        json={
            "files": [
                {"filename": "public_warnings_b.xml"},
                {"filename": "public_warnings_b.json"},
            ]
        },
    )
    aioclient_mock.get(
        f"{URL}/public_warnings_b.json/url",
        json={"temporaryDownloadUrl": "https://example.s3.test/file.json"},
    )
    aioclient_mock.get("https://example.s3.test/file.json", json={"warnings": []})
    client = KnmiWarningsClient(async_get_clientsession(hass), "key")
    name = await client.async_get_latest_filename()
    assert name == "public_warnings_b.json"
    assert await client.async_download(name) == {"warnings": []}
    # Authorization header is sent to KNMI.
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "key"

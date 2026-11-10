"""Fixtures for KNMI Waarschuwingen tests."""

from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.knmi_waarschuwingen.const import CONF_API_KEY, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"

ZWOLLE = (52.5168, 6.0830)
AMSTERDAM = (52.3676, 4.9041)


def load_snapshot() -> dict[str, Any]:
    """Load the sample snapshot."""
    return json.loads((FIXTURES / "public_warnings.json").read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in all tests."""


@pytest.fixture
def snapshot_data() -> dict[str, Any]:
    """Return the sample snapshot."""
    return load_snapshot()


@pytest.fixture
def mock_client(snapshot_data: dict[str, Any]) -> Generator[dict[str, AsyncMock]]:
    """Patch the API client."""
    with (
        patch(
            "custom_components.knmi_waarschuwingen.api.KnmiWarningsClient.async_get_latest_filename",
            new_callable=AsyncMock,
            return_value="public_warnings_2026-11-10T113000000000Z.json",
        ) as latest,
        patch(
            "custom_components.knmi_waarschuwingen.api.KnmiWarningsClient.async_download",
            new_callable=AsyncMock,
            return_value=snapshot_data,
        ) as download,
    ):
        yield {"latest": latest, "download": download}


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry for Zwolle."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Zwolle",
        unique_id=f"{ZWOLLE[0]:.4f}_{ZWOLLE[1]:.4f}",
        data={
            CONF_NAME: "Zwolle",
            CONF_LATITUDE: ZWOLLE[0],
            CONF_LONGITUDE: ZWOLLE[1],
            CONF_API_KEY: "",
        },
        options={"language": "nl"},
    )

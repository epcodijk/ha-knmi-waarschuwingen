"""Tests for the config and options flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.knmi_waarschuwingen.api import KnmiApiError, KnmiAuthError
from custom_components.knmi_waarschuwingen.const import DOMAIN

from .conftest import ZWOLLE

VALIDATE = (
    "custom_components.knmi_waarschuwingen.config_flow."
    "KnmiWarningsClient.async_get_latest_filename"
)

USER_INPUT = {
    "name": "Zwolle",
    "latitude": ZWOLLE[0],
    "longitude": ZWOLLE[1],
    "api_key": "",
}


@pytest.fixture(autouse=True)
def no_setup():
    """Don't actually set up the entry after the flow."""
    with patch(
        "custom_components.knmi_waarschuwingen.async_setup_entry", return_value=True
    ):
        yield


async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch(VALIDATE, new_callable=AsyncMock, return_value="x.json"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Zwolle"
    assert result["data"]["latitude"] == ZWOLLE[0]
    assert result["data"]["api_key"] == ""


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [(KnmiAuthError("x"), "invalid_auth"), (KnmiApiError("x"), "cannot_connect")],
)
async def test_user_flow_errors(
    hass: HomeAssistant, side_effect: Exception, error: str
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(VALIDATE, new_callable=AsyncMock, side_effect=side_effect):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**USER_INPUT, "api_key": "wrong"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_outside_netherlands(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "latitude": 48.85, "longitude": 2.35}
    )
    assert result["errors"] == {"base": "outside_netherlands"}


async def test_duplicate(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch(VALIDATE, new_callable=AsyncMock, return_value="x.json"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "new-key"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["api_key"] == "new-key"


async def test_options(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 10, "language": "en"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {"scan_interval": 10, "language": "en"}


async def test_error_detail_is_shown(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        VALIDATE,
        new_callable=AsyncMock,
        side_effect=KnmiApiError("ClientConnectorDNSError: no host"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["errors"] == {"base": "cannot_connect"}
    assert result["description_placeholders"] == {
        "error_detail": "ClientConnectorDNSError: no host"
    }

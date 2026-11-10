"""Diagnostics support for KNMI Waarschuwingen."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY
from .coordinator import KnmiConfigEntry

TO_REDACT = {CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KnmiConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "filename": data.filename if data else None,
        "generated_at": data.snapshot.generated_at.isoformat()
        if data and data.snapshot.generated_at
        else None,
        "parts_nationwide": [p.as_dict() for p in data.snapshot.parts] if data else [],
        "parts_at_location": [p.as_dict() for p in coordinator.parts_for_location()],
    }

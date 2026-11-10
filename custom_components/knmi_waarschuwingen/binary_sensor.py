"""Binary sensors for KNMI Waarschuwingen."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KnmiConfigEntry, KnmiCoordinator
from .entity import KnmiEntity, top_part_attributes
from .parser import WarningPart, sort_parts

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KnmiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KnmiWarningBinarySensor(coordinator, "warning_active"),
            KnmiWarningBinarySensor(coordinator, "warning_upcoming"),
            KnmiWarningBinarySensor(coordinator, "potentially_dangerous_weather"),
        ]
    )


class KnmiWarningBinarySensor(KnmiEntity, BinarySensorEntity):
    """On when there is a (current / upcoming / potential) warning here."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator: KnmiCoordinator, key: str) -> None:
        """Initialise."""
        super().__init__(coordinator, key)
        self._key = key

    def _selected(self) -> list[WarningPart]:
        if self._key == "warning_active":
            parts = self._current_warnings()
        elif self._key == "warning_upcoming":
            parts = self._upcoming_warnings()
        else:
            parts = [p for p in self._parts() if p.is_potentially_dangerous_weather]
        return sort_parts(parts)

    @property
    def is_on(self) -> bool:
        """Return True when something applies to the location."""
        return bool(self._selected())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the most important part plus the full list."""
        parts = self._selected()
        return {
            **top_part_attributes(parts[0] if parts else None),
            "count": len(parts),
            "warnings": [p.as_dict() for p in parts],
        }

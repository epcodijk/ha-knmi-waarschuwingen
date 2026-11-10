"""Base entity for KNMI Waarschuwingen."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, DOMAIN, KNMI_WARNINGS_URL
from .coordinator import KnmiCoordinator
from .parser import WarningPart


class KnmiEntity(CoordinatorEntity[KnmiCoordinator]):
    """Common base for all entities of a location."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    # Texts can be long; keep them out of the recorder database.
    _unrecorded_attributes = frozenset(
        {"warnings", "description", "detailed_description", "impact", "instruction"}
    )

    def __init__(self, coordinator: KnmiCoordinator, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"KNMI {coordinator.location_name}",
            manufacturer="Onofficieel (data: KNMI)",
            model="Weerwaarschuwingen",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=KNMI_WARNINGS_URL,
        )

    @property
    def _now(self) -> datetime:
        return dt_util.utcnow()

    def _parts(self) -> list[WarningPart]:
        """All non-expired parts (warnings and PDW) at the location."""
        return self.coordinator.parts_for_location(self._now)

    def _warnings(self) -> list[WarningPart]:
        return [p for p in self._parts() if p.is_warning]

    def _current_warnings(self) -> list[WarningPart]:
        now = self._now
        return [p for p in self._warnings() if p.is_current(now)]

    def _upcoming_warnings(self) -> list[WarningPart]:
        now = self._now
        return [p for p in self._warnings() if p.is_upcoming(now)]


def top_part_attributes(part: WarningPart | None) -> dict[str, Any]:
    """Flat attributes of the most important part (MeteoAlarm-compatible-ish)."""
    if part is None:
        return {}
    data = part.as_dict()
    return {
        "phenomenon": data["phenomenon"],
        "color": data["color"],
        "severity": data["severity"],
        "headline": data["headline"],
        "description": data["description"],
        "impact": data["impact"],
        "instruction": data["instruction"],
        "area_description": data["area_description"],
        "onset": data["onset"],
        # 'effective' kept for templates written for the MeteoAlarm integration.
        "effective": data["onset"],
        "expires": data["expires"],
        "probability": data["probability"],
        "certainty": data["certainty"],
    }

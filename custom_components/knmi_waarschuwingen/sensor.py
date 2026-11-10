"""Sensors for KNMI Waarschuwingen."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COLORS
from .coordinator import KnmiConfigEntry, KnmiCoordinator
from .entity import KnmiEntity, top_part_attributes
from .parser import highest_color, sort_parts

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KnmiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KnmiCurrentColorSensor(coordinator),
            KnmiMaxColorSensor(coordinator),
            KnmiNextWarningSensor(coordinator),
            KnmiLastUpdateSensor(coordinator),
        ]
    )


class KnmiCurrentColorSensor(KnmiEntity, SensorEntity):
    """Highest colour code currently in effect at the location."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(COLORS)

    def __init__(self, coordinator: KnmiCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "color")

    @property
    def native_value(self) -> str:
        """Return the colour."""
        return highest_color(self._current_warnings())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of the current warnings."""
        parts = sort_parts(self._current_warnings())
        return {
            **top_part_attributes(parts[0] if parts else None),
            "count": len(parts),
            "warnings": [p.as_dict() for p in parts],
        }


class KnmiMaxColorSensor(KnmiEntity, SensorEntity):
    """Highest colour code at the location within the published period (48h)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(COLORS)

    def __init__(self, coordinator: KnmiCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "max_color")

    @property
    def native_value(self) -> str:
        """Return the colour."""
        return highest_color(self._warnings())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of all current and upcoming warnings."""
        parts = sort_parts(self._warnings())
        return {
            **top_part_attributes(parts[0] if parts else None),
            "count": len(parts),
            "warnings": [p.as_dict() for p in parts],
        }


class KnmiNextWarningSensor(KnmiEntity, SensorEntity):
    """Start time of the next upcoming warning at the location."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: KnmiCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "next_warning")

    @property
    def native_value(self) -> datetime | None:
        """Return the onset of the next warning."""
        onsets = [p.onset for p in self._upcoming_warnings() if p.onset]
        return min(onsets) if onsets else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the details of the next warning."""
        upcoming = sorted(
            (p for p in self._upcoming_warnings() if p.onset),
            key=lambda p: (p.onset, -p.rank),
        )
        return top_part_attributes(upcoming[0] if upcoming else None)


class KnmiLastUpdateSensor(KnmiEntity, SensorEntity):
    """Time the KNMI snapshot was generated."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: KnmiCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "last_update")

    @property
    def native_value(self) -> datetime | None:
        """Return when KNMI generated the snapshot."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.snapshot.generated_at

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return technical details."""
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "filename": data.filename,
            "publication_type": data.snapshot.publication_type,
            "snapshot_uuid": data.snapshot.snapshot_uuid,
            "last_fetched": data.last_fetched.isoformat(),
            "warning_parts_nationwide": len(data.snapshot.parts),
        }

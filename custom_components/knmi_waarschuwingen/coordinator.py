"""Data update coordinator for KNMI Waarschuwingen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import KnmiApiError, KnmiAuthError, KnmiWarningsClient
from .const import (
    ANONYMOUS_API_KEY,
    CONF_API_KEY,
    CONF_LANGUAGE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NEW_WARNING,
)
from .parser import Snapshot, WarningPart, parse_snapshot

_LOGGER = logging.getLogger(__name__)

type KnmiConfigEntry = ConfigEntry[KnmiCoordinator]


@dataclass(slots=True)
class KnmiData:
    """Data held by the coordinator."""

    filename: str | None
    snapshot: Snapshot
    last_fetched: datetime


class KnmiCoordinator(DataUpdateCoordinator[KnmiData]):
    """Poll the KNMI Data Platform for new warning snapshots."""

    config_entry: KnmiConfigEntry

    def __init__(self, hass: HomeAssistant, entry: KnmiConfigEntry) -> None:
        """Initialise the coordinator."""
        minutes = entry.options.get(CONF_SCAN_INTERVAL)
        interval = timedelta(minutes=int(minutes)) if minutes else DEFAULT_SCAN_INTERVAL
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=interval,
        )
        self.client = KnmiWarningsClient(
            async_get_clientsession(hass),
            entry.data.get(CONF_API_KEY) or ANONYMOUS_API_KEY,
        )
        self.language: str = entry.options.get(
            CONF_LANGUAGE, "nl" if hass.config.language.startswith("nl") else "en"
        )
        self._raw: dict | None = None
        self._seen: set[tuple[str, str]] | None = None
        self._unsub_boundary: CALLBACK_TYPE | None = None

    # ------------------------------------------------------------------ location

    @property
    def location_name(self) -> str:
        """Return the configured location name."""
        return self.config_entry.data.get(CONF_NAME) or self.config_entry.title

    @property
    def latitude(self) -> float:
        """Return the configured latitude."""
        return float(self.config_entry.data[CONF_LATITUDE])

    @property
    def longitude(self) -> float:
        """Return the configured longitude."""
        return float(self.config_entry.data[CONF_LONGITUDE])

    def parts_for_location(self, now: datetime | None = None) -> list[WarningPart]:
        """Return all non-expired parts that cover the configured location."""
        if self.data is None:
            return []
        return self.data.snapshot.for_location(
            self.latitude, self.longitude, now or dt_util.utcnow()
        )

    # -------------------------------------------------------------------- update

    async def _async_update_data(self) -> KnmiData:
        try:
            filename = await self.client.async_get_latest_filename()
            previous = self.data.filename if self.data else None
            if filename and (filename != previous or self._raw is None):
                self._raw = await self.client.async_download(filename)
                _LOGGER.debug("Downloaded new KNMI snapshot %s", filename)
        except KnmiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KnmiApiError as err:
            raise UpdateFailed(str(err)) from err

        snapshot = parse_snapshot(self._raw or {}, self.language)
        data = KnmiData(
            filename=filename, snapshot=snapshot, last_fetched=dt_util.utcnow()
        )
        self._fire_new_warning_events(data)
        return data

    @callback
    def _fire_new_warning_events(self, data: KnmiData) -> None:
        """Fire an event for each new/updated warning part at our location."""
        now = dt_util.utcnow()
        parts = data.snapshot.for_location(self.latitude, self.longitude, now)
        keys = {part.key for part in parts}
        if self._seen is None:
            # First run after start-up: don't spam events for existing warnings.
            self._seen = keys
            return
        for part in parts:
            if part.key in self._seen:
                continue
            self.hass.bus.async_fire(
                EVENT_NEW_WARNING,
                {
                    "config_entry_id": self.config_entry.entry_id,
                    "location": self.location_name,
                    **part.as_dict(),
                },
            )
        self._seen = keys

    # ------------------------------------------------------------ time handling

    @callback
    def schedule_boundary_update(self) -> None:
        """Refresh entity states exactly when a warning starts or ends.

        States depend on the current time (a code yellow from 14:00 is
        'upcoming' at 13:59 and 'current' at 14:00), so we wake up the
        listeners at the next onset/expiry instead of waiting for the next poll.
        """
        if self._unsub_boundary:
            self._unsub_boundary()
            self._unsub_boundary = None
        now = dt_util.utcnow()
        moments = [
            moment
            for part in self.parts_for_location(now)
            for moment in (part.onset, part.expires)
            if moment is not None and moment > now
        ]
        if not moments:
            return

        @callback
        def _boundary(_now: datetime) -> None:
            self._unsub_boundary = None
            self.async_update_listeners()

        self._unsub_boundary = async_track_point_in_utc_time(
            self.hass, _boundary, min(moments) + timedelta(seconds=1)
        )

    @callback
    def async_update_listeners(self) -> None:
        """Update listeners and (re)schedule the boundary timer."""
        super().async_update_listeners()
        if self.data is not None:
            self.schedule_boundary_update()

    async def async_shutdown(self) -> None:
        """Cancel timers on unload."""
        if self._unsub_boundary:
            self._unsub_boundary()
            self._unsub_boundary = None
        await super().async_shutdown()

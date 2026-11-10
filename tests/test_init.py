"""Integration tests: setup, entity states, time boundaries and events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.knmi_waarschuwingen.api import KnmiApiError, KnmiAuthError
from custom_components.knmi_waarschuwingen.const import EVENT_NEW_WARNING

from .conftest import load_snapshot

NOON = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

COLOR = "sensor.knmi_zwolle_color_code"
MAX_COLOR = "sensor.knmi_zwolle_highest_color_code_48h"
NEXT = "sensor.knmi_zwolle_next_warning"
ACTIVE = "binary_sensor.knmi_zwolle_warning_active"
UPCOMING = "binary_sensor.knmi_zwolle_warning_upcoming"
PDW = "binary_sensor.knmi_zwolle_potentially_dangerous_weather"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_states_at_noon(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_client,
    config_entry: MockConfigEntry,
) -> None:
    freezer.move_to(NOON)
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    color = hass.states.get(COLOR)
    assert color.state == "yellow"
    assert color.attributes["phenomenon"] == "Fog"
    assert color.attributes["effective"] == "2026-11-10T06:00:00+00:00"
    assert color.attributes["headline"] == "Code geel: dichte mist"
    assert color.attributes["count"] == 1

    assert hass.states.get(MAX_COLOR).state == "orange"
    assert hass.states.get(MAX_COLOR).attributes["count"] == 2
    assert hass.states.get(ACTIVE).state == "on"
    assert hass.states.get(UPCOMING).state == "on"
    assert hass.states.get(UPCOMING).attributes["phenomenon"] == "Wind"
    assert hass.states.get(PDW).state == "on"
    assert hass.states.get(NEXT).state == "2026-11-11T02:00:00+00:00"


async def test_boundaries_update_states(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_client,
    config_entry: MockConfigEntry,
) -> None:
    """States change at onset/expiry without a new KNMI snapshot."""
    freezer.move_to(NOON)
    await _setup(hass, config_entry)

    # Fog expires at 14:00.
    freezer.move_to(datetime(2026, 11, 10, 14, 0, 2, tzinfo=UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(COLOR).state == "green"
    assert hass.states.get(ACTIVE).state == "off"
    assert hass.states.get(UPCOMING).state == "on"

    # Wind starts 02:00 the next day.
    freezer.move_to(datetime(2026, 11, 11, 2, 0, 2, tzinfo=UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(COLOR).state == "orange"
    assert hass.states.get(ACTIVE).state == "on"
    assert hass.states.get(UPCOMING).state == "off"
    assert hass.states.get(NEXT).state == "unknown"


async def test_download_only_on_new_file(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_client,
    config_entry: MockConfigEntry,
) -> None:
    freezer.move_to(NOON)
    await _setup(hass, config_entry)
    assert mock_client["download"].await_count == 1

    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client["latest"].await_count == 2
    assert mock_client["download"].await_count == 1


async def test_event_on_new_warning(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_client,
    config_entry: MockConfigEntry,
) -> None:
    freezer.move_to(NOON)
    await _setup(hass, config_entry)
    events = async_capture_events(hass, EVENT_NEW_WARNING)

    new = load_snapshot()
    new["warnings"][1]["parts"][0]["version_id"] = "2"  # wind re-issued
    new["warnings"][1]["parts"][0]["color"] = "red"
    mock_client["latest"].return_value = "public_warnings_new.json"
    mock_client["download"].return_value = new

    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["phenomenon"] == "Wind"
    assert events[0].data["color"] == "red"
    assert events[0].data["location"] == "Zwolle"
    assert hass.states.get(MAX_COLOR).state == "red"


async def test_location_outside_areas(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_client,
    config_entry: MockConfigEntry,
) -> None:
    freezer.move_to(NOON)
    entry = MockConfigEntry(
        domain=config_entry.domain,
        title="Amsterdam",
        data={
            **config_entry.data,
            "name": "Amsterdam",
            "latitude": 52.3676,
            "longitude": 4.9041,
        },
    )
    await _setup(hass, entry)
    assert hass.states.get("sensor.knmi_amsterdam_color_code").state == "green"
    assert hass.states.get("binary_sensor.knmi_amsterdam_warning_active").state == "off"
    assert (
        hass.states.get(
            "binary_sensor.knmi_amsterdam_potentially_dangerous_weather"
        ).state
        == "on"
    )


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (KnmiApiError("down"), ConfigEntryState.SETUP_RETRY),
        (KnmiAuthError("bad key"), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_setup_errors(
    hass: HomeAssistant,
    mock_client,
    config_entry: MockConfigEntry,
    error: Exception,
    state: ConfigEntryState,
) -> None:
    mock_client["latest"].side_effect = error
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is state


async def test_unload(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_client,
    config_entry: MockConfigEntry,
) -> None:
    freezer.move_to(NOON)
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert dt_util.utcnow() == NOON


async def test_dutch_entity_ids_and_diagnostics(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_client,
    config_entry: MockConfigEntry,
) -> None:
    """Dutch installs get Dutch entity ids (as documented in the README)."""
    from custom_components.knmi_waarschuwingen.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    hass.config.language = "nl"
    freezer.move_to(NOON)
    await _setup(hass, config_entry)
    for entity_id in (
        "sensor.knmi_zwolle_kleurcode",
        "sensor.knmi_zwolle_hoogste_kleurcode_48_uur",
        "sensor.knmi_zwolle_volgende_waarschuwing",
        "sensor.knmi_zwolle_knmi_update",
        "binary_sensor.knmi_zwolle_waarschuwing_actief",
        "binary_sensor.knmi_zwolle_waarschuwing_verwacht",
        "binary_sensor.knmi_zwolle_mogelijk_gevaarlijk_weer",
    ):
        assert hass.states.get(entity_id) is not None, entity_id
    assert hass.states.get("sensor.knmi_zwolle_knmi_update").state == (
        "2026-11-10T11:30:00+00:00"
    )

    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diag["entry"]["data"]["latitude"] == "**REDACTED**"
    assert len(diag["parts_at_location"]) == 3

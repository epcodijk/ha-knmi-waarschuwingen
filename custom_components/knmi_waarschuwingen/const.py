"""Constants for the KNMI Waarschuwingen integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "knmi_waarschuwingen"

API_BASE_URL: Final = "https://api.dataplatform.knmi.nl/open-data/v1"
DATASET_NAME: Final = "KNMI-public-weather-warnings"
DATASET_VERSION: Final = "1.0"


CONF_API_KEY: Final = "api_key"
CONF_LANGUAGE: Final = "language"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=5)
MIN_SCAN_INTERVAL_MINUTES: Final = 2
MAX_SCAN_INTERVAL_MINUTES: Final = 60

LANGUAGES: Final = ("nl", "en")

COLOR_GREEN: Final = "green"
COLOR_YELLOW: Final = "yellow"
COLOR_ORANGE: Final = "orange"
COLOR_RED: Final = "red"
COLORS: Final = (COLOR_GREEN, COLOR_YELLOW, COLOR_ORANGE, COLOR_RED)
COLOR_RANK: Final = {color: rank for rank, color in enumerate(COLORS)}

SEVERITY_TO_COLOR: Final = {
    "Moderate": COLOR_YELLOW,
    "Severe": COLOR_ORANGE,
    "Extreme": COLOR_RED,
}

WARNING_TYPE_WARNING: Final = "warning"
WARNING_TYPE_PDW: Final = "potentially-dangerous-weather"

EVENT_NEW_WARNING: Final = f"{DOMAIN}_new_warning"

ATTRIBUTION: Final = (
    "Data: © KNMI (CC BY 4.0), bewerkt. Onofficiële integratie, geen KNMI-product."
)
KNMI_API_KEY_URL: Final = "https://developer.dataplatform.knmi.nl/"
KNMI_WARNINGS_URL: Final = "https://www.knmi.nl/nederland-nu/weer/waarschuwingen"

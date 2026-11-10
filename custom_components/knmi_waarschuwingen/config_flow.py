"""Config flow for KNMI Waarschuwingen."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import KnmiApiError, KnmiAuthError, KnmiWarningsClient
from .const import (
    CONF_API_KEY,
    CONF_LANGUAGE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    KNMI_API_KEY_URL,
    LANGUAGES,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

# Rough bounding box of the warning domain (from the KNMI dataset metadata).
NL_LAT = (50.6, 53.7)
NL_LON = (3.2, 7.4)


async def _validate_key(hass: HomeAssistant, api_key: str) -> tuple[str | None, str]:
    """Return (error key, detail); error key is None when the API key works."""
    client = KnmiWarningsClient(async_get_clientsession(hass), api_key)
    try:
        await client.async_get_latest_filename()
    except KnmiAuthError as err:
        _LOGGER.warning("KNMI rejected the API key: %s", err)
        return "invalid_auth", str(err)
    except KnmiApiError as err:
        _LOGGER.warning("Could not reach the KNMI Open Data API: %s", err)
        return "cannot_connect", str(err)
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("Unexpected error validating KNMI API key")
        return "unknown", f"{type(err).__name__}: {err}"
    return None, ""


class KnmiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a location and (optionally) an API key."""
        errors: dict[str, str] = {}
        detail = ""

        if user_input is not None:
            lat = float(user_input[CONF_LATITUDE])
            lon = float(user_input[CONF_LONGITUDE])
            api_key = (user_input.get(CONF_API_KEY) or "").strip()

            if not (NL_LAT[0] <= lat <= NL_LAT[1] and NL_LON[0] <= lon <= NL_LON[1]):
                errors["base"] = "outside_netherlands"
            else:
                await self.async_set_unique_id(f"{lat:.4f}_{lon:.4f}")
                self._abort_if_unique_id_configured()
                error, detail = await _validate_key(self.hass, api_key)
                if error:
                    errors["base"] = error
                else:
                    return self.async_create_entry(
                        title=user_input[CONF_NAME],
                        data={
                            CONF_NAME: user_input[CONF_NAME],
                            CONF_LATITUDE: lat,
                            CONF_LONGITUDE: lon,
                            CONF_API_KEY: api_key,
                        },
                    )

        defaults = user_input or {
            CONF_NAME: self.hass.config.location_name or "Thuis",
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_API_KEY: "",
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=defaults[CONF_NAME]): str,
                vol.Required(
                    CONF_LATITUDE, default=defaults[CONF_LATITUDE]
                ): cv.latitude,
                vol.Required(
                    CONF_LONGITUDE, default=defaults[CONF_LONGITUDE]
                ): cv.longitude,
                vol.Required(
                    CONF_API_KEY,
                    description={"suggested_value": defaults.get(CONF_API_KEY)},
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "error_detail": detail,
                "key_url": KNMI_API_KEY_URL,
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication when the API key is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key."""
        errors: dict[str, str] = {}
        detail = ""
        if user_input is not None:
            api_key = (user_input.get(CONF_API_KEY) or "").strip()
            error, detail = await _validate_key(self.hass, api_key)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_API_KEY: api_key}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
            description_placeholders={
                "error_detail": detail,
                "key_url": KNMI_API_KEY_URL,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> KnmiOptionsFlow:
        """Return the options flow."""
        return KnmiOptionsFlow()


class KnmiOptionsFlow(OptionsFlowWithReload):
    """Options: polling interval and text language."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        default_lang = "nl" if self.hass.config.language.startswith("nl") else "en"
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(
                        CONF_SCAN_INTERVAL,
                        int(DEFAULT_SCAN_INTERVAL.total_seconds() // 60),
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                        step=1,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_LANGUAGE, default=options.get(CONF_LANGUAGE, default_lang)
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(LANGUAGES),
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="language",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

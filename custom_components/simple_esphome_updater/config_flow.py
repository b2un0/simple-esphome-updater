"""Config flow."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from aiohttp import ClientError, ClientResponseError
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import create_api
from .const import CONF_ONLY_ONLINE, DOMAIN, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _normalize(url: str) -> str:
    url = url.strip().rstrip("/")
    return url if "://" in url else f"http://{url}"


class UpdaterOptionsFlow(OptionsFlow):
    """Configure device admission."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the online-only filter."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ONLY_ONLINE,
                        default=self.config_entry.options.get(CONF_ONLY_ONLINE, False),
                    ): bool,
                }
            ),
        )


class SimpleEsphomeUpdaterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for dashboard URL, user and password."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return editable options."""
        return UpdaterOptionsFlow()

    async def _validate(self, data: Mapping[str, Any]) -> str | None:
        """Return an error key or None."""
        api = create_api(
            self.hass, data[CONF_URL], data.get(CONF_USERNAME), data.get(CONF_PASSWORD)
        )
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                await api.get_devices()
        except ClientResponseError as err:
            return "invalid_auth" if err.status in (401, 403) else "cannot_connect"
        except (ClientError, TimeoutError):
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error")
            return "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**user_input, CONF_URL: _normalize(user_input[CONF_URL])}
            await self.async_set_unique_id(data[CONF_URL].lower())
            self._abort_if_unique_id_configured()
            if error := await self._validate(data):
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=data[CONF_URL],
                    options={CONF_ONLY_ONLINE: data.pop(CONF_ONLY_ONLINE, False)},
                    data=data,
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_URL): str,
                        vol.Optional(CONF_ONLY_ONLINE, default=False): bool,
                        vol.Optional(CONF_USERNAME): str,
                        vol.Optional(CONF_PASSWORD): _PASSWORD,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, **user_input}
            if error := await self._validate(data):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Optional(CONF_USERNAME): str,
                        vol.Optional(CONF_PASSWORD): _PASSWORD,
                    }
                ),
                {CONF_USERNAME: entry.data.get(CONF_USERNAME)},
            ),
            errors=errors,
        )

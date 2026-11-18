"""Simple EspHome Updater: compile / flash / update buttons for ESPHome devices."""

from __future__ import annotations

from aiohttp import BasicAuth
from esphome_dashboard_api import ESPHomeDashboardAPI
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .coordinator import UpdaterCoordinator

PLATFORMS = [Platform.BUTTON, Platform.UPDATE]

type UpdaterConfigEntry = ConfigEntry[UpdaterCoordinator]


def create_api(
    hass: HomeAssistant, url: str, username: str | None, password: str | None
) -> ESPHomeDashboardAPI:
    """Create a dashboard client with its own (optionally authenticated) session."""
    headers = {}
    if username or password:
        headers["Authorization"] = BasicAuth(username or "", password or "").encode()
    session = async_create_clientsession(hass, headers=headers)
    return ESPHomeDashboardAPI(url, session)


async def async_setup_entry(hass: HomeAssistant, entry: UpdaterConfigEntry) -> bool:
    """Set up from a config entry."""
    api = create_api(
        hass,
        entry.data[CONF_URL],
        entry.data.get(CONF_USERNAME),
        entry.data.get(CONF_PASSWORD),
    )
    coordinator = UpdaterCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UpdaterConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

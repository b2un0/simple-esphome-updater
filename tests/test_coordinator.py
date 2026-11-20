"""Device admission through real Home Assistant coordinators."""

from unittest.mock import AsyncMock, Mock

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.simple_esphome_updater.const import DOMAIN
from custom_components.simple_esphome_updater.coordinator import UpdaterCoordinator


def make_coordinator(hass, *, options=None, entry=None):
    """Create coordinator backed by a mocked external dashboard only."""
    if entry is None:
        entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {})
        entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    api = Mock(url="http://example.com:6052")
    api.get_devices = AsyncMock()
    return UpdaterCoordinator(hass, entry, api)


def devices(*states):
    """Dashboard response with deterministic placeholder names."""
    return {
        "configured": [
            {"name": f"device-{i}", **({"state": state} if state is not None else {})}
            for i, state in enumerate(states)
        ]
    }


async def test_only_explicit_online_admitted(hass):
    coordinator = make_coordinator(hass, options={"only_online": True})
    coordinator.api.get_devices.return_value = devices(
        "online", "offline", None, "unknown"
    )
    await coordinator.async_config_entry_first_refresh()
    assert set(coordinator.data) == {"device-0"}


async def test_online_then_offline_retained(hass):
    coordinator = make_coordinator(hass, options={"only_online": True})
    coordinator.api.get_devices.return_value = devices("online", "offline")
    await coordinator.async_config_entry_first_refresh()
    coordinator.api.get_devices.return_value = devices("offline", "online")
    await coordinator.async_refresh()
    assert set(coordinator.data) == {"device-0", "device-1"}
    assert coordinator.data["device-0"]["state"] == "offline"


async def test_admission_survives_new_coordinator(hass, hass_storage):
    """Store persists proven-online names even when filter was disabled."""
    coordinator = make_coordinator(hass)
    coordinator.api.get_devices.return_value = devices("online", "offline", None)
    await coordinator.async_config_entry_first_refresh()
    assert set(coordinator.data) == {"device-0", "device-1", "device-2"}
    entry = coordinator.config_entry
    await coordinator.async_shutdown()
    hass.config_entries.async_update_entry(entry, options={"only_online": True})
    reloaded = make_coordinator(hass, entry=entry)
    reloaded.api.get_devices.return_value = devices("offline", "offline", None)
    await reloaded.async_config_entry_first_refresh()
    assert set(reloaded.data) == {"device-0"}
    assert hass_storage[f"{DOMAIN}.{entry.entry_id}.admitted"]["data"] == {
        "names": ["device-0"]
    }

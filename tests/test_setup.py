"""Full setup, platforms, reload and registry isolation."""

from unittest.mock import AsyncMock, Mock, patch

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.simple_esphome_updater.const import DOMAIN


async def test_remove_entry_removes_admission_store(hass, hass_storage):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    key = f"{DOMAIN}.{entry.entry_id}.admitted"
    await Store(hass, 1, key).async_save({"names": ["my-device"]})
    await hass.config_entries.async_remove(entry.entry_id)
    assert key not in hass_storage


async def test_enable_cleans_unproven_devices_only(hass):
    """Configure reload removes unproven entities/devices, not linked peers."""
    entry = MockConfigEntry(domain=DOMAIN, data={"url": "http://example.com:6052"})
    entry.add_to_hass(hass)
    peer = MockConfigEntry(domain="esphome", data={})
    peer.add_to_hass(hass)
    api = Mock(url="http://example.com:6052")
    api.get_devices = AsyncMock(
        return_value={
            "configured": [
                {
                    "name": "real-device",
                    "state": "online",
                    "address": "example.com",
                    "mac_address": "00:11:22:33:44:55",
                },
                {
                    "name": "blueprint",
                    "state": "offline",
                    "mac_address": "00:11:22:33:44:66",
                },
            ]
        }
    )
    with patch("custom_components.simple_esphome_updater.create_api", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        own = er.async_entries_for_config_entry(registry, entry.entry_id)
        assert len(own) == 6
        blueprint = next(e for e in own if "_blueprint_" in e.unique_id)
        real_device = next(e.device_id for e in own if "_real-device_" in e.unique_id)
        devices = dr.async_get(hass)
        peer_device = devices.async_get_or_create(
            config_entry_id=peer.entry_id,
            identifiers={("esphome", "placeholder")},
            connections={(dr.CONNECTION_NETWORK_MAC, "00:11:22:33:44:66")},
        )
        peer_entity = registry.async_get_or_create(
            "sensor",
            "esphome",
            "placeholder",
            config_entry=peer,
            device_id=peer_device.id,
        )
        api.get_devices.return_value["configured"][0]["state"] = "offline"
        result = await hass.config_entries.options.async_init(entry.entry_id)
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"only_online": True}
        )
        await hass.async_block_till_done()
        assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 3
        assert devices.async_get(blueprint.device_id) is None
        assert devices.async_get(real_device) is not None
        assert devices.async_get(peer_device.id) is not None
        assert registry.async_get(peer_entity.entity_id) is not None
        own = er.async_entries_for_config_entry(registry, entry.entry_id)
        assert all("_real-device_" in e.unique_id for e in own)
        for entity in own:
            state = hass.states.get(entity.entity_id)
            assert state is not None
            assert state.state == (
                "unknown" if entity.unique_id.endswith("_compile") else "unavailable"
            )
        # Turning the filter off recreates excluded devices and all their entities.
        result = await hass.config_entries.options.async_init(entry.entry_id)
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"only_online": False}
        )
        await hass.async_block_till_done()
        assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 6


async def test_filtered_platforms_add_only_online_devices(hass):
    """All platforms filter initial discovery and admit devices on later polls."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"url": "http://example.com:6052"},
        options={"only_online": True},
    )
    entry.add_to_hass(hass)
    api = Mock(url="http://example.com:6052")
    api.get_devices = AsyncMock(
        return_value={
            "configured": [
                {"name": "blueprint", "state": "offline"},
                {"name": "unknown-device"},
            ]
        }
    )
    with patch("custom_components.simple_esphome_updater.create_api", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entities = er.async_get(hass)
        devices = dr.async_get(hass)
        assert er.async_entries_for_config_entry(entities, entry.entry_id) == []
        assert dr.async_entries_for_config_entry(devices, entry.entry_id) == []
        api.get_devices.return_value["configured"][1]["state"] = "online"
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        own = er.async_entries_for_config_entry(entities, entry.entry_id)
        assert len(own) == 3
        assert {e.domain for e in own} == {"button", "update"}
        assert all("_unknown-device_" in e.unique_id for e in own)
        assert len(dr.async_entries_for_config_entry(devices, entry.entry_id)) == 1
        # HA reload creates fresh coordinator, retaining proven device while offline.
        api.get_devices.return_value["configured"][1]["state"] = "offline"
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert len(er.async_entries_for_config_entry(entities, entry.entry_id)) == 3
        assert set(entry.runtime_data.data) == {"unknown-device"}

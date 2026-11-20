"""Setup and options flow behaviour."""

from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.simple_esphome_updater.const import DOMAIN


async def test_setup_online_option(hass):
    """Setup exposes false default and stores chosen filter in options."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert (
        result["data_schema"]({"url": "http://example.com:6052"})["only_online"]
        is False
    )
    with (
        patch("custom_components.simple_esphome_updater.config_flow.create_api") as api,
        patch(
            "custom_components.simple_esphome_updater.async_setup_entry",
            return_value=True,
        ),
    ):
        api.return_value.get_devices = AsyncMock(return_value={"configured": []})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"url": "http://example.com:6052", "only_online": True},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {"only_online": True}
    assert "only_online" not in result["data"]


async def test_options_edit(hass):
    """Old entries default false; Configure can enable or disable filter."""
    entry = MockConfigEntry(domain=DOMAIN, data={"url": "http://example.com:6052"})
    entry.add_to_hass(hass)
    for enabled in (True, False):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["data_schema"]({})["only_online"] is (not enabled)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"only_online": enabled}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.options == {"only_online": enabled}
        assert entry.data == {"url": "http://example.com:6052"}

"""Buttons: update, flash, compile."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from esphome_dashboard_api import ConfiguredDevice
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import UpdaterConfigEntry
from .const import DOMAIN
from .coordinator import UpdaterCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class UpdaterButtonDescription(ButtonEntityDescription):
    """Button description."""

    upload: bool
    # Extra availability rule on top of "device known and not busy".
    needs: Callable[[ConfiguredDevice], bool] = lambda _dev: True


def _update_available(dev: ConfiguredDevice) -> bool:
    if not dev.get("address"):
        return False
    deployed, latest = dev.get("deployed_version"), dev.get("current_version")
    return bool(
        dev.get("update_available") or (deployed and latest and deployed != latest)
    )


BUTTONS = (
    UpdaterButtonDescription(
        key="update", translation_key="update", upload=True, needs=_update_available
    ),
    UpdaterButtonDescription(
        key="flash",
        translation_key="flash",
        upload=True,
        needs=lambda dev: bool(dev.get("address")),
    ),
    UpdaterButtonDescription(key="compile", translation_key="compile", upload=False),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpdaterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create buttons for every device, including ones that show up later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = set(coordinator.data) - known
        known.update(new)
        async_add_entities(
            UpdaterButton(coordinator, name, desc)
            for name in sorted(new)
            for desc in BUTTONS
        )

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class UpdaterButton(CoordinatorEntity[UpdaterCoordinator], ButtonEntity):
    """One action for one dashboard device."""

    _attr_has_entity_name = True
    entity_description: UpdaterButtonDescription

    def __init__(
        self,
        coordinator: UpdaterCoordinator,
        name: str,
        description: UpdaterButtonDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        self._name = name
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{name}_{description.key}"
        self._attr_device_info = self._device_info(name, entry_id)

    def _device_info(self, name: str, entry_id: str) -> DeviceInfo:
        """Device carries the MAC as connection, so HA links it to the ESPHome one."""
        dev = self.coordinator.data[name]
        macs = {
            (dr.CONNECTION_NETWORK_MAC, format_mac(mac))
            for mac in (dev.get("mac_address"), dev.get("ethernet_mac"))
            if mac
        }
        return DeviceInfo(
            connections=macs,
            identifiers={(DOMAIN, f"{entry_id}_{name}")},
            name=dev.get("friendly_name") or name,
            manufacturer="ESPHome",
            configuration_url=self.coordinator.api.url,
        )

    @property
    def _device(self) -> ConfiguredDevice | None:
        return self.coordinator.data.get(self._name)

    @property
    def available(self) -> bool:
        """Unavailable while busy, gone from the dashboard, or not applicable."""
        dev = self._device
        return (
            super().available
            and dev is not None
            and self._name not in self.coordinator.active
            and self.entity_description.needs(dev)
        )

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Show versions for context."""
        dev = self._device or {}
        return {
            "deployed_version": dev.get("deployed_version"),
            "available_version": dev.get("current_version"),
        }

    async def async_press(self) -> None:
        """Start the job in the background; progress/failure via notification."""
        self.coordinator.start_job(self._name, upload=self.entity_description.upload)

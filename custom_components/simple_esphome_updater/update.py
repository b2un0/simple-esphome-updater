"""Update entity: installed vs. available ESPHome version, with progress."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import UpdaterConfigEntry
from .coordinator import UpdaterCoordinator, device_info, is_reachable

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpdaterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create an update entity for every device, including ones that show up later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = set(coordinator.data) - known
        known.update(new)
        async_add_entities(UpdaterUpdate(coordinator, name) for name in sorted(new))

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class UpdaterUpdate(CoordinatorEntity[UpdaterCoordinator], UpdateEntity):
    """ESPHome firmware update of one dashboard device."""

    _attr_has_entity_name = True
    _attr_translation_key = "firmware"
    _attr_title = "ESPHome"
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )

    def __init__(self, coordinator: UpdaterCoordinator, name: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{name}_update"
        self._attr_device_info = device_info(coordinator, name)

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._name) or {}

    @property
    def available(self) -> bool:
        """Unavailable if gone from the dashboard or reported offline."""
        return (
            super().available
            and self._name in self.coordinator.data
            and is_reachable(self._device)
        )

    @property
    def installed_version(self) -> str | None:
        """Version running on the device."""
        return self._device.get("deployed_version")

    @property
    def latest_version(self) -> str | None:
        """Version the dashboard would build."""
        return self._device.get("current_version")

    @property
    def in_progress(self) -> bool:
        """Job running for this device."""
        return self._name in self.coordinator.active

    @property
    def update_percentage(self) -> int | None:
        """Combined compile + upload progress, None until a percentage is seen."""
        return self.coordinator.progress.get(self._name)

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Compile and upload in the background."""
        if not self._device.get("address"):
            raise ValueError("Device has no address, cannot upload")
        self.coordinator.start_job(self._name, upload=True)

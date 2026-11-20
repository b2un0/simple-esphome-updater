"""Coordinator: polls the dashboard and runs compile/upload jobs."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from datetime import timedelta
from typing import TYPE_CHECKING

from aiohttp import ClientError, ClientResponseError
from esphome_dashboard_api import ConfiguredDevice, ESPHomeDashboardAPI
from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ONLY_ONLINE,
    DOMAIN,
    LOG_TAIL_LINES,
    REQUEST_TIMEOUT,
    SCAN_INTERVAL_SECONDS,
)

if TYPE_CHECKING:
    from . import UpdaterConfigEntry

_LOGGER = logging.getLogger(__name__)

# The dashboard sends colours either as real escape bytes or as literal "\033".
_ANSI = re.compile(r"(?:\x1b|\\033)\[[0-9;]*m")
# Build: ninja "[ 45%] ..."; OTA: "Uploading: [=====   ] 45%".
_PERCENT = re.compile(r"^(?:\[\s*(\d+)%\]|Uploading:.*?(\d+)%)")


class UpdaterCoordinator(DataUpdateCoordinator[dict[str, ConfiguredDevice]]):
    """Fetch configured devices from the dashboard, serialise build jobs."""

    config_entry: UpdaterConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: UpdaterConfigEntry,
        api: ESPHomeDashboardAPI,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api
        self._admitted: set[str] = set()
        self._admission_store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.admitted")
        self._lock = asyncio.Lock()
        self.active: set[str] = set()
        # 0-100 while a job runs, None if no percentage seen yet.
        self.progress: dict[str, int | None] = {}

    async def _async_setup(self) -> None:
        """Restore names with explicit online evidence before the first poll."""
        if stored := await self._admission_store.async_load():
            self._admitted = set(stored["names"])

    async def _async_update_data(self) -> dict[str, ConfiguredDevice]:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                devices = await self.api.get_devices()
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed from err
            raise UpdateFailed(f"Dashboard error: {err.status}") from err
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Dashboard unreachable: {err}") from err
        newly_online = {
            dev["name"] for dev in devices["configured"] if dev.get("state") == "online"
        } - self._admitted
        if newly_online:
            admitted = self._admitted | newly_online
            await self._admission_store.async_save({"names": sorted(admitted)})
            self._admitted = admitted
        return {
            dev["name"]: dev
            for dev in devices["configured"]
            if not self.config_entry.options.get(CONF_ONLY_ONLINE, False)
            or dev["name"] in self._admitted
        }

    @callback
    def async_remove_unadmitted(self) -> None:
        """Remove only this entry's entities and exclusively owned devices."""
        if not self.config_entry.options.get(CONF_ONLY_ONLINE, False):
            return
        entry_id = self.config_entry.entry_id
        prefix = f"{entry_id}_"
        entities = er.async_get(self.hass)
        for entity in er.async_entries_for_config_entry(entities, entry_id):
            if entity.platform != DOMAIN or not entity.unique_id.startswith(prefix):
                continue
            name, _, action = entity.unique_id[len(prefix) :].rpartition("_")
            if action in {"compile", "flash", "update"} and name not in self._admitted:
                entities.async_remove(entity.entity_id)
        devices = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(devices, entry_id):
            names = {
                identifier[len(prefix) :]
                for domain, identifier in device.identifiers
                if domain == DOMAIN and identifier.startswith(prefix)
            }
            if not names or names & self._admitted:
                continue
            # HA 2026.8+ devices belong to one entry. Never remove linked peers
            # or an entry with entities/identifiers from another integration.
            if (
                device.config_entry_id == entry_id
                and all(domain == DOMAIN for domain, _ in device.identifiers)
                and not er.async_entries_for_device(
                    entities, device.id, include_disabled_entities=True
                )
            ):
                devices.async_remove_device(device.id)

    @callback
    def start_job(self, name: str, *, upload: bool) -> None:
        """Queue a compile (+ upload) job for a device. No-op if one is queued."""
        if name in self.active:
            return
        self.active.add(name)
        self.progress[name] = None
        self.async_update_listeners()
        self.config_entry.async_create_background_task(
            self.hass, self._run(name, upload), f"{DOMAIN}_{name}"
        )

    async def _run(self, name: str, upload: bool) -> None:
        tail: deque[str] = deque(maxlen=LOG_TAIL_LINES)

        # With upload: compile fills 0-50 %, upload 50-100 %.
        phase = {"base": 0, "span": 50 if upload else 100}

        def on_line(line: str) -> None:
            if not (line := _ANSI.sub("", line).strip()):
                return
            tail.append(line)
            if m := _PERCENT.match(line):
                pct = int(m[1] or m[2])
                self.progress[name] = phase["base"] + pct * phase["span"] // 100
                self.async_update_listeners()

        action = "Flash" if upload else "Compile"
        try:
            async with self._lock:
                device = self.data[name]
                config = device["configuration"]
                if not await self.api.compile(config, on_line):
                    raise RuntimeError("compile failed")
                phase["base"] = 50
                if upload:
                    self.progress[name] = 50
                    self.async_update_listeners()
                if upload and not await self.api.upload(
                    config, device["address"], on_line
                ):
                    raise RuntimeError("upload failed")
        except Exception as err:  # noqa: BLE001 - report every failure to the user
            _LOGGER.error("%s of %s failed: %s", action, name, err)
            persistent_notification.async_create(
                self.hass,
                f"{action} of `{name}` failed: {err}\n\n```\n"
                + "\n".join(tail)
                + "\n```",
                title="Simple EspHome Updater",
                notification_id=f"{DOMAIN}_{name}",
            )
        else:
            persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{name}")
        finally:
            self.active.discard(name)
            self.progress.pop(name, None)
            self.async_update_listeners()
            await self.async_request_refresh()


def is_reachable(dev: ConfiguredDevice) -> bool:
    """False only if the dashboard says the device is offline."""
    return dev.get("state") != "offline"


def device_info(coordinator: UpdaterCoordinator, name: str) -> DeviceInfo:
    """Device carries the MAC as connection, so HA links it to the ESPHome one."""
    dev = coordinator.data[name]
    macs = {
        (dr.CONNECTION_NETWORK_MAC, format_mac(mac))
        for mac in (dev.get("mac_address"), dev.get("ethernet_mac"))
        if mac
    }
    return DeviceInfo(
        connections=macs,
        identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_{name}")},
        name=dev.get("friendly_name") or name,
        manufacturer="ESPHome",
        configuration_url=coordinator.api.url,
    )

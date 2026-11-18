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
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOG_TAIL_LINES, REQUEST_TIMEOUT, SCAN_INTERVAL_SECONDS

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
        self._lock = asyncio.Lock()
        self.active: set[str] = set()
        # 0-100 while a job runs, None if no percentage seen yet.
        self.progress: dict[str, int | None] = {}

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
        return {dev["name"]: dev for dev in devices["configured"]}

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

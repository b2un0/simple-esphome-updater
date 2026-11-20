# Simple EspHome Updater

<img src="assets/icon.svg" alt="icon" width="96">

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=b2un0&repository=simple-esphome-updater&category=integration)
[![Validate](https://github.com/b2un0/simple-esphome-updater/actions/workflows/validate.yml/badge.svg)](https://github.com/b2un0/simple-esphome-updater/actions/workflows/validate.yml)

Home Assistant integration that adds an update entity plus flash and compile buttons per ESPHome device, driven by your [ESPHome Dashboard](https://esphome.io/guides/getting_started_command_line/):

Per device:

| Entity | Does |
|---|---|
| **ESPHome firmware** (update entity) | installed vs. available ESPHome version. *Install* = compile + OTA upload, with progress in percent (compile 0-50 %, upload 50-100 %) |
| **ESPHome flash** (button, diagnostic) | compile + OTA upload on every press, even without a new version |
| **ESPHome compile** (button, diagnostic) | compile only, no upload |

Use **ESPHome flash** to roll out changes that do not bump the ESPHome version, e.g. updated remote packages or `external_components`.

Each device carries the MAC address of the ESPHome device as connection. Home Assistant (2026.8+) keeps one device per integration, and links devices with the same MAC: the ESPHome device page shows this device as linked.

## Install

1. Add the repository in the Marketplace (badge above), or as a custom repository: `b2un0/simple-esphome-updater`, type *Integration*.
2. Install, restart Home Assistant.
3. *Settings -> Devices & services -> Add integration -> Simple EspHome Updater*.

## Configuration

| Field | Description |
|---|---|
| URL | Dashboard address, e.g. `http://192.168.1.10:6052` |
| Username | Dashboard login, empty if none |
| Password | Dashboard login, empty if none |
| Only online devices | Off by default. Admit devices only after the dashboard explicitly reports them online; applies to update entities and both buttons. Editable later via **Configure**. |

Home Assistant must reach the dashboard over HTTP. The dashboard must reach the devices (OTA).

## Behaviour

- Online state comes from the dashboard. Offline devices: *ESPHome firmware* and *ESPHome flash* are unavailable. *ESPHome compile* stays available.
- Devices are read from the dashboard every minute; newly eligible devices get update entities and buttons automatically.
- With **Only online devices** enabled, never-seen-online configurations (including blueprints and unknown/missing states) have no entities or devices in this integration. Once explicitly seen online, a device stays admitted across outages, integration reloads, and Home Assistant restarts. Offline firmware/flash actions remain unavailable; compile stays available. Admission history is stored per dashboard entry, including online observations while the option is off.
- Changing the option reloads the integration. Enabling it removes excluded entities and exclusively owned device registry entries, never another integration's devices or entities. Existing registry entries alone do not prove a device was online: after upgrading, a real device offline before its first observed online poll will be excluded until it comes online. Disabling the option includes all configured devices again. Names identify devices; renaming a dashboard device requires a new online observation. Removing the integration entry clears its admission history.
- A press starts a background job. Buttons are unavailable and the update entity shows progress while it runs. One job at a time per dashboard, others wait.
- On failure a persistent notification shows the last log lines.

## Development

Tests use real Home Assistant dependencies (Python 3.14):

```sh
python -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/pytest tests -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

CI: HACS action, hassfest, ruff. Release: bump `version` in `manifest.json`, tag `vX.Y.Z`.

## License

MIT

# Simple EspHome Updater

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=b2un0&repository=simple-esphome-updater&category=integration)
[![Validate](https://github.com/b2un0/simple-esphome-updater/actions/workflows/validate.yml/badge.svg)](https://github.com/b2un0/simple-esphome-updater/actions/workflows/validate.yml)

Home Assistant integration that adds three buttons per ESPHome device, driven by your [ESPHome Dashboard](https://esphome.io/guides/getting_started_command_line/):

| Button | Does | Available |
|---|---|---|
| **Update** | compile + OTA upload | only when the dashboard offers a newer ESPHome version than the device runs |
| **Flash** | compile + OTA upload, every press | always (device needs an address) |
| **Compile** | compile only, no upload | always |

Use **Flash** to roll out changes that do not bump the ESPHome version, e.g. updated remote packages or `external_components`.

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

Home Assistant must reach the dashboard over HTTP. The dashboard must reach the devices (OTA).

## Behaviour

- Devices are read from the dashboard every 5 minutes; new devices get buttons automatically.
- A press starts a background job. The device's buttons are unavailable while it runs. One job at a time per dashboard, others wait.
- On failure a persistent notification shows the last log lines.

## Development

CI: HACS action, hassfest, ruff. Release: bump `version` in `manifest.json`, tag `vX.Y.Z`.

## License

MIT

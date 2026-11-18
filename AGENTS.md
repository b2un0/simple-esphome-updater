# AGENTS.md

Rules for agents working in this repo.

## Scope

- Home Assistant custom integration `simple_esphome_updater`. One integration, `custom_components/simple_esphome_updater/`.
- Keep it simple: per ESPHome dashboard device three buttons (update, flash, compile). No panels, cards, queues, auto-update, services unless asked.
- Talk to the dashboard only through `esphome-dashboard-api` (shipped with HA core). Do not add other requirements without a strong reason.

## Privacy

- Generic only. No personal data in code, docs, tests, commits, issues: no real hostnames, IPs, device names, credentials, tokens, paths, e-mail addresses.
- Examples use placeholders (`http://192.168.1.10:6052`, `my-device`).
- Never commit secrets or logs from a real setup.

## Rules

- Marketplace/HACS rules: `manifest.json` needs `domain`, `name`, `version`, `documentation`, `issue_tracker`, `codeowners`; `hacs.json` with `name`; `brand/icon.png`; release tag `vX.Y.Z` equals manifest version.
- CI must pass without ignored checks: HACS action, hassfest, ruff (`ruff check`, `ruff format --check`).
- Entity names carry the `ESPHome` prefix so they differ from the device's own entities. Buttons are `EntityCategory.DIAGNOSTIC`.
- Strings only in `translations/en.json`. Entity names via `translation_key`.
- No blocking I/O in the event loop. Long jobs run as background tasks, never inside `async_press`.
- Errors surface as persistent notification with log tail, not silent.
- Keep the README short and in sync with behaviour.
- Icon source is `assets/icon.svg`. After changing it, regenerate `brand/icon.png` (256x256) and `brand/icon@2x.png` (512x512). Do not use Home Assistant or ESPHome logos.

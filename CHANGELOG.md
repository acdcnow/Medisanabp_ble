# Changelog

All notable changes to this fork of [bkbilly/medisanabp_ble](https://github.com/bkbilly/medisanabp_ble)
are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-09-22

Home Assistant 2026.9 audit release, verified against core `2026.9.3`. The full
evidence, including every API that was checked and every open recommendation, is in
[docs/Home-Assistant-2026.9-Compatibility-Report.md](docs/Home-Assistant-2026.9-Compatibility-Report.md).

### Fixed

- **Setup could fail with `ModuleNotFoundError` on a clean Home Assistant.** The manifest declared
  `"requirements": []` while the parser imports `bluetooth_sensor_state_data` and `sensor_state_data`.
  Neither library is part of Home Assistant's base requirements, its `package_constraints.txt` or the
  `bluetooth` component's dependency tree, so nothing ever installed them and `async_setup_entry` raised
  before any entity was created. Both are now declared.
- **A failed battery read leaked the Bluetooth connection.** The battery read and the notification wait
  were outside the `try` block, and the `finally` clause called `stop_notify()`, which raises when
  `start_notify()` never succeeded. Everything after `establish_connection` now runs in `try/finally`
  with `disconnect()` as the only cleanup step, so the monitor cannot be left unreachable until a restart.
- **Measurements were republished as if they were new.** The notification `asyncio.Event` was created once
  and never cleared, so every poll after the first one returned immediately and reported the values of the
  previous measurement. The event is cleared before each connection.
- **The window in which the monitor answers could be delayed.** The battery was read before the
  notification subscription; it is now read first, then subscribed, then awaited.
- **`@retry_bluetooth_connection_error()` on the notification handler.** A notification is not a connection
  operation, and under bleak 3.0 the decorator turns the synchronous callback into a coroutine function,
  which bleak runs as a detached task. The handler is a plain function again and is called inline.
- **Bare `except:` clauses** on the date, subscribe and wait paths swallowed `BaseException`, including
  `asyncio.CancelledError`, so a reload could be lost; they now catch `BleakError`/`EOFError`/
  `TimeoutError`/`ValueError` and log with `_LOGGER.warning` instead of the deprecated `_LOGGER.warn`.
- **No config-flow text was rendered.** Home Assistant only loads
  `custom_components/<domain>/translations/<language>.json`; `strings.json` alone is not read for custom
  integrations. `translations/en.json` now ships.
- Short or malformed measurement frames no longer raise inside the Bluetooth stack (length guard plus a
  narrow date-parse guard), and a nameless advertisement no longer produces a device name starting with
  `None`.
- A missing battery characteristic (or a device without one) no longer fails the poll.

### Changed

- Coordinator state moved from `hass.data[DOMAIN][entry.entry_id]` to `entry.runtime_data`;
  `async_unload_entry` is a single platform unload.
- Config flow returns `ConfigFlowResult` and passes `include_ignore=False` to `_async_current_ids()`, so a
  device that was ignored in an earlier discovery is still offered in the manual picker.
- Sensor platform uses `AddConfigEntryEntitiesCallback`; `native_value` is annotated with `datetime`
  because the measured-date sensor returns one.
- Manifest gained `integration_type: "device"`; version bumped to `1.4.0`.
- `hacs.json`: minimum Home Assistant version raised from `2023.11.0` to `2026.9.0`.
- Mean arterial pressure, user id and the seconds field of the frame are decoded again (MAP is logged
  instead of being discarded).

### Added

- `custom_components/medisanabp_ble/translations/en.json`
- `custom_components/medisanabp_ble/brand/icon.png` and `icon@2x.png` (required by HACS validation)
- `docs/Architecture-Concept-Document.md`, `docs/System-Design-Document.md` and
  `docs/Home-Assistant-2026.9-Compatibility-Report.md`
- `testing/offline_smoke.py` — 20 checks that run the real parser, config flow, setup and platform code
  with stubbed Home Assistant/Bluetooth imports, so they need neither hardware nor Home Assistant
- `testing/make_brand_assets.py` — regenerates the brand icons without image libraries
- `CHANGELOG.md`

### Removed

- Unused imports (`BinarySensorValue`, `SensorDescription`) and the unused `user = data[16]` decoding.

## [1.3.0] and earlier

Earlier releases are the upstream project's; see the
[bkbilly/medisanabp_ble commit history](https://github.com/bkbilly/medisanabp_ble/commits/main).

[1.4.0]: https://github.com/acdcnow/Medisanabp_ble/releases/tag/v1.4.0

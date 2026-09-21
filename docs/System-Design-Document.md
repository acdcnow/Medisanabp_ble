# System Design Document (SDD)

**Integration:** `medisanabp_ble` — Medisana Blood Pressure BLE
**Version:** 1.4.0 (branch `ha-2026.9-audit`)
**Platform:** Home Assistant 2026.9 (core 2026.9.3, Python 3.14)
**Companion documents:** [ACD](Architecture-Concept-Document.md) · [HA 2026.9 Compatibility Report](Home-Assistant-2026.9-Compatibility-Report.md)

---

## 1. Overview

```text
manifest.json ─── matchers ─────► HA bluetooth component ──► config_flow.py ──► config entry
                                                                                    │
                                        __init__.py ◄── async_setup_entry ────────────┘
                                             │
                     ActiveBluetoothProcessorCoordinator (mode PASSIVE, connectable False)
                        │                                    │
          update_method │                                    │ poll_method (debounced)
                        ▼                                    ▼
        medisana_bp/parser.py: update()            medisana_bp/parser.py: async_poll()
        (advertisement → name, model, RSSI)        (connect → battery read → notify → event)
                        └──────────────┬─────────────────────┘
                                       ▼
                             SensorUpdate (sensor_state_data)
                                       │
                      sensor.py: sensor_update_to_bluetooth_data_update
                                       │
                     PassiveBluetoothDataProcessor → entities → HA state machine
```

Runtime dependencies (all guaranteed by HA 2026.9's `bluetooth` component unless declared): `bluetooth-sensor-state-data>=1.9.0` *(declared)*, `sensor-state-data>=2.20.0` *(declared)*, `habluetooth`, `bluetooth-data-tools`, `bleak`, `bleak-retry-connector` *(implied by the `bluetooth` component)*.

---

## 2. Data model

### 2.1 Config entry

| Field | Value |
| --- | --- |
| `domain` | `medisanabp_ble` |
| `VERSION` | `1` (no migrations defined; v1 entries are never invalidated) |
| `unique_id` | Bluetooth address (uppercase MAC or macOS UUID) |
| `title` | `device.title or device.get_device_name() or discovery_info.name`, i.e. advertisement name or model |
| `data` | empty — the address is the identity, everything else is derived at runtime |
| `options` | none (no options flow) |
| `runtime_data` | `ActiveBluetoothProcessorCoordinator[SensorUpdate]` |

### 2.2 Parser and coordinator state

| Object | Lifetime | Content |
| --- | --- | --- |
| `MedisanaBPBluetoothDeviceData` (subclass of `bluetooth_sensor_state_data.BluetoothData` → `sensor_state_data.SensorData`) | one per config entry, created in `async_setup_entry` | `_device_id_info`, `_device_id_to_name/type`, `_sensor_values(_updates)`, `_sensor_descriptions(_updates)`, `_title`, plus the integration's `_event: asyncio.Event` |
| `ActiveBluetoothProcessorCoordinator` | one per config entry | last advertisement, `_last_service_info`, `_last_poll`, debounced poll task, registered processors, restore data keyed by `entry.entry_id` |
| `PassiveBluetoothDataProcessor` | created in the sensor platform | accumulated `PassiveBluetoothDataUpdate` (devices, descriptions, names, data) → entity values |

Key detail: the parser object is shared between the passive (`update`) and the active (`async_poll`) path, so a poll merges into the same sensor set instead of creating parallel state.

### 2.3 Entity model

`device_id` is never set by the parser, so exactly one HA device per config entry (entity unique IDs `{address}-{key}`) is produced by `PassiveBluetoothProcessorEntity`.

| Parser key | HA entity | Unit | Device class | State class | Category | Enabled |
| --- | --- | --- | --- | --- | --- | --- |
| `systolic` | Systolic | mmHg | `pressure` | – | – | yes |
| `diastolic` | Diastolic | mmHg | `pressure` | – | – | yes |
| `pulse` | Pulse | bpm | – | – | – | yes |
| `battery_percent` | Battery | % | `battery` | `measurement` | diagnostic | yes |
| `signal_strength` | Signal Strength | dBm | `signal_strength` | `measurement` | diagnostic | no |
| `timestamp` | Measured Date | – | `timestamp` | – | – | yes |

Pressure and pulse deliberately carry no `state_class`, so they are not treated as long-term statistics (a measurement is an event, not a continuous quantity).

---

## 3. Measurement model

### 3.1 Source of data

| Transport | Characteristic | Usage |
| --- | --- | --- |
| advertisement | – | discovery, name, RSSI; **no measurement data** |
| GATT notify | `00002A35-0000-1000-8000-00805f9b34fb` (Blood Pressure Measurement) | one frame per connection after `start_notify` |
| GATT read | `00002A19-0000-1000-8000-00805F9B34FB` (Battery Level) | first byte = percent |

### 3.2 `0x2A35` frame layout as parsed

| Offset | Meaning | Code |
| --- | --- | --- |
| 0 | flags (ignored) | – |
| 1–2 | systolic, little endian | `data[2] * 256 + data[1]` |
| 3–4 | diastolic, little endian | `data[4] * 256 + data[3]` |
| 5–6 | mean arterial pressure (MAP) — **decoded into the log only** | `data[6] * 256 + data[5]` |
| 7–8 | year, little endian | `data[8] * 256 + data[7]` |
| 9 / 10 / 11 / 12 | month / day / hour / minute | direct |
| 13 | seconds — **ignored** | – |
| 14–15 | pulse, little endian | `data[15] * 256 + data[14]` |
| 16 | user id — **ignored** | – |

Frames shorter than 16 bytes are rejected with a warning instead of raising `IndexError` inside the Bluetooth stack.

---

## 4. Component design

### 4.1 `custom_components/medisanabp_ble/__init__.py`

Responsibility: config entry lifecycle, coordinator construction, platform forwarding.

| Symbol | Signature | Notes |
| --- | --- | --- |
| `PLATFORMS` | `list[Platform]` | `[Platform.SENSOR]` |
| `MedisanaBPConfigEntry` | `ConfigEntry[ActiveBluetoothProcessorCoordinator[SensorUpdate]]` | plain alias instead of a PEP 695 `type` statement, so the package imports on Python 3.11 for the offline test |
| `async_setup_entry` | `(hass, entry: MedisanaBPConfigEntry) -> bool` | builds `MedisanaBPBluetoothDeviceData`, the coordinator, stores it in `runtime_data`, forwards platforms, then `coordinator.async_start()` via `entry.async_on_unload` |
| `_needs_poll` (closure) | `(service_info: BluetoothServiceInfoBleak, last_poll: float | None) -> bool` | `hass.state is CoreState.running` **and** `data.poll_needed(...)` **and** a connectable `BLEDevice` exists |
| `_async_poll` (closure) | `(service_info) -> SensorUpdate` (coroutine) | picks `service_info.device` when connectable, else resolves one with `async_ble_device_from_address(..., True)`; raises `RuntimeError` when none is reachable |
| `async_unload_entry` | `(hass, entry) -> bool` | `async_unload_platforms` only; coordinator teardown is handled by `async_on_unload` |

### 4.2 `config_flow.py`

| Symbol | Behaviour |
| --- | --- |
| `MedisanaBPConfigFlow` | `VERSION = 1`, `domain=DOMAIN`, state: `_discovery_info`, `_discovered_device`, `_discovered_devices` |
| `async_step_bluetooth(discovery_info)` | sets the unique ID, aborts when configured, rejects unsupported signatures with `not_supported`, otherwise jumps to the confirm step |
| `async_step_bluetooth_confirm(user_input)` | `_set_confirm_only()`, creates the entry with the device name; title placeholders are set for the dialog |
| `async_step_user(user_input)` | lists every discovered device that is not yet configured (`_async_current_ids(include_ignore=False)`) and not already in the picker; aborts with `no_devices_found`; creates the entry for the chosen address |

Notes: `async_discovered_service_info(self.hass, False)` asks for **all** recorded advertisements (superset of connectable ones), matching the coordinator's `connectable=False` choice; the actual connectability is re-checked when polling.

### 4.3 `sensor.py`

| Symbol | Behaviour |
| --- | --- |
| `SENSOR_DESCRIPTIONS` | `dict[str, SensorEntityDescription]`, see §2.3 |
| `sensor_update_to_bluetooth_data_update(sensor_update)` | converts a `SensorUpdate` into `PassiveBluetoothDataUpdate`: device infos via `sensor_device_info_to_hass_device_info`, descriptions via `SENSOR_DESCRIPTIONS[key]`, values/names via the entity values |
| `async_setup_entry(hass, entry, async_add_entities: AddConfigEntryEntitiesCallback)` | reads the coordinator from `entry.runtime_data`, registers the entity listener and the processor (`async_register_processor(processor, SensorEntityDescription)`) |
| `MedisanaBPBluetoothSensorEntity` | `native_value` from `processor.entity_data`, `available` always `True`, `assumed_state = not processor.available` |

### 4.4 `device.py` and `const.py`

| Symbol | Behaviour |
| --- | --- |
| `const.DOMAIN` | `"medisanabp_ble"` — used by the config flow only after the `runtime_data` refactor |
| `device_key_to_bluetooth_entity_key(device_key: DeviceKey)` | adapts `sensor_state_data` keys to `PassiveBluetoothEntityKey(key, device_id)` |

### 4.5 `medisana_bp/parser.py` (vendored parser)

| Symbol | Signature | Behaviour |
| --- | --- | --- |
| `MedisanaBPSensor` | `StrEnum` | `systolic`, `diastolic`, `pulse`, `signal_strength`, `battery_percent`, `timestamp` (the string values are the entity keys, and `signal_strength` intentionally matches `sensor_state_data.DeviceClass.SIGNAL_STRENGTH.value`) |
| `MedisanaBPBluetoothDeviceData.__init__` | `() -> None` | `super().__init__()` plus the notification `asyncio.Event` |
| `_start_update(service_info)` | `(BluetoothServiceInfo) -> None` | sets manufacturer `Medisana`, model `Blood Pressure Measurement`, device name/title `«advertisement name or "Medisana BP"» «short address»` |
| `poll_needed(service_info, last_poll)` | `(…, float | None) -> bool` | `not last_poll or last_poll > UPDATE_INTERVAL`; `last_poll` is the *age in seconds* of the last attempt, not a timestamp |
| `notification_handler(_sender, data)` | `(Any, bytearray) -> None` | validates length, decodes the frame, publishes the measured date + three values, sets the event. Plain synchronous callable: bleak 3.0 invokes it inline, so ordering and the event are deterministic |
| `_async_read_battery(client)` | `(BleakClientWithServiceCache) -> None` | reads `0x2A19`; missing characteristic or `BleakError`/`EOFError` is logged and skipped |
| `async_poll(ble_device)` | `(BLEDevice) -> SensorUpdate` | clears the event, connects, battery, subscribe, bounded wait, always disconnects, returns `_finish_update()` |

### 4.6 `medisana_bp/__init__.py` and `medisana_bp/const.py`

Facade that re-exports the parser API (`__all__`) so the module can be consumed standalone; `const.py` holds the two characteristic UUIDs, `UPDATE_INTERVAL = 10` and `NOTIFICATION_TIMEOUT = 15`.

---

## 5. Data quality

### 5.1 Validation pipeline

1. **Frame length** – `< 16` bytes → warning, no sensor touched.
2. **Date parse** – `strptime` failure (`TypeError`/`ValueError`) → warning, the three pressure/pulse values are still published.
3. **Battery** – non-byte-safe payloads, missing characteristic or read failure → skipped, the previous battery value is kept.
4. **Unreachable device** – `_async_poll` raises `RuntimeError` when no connectable adapter/proxy can reach the address; the coordinator logs the poll failure and continues.
5. **Subscribe failure** – `BleakError`/`EOFError` from `start_notify` → warning, no 15 s wait (the poll returns the battery only).

### 5.2 Timestamps

The device sends a local wall clock. The parser attaches the host's local timezone (`datetime.now(timezone.utc).astimezone().tzinfo`) and hands a timezone-aware `datetime` to `SensorDeviceClass.TIMESTAMP`, which HA renders as the measurement time. If HA's configured timezone differs from the host OS timezone the value is off by that offset (open item R-2; fixing it requires the conversion to move into the integration layer, because the vendored parser must stay HA free).

### 5.3 Availability semantics

`available` is always `True` and `assumed_state` mirrors `processor.available`. Rationale: the monitor only speaks when someone measures blood pressure, so a real "unavailable" state would make every entity flap between measurements. The measured-date sensor is the honest freshness indicator; HA's restore mechanism (passive update processor storage) repopulates the last values after a restart.

---

## 6. Runtime flows

### 6.1 Setup

`async_setup_entry` → `MedisanaBPBluetoothDeviceData()` → `ActiveBluetoothProcessorCoordinator(...)` (keyword arguments `address`, `mode=PASSIVE`, `update_method=data.update`, `needs_poll_method=_needs_poll`, `poll_method=_async_poll`, `connectable=False`) → `entry.runtime_data = coordinator` → `async_forward_entry_setups` → `entry.async_on_unload(coordinator.async_start())`.

### 6.2 Poll with measurement

See ACD §7.3. Failure branches: no connectable device (raise, poll skipped), connect error (propagates to the coordinator which logs and retries on the next advertisement), battery error (logged, continue), subscribe error (logged, skip wait), wait timeout (warning, return whatever was collected).

### 6.3 Advertisement-only update

`update_method` runs `BluetoothData.update(service_info)`, which sets device info and injects RSSI, so the diagnostic signal sensor stays fresh even when no poll happens.

### 6.4 Unload/reload

Platform unload → listener/processor removal → coordinator stop via `async_on_unload` → `runtime_data` released. The `finally` in `async_poll` guarantees that a reload during an in-flight poll cannot leave a connected client behind.

---

## 7. Function inventory — what is actually hit at runtime

### 7.1 Called by Home Assistant / the BLE stack

| Function | Called by | Frequency |
| --- | --- | --- |
| `config_flow.MedisanaBPConfigFlow.__init__` | HA flow manager | once per flow |
| `config_flow.async_step_bluetooth` | HA discovery | per matching advertisement while unconfigured |
| `config_flow.async_step_bluetooth_confirm` | HA UI | once per setup |
| `config_flow.async_step_user` | HA UI | once per manual setup |
| `__init__.async_setup_entry` | HA config entry manager | per load/reload |
| `__init__.async_unload_entry` | HA config entry manager | per unload/reload |
| `sensor.async_setup_entry` | HA platform forwarding | per load/reload |
| `sensor.MedisanaBPBluetoothSensorEntity.native_value` / `.available` / `.assumed_state` | HA entity platform | on every state write |
| `parser.MedisanaBPSensor`, `MedisanaBPBluetoothDeviceData.__init__` | `async_setup_entry` / config flow | per load/flow |

### 7.2 Called indirectly (through the coordinator)

| Function | Called by | Frequency |
| --- | --- | --- |
| `parser._start_update` | `BluetoothData.update()` / `BluetoothData.supported()` | every advertisement, and each config-flow support check |
| `parser.poll_needed` | `__init__._needs_poll` | every advertisement |
| `__init__._needs_poll` | `ActiveBluetoothProcessorCoordinator.needs_poll` | every advertisement |
| `__init__._async_poll` | coordinator's debounced poll | when a poll is due and a connectable device exists |
| `parser.async_poll` | `__init__._async_poll` | idem |
| `parser._async_read_battery` | `parser.async_poll` | every successful connection |
| `parser.notification_handler` | bleak callback (inline, as a plain function) | once per connection when the device answers |
| `sensor.sensor_update_to_bluetooth_data_update` | `PassiveBluetoothDataProcessor.async_handle_update` | every update (advertisement *and* poll) |
| `device.device_key_to_bluetooth_entity_key` | `sensor_update_to_bluetooth_data_update` | every update, once per sensor |
| inherited `SensorData.update_sensor` / `_finish_update` / `set_device_*` / `set_title` / `update_signal_strength` | parser | every update |

### 7.3 Present but never hit by this integration

| Symbol | Status |
| --- | --- |
| `medisana_bp.__version__` (`"0.1.0"`) | informational only; the shipped version is `manifest.json:version` |
| `medisana_bp.__all__` entries `BinarySensorDeviceClass`, `SensorDeviceClass`, `SensorDeviceInfo`, `SensorValue`, `Units` | unused by the integration, kept as the vendored library's public API |
| `retry_bluetooth_connection_error` on the notification handler | **removed** in 1.4.0 — a notification is not a connection operation; bleak 3.0 would run the coroutine wrapper as a detached task (see report F4) |
| `user = data[16]` | **removed** in 1.4.0 (decoded, never used) |
| `arter` (MAP) | **repurposed** in 1.4.0: decoded value is now logged; exposing it as an entity is open item R-7 |
| `BinarySensorValue`, `SensorDescription` imports in `medisana_bp/__init__.py` | **removed** in 1.4.0 (unused imports) |
| `MedisanaBPSensor.SIGNAL_STRENGTH` description | **not** dead code: `bluetooth_sensor_state_data` injects the RSSI sensor automatically |

---

## 8. Localisation

* `translations/en.json` is the file Home Assistant loads (`Integration.has_translations` requires the directory; the loader reads `<component>/translations/<language>.json`).
* `strings.json` is kept identical in content for parity with core tooling and for the upstream translation pipeline.
* Reused core strings are referenced, not duplicated: `[%key:component::bluetooth::config::flow_title%]`, `[%key:common::config_flow::data::device%]`, `[%key:common::config_flow::abort::no_devices_found%]`, `[%key:component::bluetooth::config::step::bluetooth_confirm::description%]`. The frontend resolves these keys, therefore the bluetooth integration's own strings must exist in the running core (they do, for every supported HA version).
* No entity-name translations exist: entity names come from `SensorEntityDescription`/`SensorValue.name` ("Systolic", "Diastolic", "Pulse", "Battery", "Measured Date"). Moving to `translation_key`s plus an `entity` section is possible but would rename existing entities.

---

## 9. Migrations and compatibility

| Aspect | State |
| --- | --- |
| Config entry version | `1`; no `async_migrate_entry`. All the data lives in `unique_id`, so a version bump is only needed if entry data is introduced. |
| HA minimum version | `hacs.json` demands 2026.9.0 (this branch is verified against core 2026.9.3). The code itself needs ≥ 2024.6 for `runtime_data`, ≥ 2024.4 for `ConfigFlowResult` and ≥ 2023.12 for the active Bluetooth coordinator. |
| Python minimum | 3.11 (plain type alias in `__init__.py`, so the package imports on a developer machine for the offline smoke test); HA 2026.9 ships 3.14. |
| Entity historical continuity | Unique IDs are `{address}-{key}` and unchanged, so existing entities, statistics and automations survive the 1.4.0 update. |
| Parser API | The vendored module is only consumed by this integration; no external importers are known. |
| Restored state | HA's passive update processor storage restores devices/descriptions/values across restarts; the entity set therefore survives a restart even before the first advertisement arrives. |

---

## 10. Testing and validation

| Level | How | Notes |
| --- | --- | --- |
| Offline behaviour | `python testing/offline_smoke.py` (20 checks) | stubs Home Assistant, Bluetooth, bleak and `sensor_state_data`; covers advertisement and notification parsing (including short/malformed frames), the whole poll lifecycle with its error paths, the disconnect guarantees, the per-poll notification wait, the config flow, entity creation and the metadata rules |
| Metadata | hassfest + HACS GitHub Actions (`.github/workflows/*`) | they validate the manifest and repository layout but cannot detect undeclared imports (F1) |
| Syntax | `python -m py_compile custom_components/medisanabp_ble/**/*.py` | any Python ≥ 3.11 |
| Structural | compare the calls against the pinned library signatures (report §2) | repeat on every HA release |
| End to end | real device: `Settings → Devices`, then measure and watch `sensor.*_systolic` | the only true acceptance test of the BLE transport |

---

## 11. Extension guide

**Add a sensor (e.g. MAP / mean arterial pressure).**
1. `parser.py`: add the enum member, call `update_sensor(key=…, native_unit_of_measurement=Units.PRESSURE_MMHG, native_value=arter, device_class=SensorDeviceClass.PRESSURE, name="Mean Arterial Pressure")` in `notification_handler`.
2. `sensor.py`: add the matching `SensorEntityDescription` (key, unit, device class, icon).
3. Nothing else — the processor creates the entity on the first update, and the key mapping in `device.py` is generic.

**Add a device model.**
1. `manifest.json`: add a `bluetooth` matcher (`manufacturer_id`, optional `manufacturer_data_start`, or `local_name`).
2. `parser.py`: extend `_start_update` (model name) and, if the frame differs, the decoding in `notification_handler`.
3. `docs/Home-Assistant-2026.9-Compatibility-Report.md`: record the new signature.

**Replace the vendored parser with a PyPI package.**
Publish `medisana_bp` (name it `medisana-bp` to match the `*-ble` ecosystem), delete the local package, import from the distribution and add it to `manifest.json:requirements`. This makes the parser independently updatable by HACS/HA.

**Change the poll cadence.** `medisana_bp/const.py:UPDATE_INTERVAL` (age of the last attempt) and `NOTIFICATION_TIMEOUT`; the coordinator's debouncer cooldown (`POLL_DEFAULT_COOLDOWN = 10` in core) is an upper bound for overlap protection, and can be overridden with `poll_debouncer` if a different cadence is needed.

---

## 12. Known limitations

1. Only the values the device offers after a connection are available; no historical measurements, no on-demand measurement trigger.
2. Measured-date timezone relies on the host's local timezone (§5.2, R-2).
3. Entities never become unavailable; staleness must be evaluated through the measured-date sensor (R-1).
4. Polling repeats every `UPDATE_INTERVAL` of advertisement activity even when the measurement has not changed (R-3).
5. `SENSOR_DESCRIPTIONS[key]` is a strict lookup: a key the library adds later would fail the whole update instead of being skipped (R-4).
6. MAP, user id and seconds of the frame are not exposed (R-7).
7. No diagnostics platform, and no captured advertisement/notification fixture: the offline smoke test proves the wiring and the error paths, not the real frame layout of a device (R-6).
8. The fork still advertises the upstream repository as documentation and issue tracker (R-5).

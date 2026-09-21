# Home Assistant 2026.9 Compatibility Report

**Repository:** <https://github.com/acdcnow/Medisanabp_ble>
**Audited revision:** `bf505a7` (`main`, identical to upstream `bkbilly/medisanabp_ble:main`)
**Audit branch:** `ha-2026.9-audit` (integration version 1.4.0)
**Reference platform:** Home Assistant core tag **2026.9.3** (Python 3.14), library versions as pinned by that core release
**Method:** static audit — every Home Assistant and third-party API used by the integration was checked against the 2026.9.3 sources and the library sources/versions that core installs. No physical Medisana monitor was available, so the BLE transport itself was reviewed by reading `bleak` 3.0.2 and `bleak-retry-connector` 4.7.x.

**Companion documents:** [ACD](Architecture-Concept-Document.md) · [SDD](System-Design-Document.md)

---

## 1. Verdict

| Question | Answer |
| --- | --- |
| Is the integration still **API compatible** with HA 2026.9? | **Yes.** Every API it uses still exists with a matching signature (see §2). No removal, rename or deprecation blocks it. |
| Would a **fresh HA 2026.9 installation** have loaded it? | **No.** `manifest.json` declared `"requirements": []` while importing two libraries that Home Assistant does not install → `ModuleNotFoundError` on setup. Fixed in this branch (§3, F1). |
| Are there other real defects? | **Yes**, four with runtime impact (F2–F5): a leaked BLE connection, a notification event that was never cleared (stale measurements after the first poll), an ordering problem around the battery read, and bare `except:` clauses that swallowed cancellation. All fixed. |
| Is it ready now? | **Yes**, with the fixes in this branch: manifest valid for hassfest/HACS, all used APIs verified against 2026.9.3, config-flow strings actually rendered. Remaining work is optional hardening (§5). |

---

## 2. Interface verification (evidence)

| Used by the integration | Status in HA 2026.9.3 | Evidence (core tag 2026.9.3 / library version) |
| --- | --- | --- |
| `ActiveBluetoothProcessorCoordinator(hass, logger, *, address, mode, update_method, needs_poll_method, poll_method, poll_debouncer, connectable, scan_interval, scan_duration)` | unchanged; only `hass`/`logger` are positional, the rest is keyword-only — the call site passes exactly that | `homeassistant/components/bluetooth/active_update_processor.py` |
| `BluetoothScanningMode`, `BluetoothServiceInfoBleak`, `async_ble_device_from_address`, `async_discovered_service_info` exported from `homeassistant.components.bluetooth` | present | `components/bluetooth/__init__.py`, `components/bluetooth/api.py` |
| `PassiveBluetoothDataUpdate(devices, entity_descriptions, entity_names, entity_data)` | present, still generic, `entity_names` still supported (used for the entity names) | `components/bluetooth/passive_update_processor.py` |
| `PassiveBluetoothDataProcessor(update_method, restore_key)`, `async_add_entities_listener`, `async_register_processor(processor, entity_description_class)` | present, `entity_description_class` still optional | idem |
| `PassiveBluetoothProcessorEntity` with `entity_key`, `processor.entity_data`, `processor.available`, `_attr_unique_id = f"{address}-{key}"` | present | idem |
| `sensor_device_info_to_hass_device_info` from `homeassistant.helpers.sensor` | **still exists**, not deprecated (imports `sensor_state_data` under `TYPE_CHECKING` only) | `homeassistant/helpers/sensor.py` |
| `AddEntitiesCallback` / `AddConfigEntryEntitiesCallback` | both exist; the latter is the typed protocol for `async_setup_entry` platforms | `homeassistant/helpers/entity_platform.py` |
| `_set_confirm_only()` | present | `homeassistant/config_entries.py` |
| `_async_current_ids()` | present, signature `(include_ignore: bool = True)` — core's own Bluetooth flows pass `include_ignore=False` | `homeassistant/config_entries.py`, `components/oralb/config_flow.py` |
| `FlowResult` | still importable, but the canonical alias is `ConfigFlowResult` (`_flow_result = ConfigFlowResult`) | `homeassistant/config_entries.py` |
| `SensorDeviceClass`, `SensorStateClass`, `EntityCategory`, `UnitOfPressure`, `UnitOfPressure.MMHG`, `PERCENTAGE`, `SIGNAL_STRENGTH_DECIBELS_MILLIWATT` | present | `homeassistant/components/sensor/__init__.py`, `homeassistant/const.py` |
| Manifest `bluetooth` matcher keys `manufacturer_id`, `local_name`, `connectable` | valid; `connectable` is a supported key and defaults to `True` in the matcher | `script/hassfest/manifest.py`, `components/bluetooth/match.py` |
| `sensor_state_data` 2.20.0: `SensorDeviceClass`, `BinarySensorDeviceClass`, `Units.PRESSURE_MMHG`, `Units.PERCENTAGE`, `SensorData.update_sensor(...)`, `set_device_name/manufacturer/type`, `set_title`, `_finish_update()`, `SensorUpdate.entity_values` | all present, keyword-compatible with the call sites | `sensor_state_data` 2.20.0 (`__init__.py`, `data.py`, `units.py`) |
| `bluetooth_sensor_state_data` 1.9.0: `BluetoothData.update()` → `_start_update()` + `update_signal_strength(data.rssi)` + `_finish_update()` | present; explains why the `signal_strength` entity description is needed although the parser never sets it | `bluetooth_sensor_state_data` 1.9.0 |
| `bleak` 3.0.2 `start_notify(..., callback)` | accepts sync **and** async callbacks: a coroutine function is scheduled as a task, a plain function is called inline | `bleak/__init__.py` (v3.0.2) |
| `bleak_retry_connector` 4.7.x `establish_connection(client_class, device, name)`, `retry_bluetooth_connection_error()` | present; `retry_bluetooth_connection_error` wraps **coroutine** functions only | `bleak-retry-connector` 4.7.x |

### Version context pinned by core 2026.9.3

`bleak==3.0.2`, `bleak-retry-connector==4.7.0`, `bluetooth-adapters==2.4.0`, `bluetooth-auto-recovery==1.6.4`, `bluetooth-data-tools==1.29.24`, `habluetooth==6.26.11`, `home-assistant-bluetooth==2.0.0` (base requirement), `dbus-fast==5.0.22`.

Not part of core: `sensor-state-data`, `bluetooth-sensor-state-data` — neither appears in `requirements.txt` (base), `package_constraints.txt`, nor the `bluetooth` component's requirements.

---

## 3. Findings

Severity: **Blocker** = cannot load, **High** = wrong data or resource leak, **Medium** = broken behaviour/lint class bug, **Low** = convention/typing, **Info** = tidy-up.

| ID | Sev | Finding | Evidence / reasoning | Status |
| --- | --- | --- | --- | --- |
| F1 | **Blocker** | `manifest.json` had `"requirements": []` but the parser imports `bluetooth_sensor_state_data` and `sensor_state_data`. | Home Assistant installs a component's declared requirements and nothing else. `home-assistant-bluetooth==2.0.0` is in HA's base `requirements.txt`, so that import is safe — but `sensor-state-data` / `bluetooth-sensor-state-data` are in neither `requirements.txt`, `package_constraints.txt`, the `bluetooth` component manifest, nor the dependency tree of `habluetooth` 6.26.11. Core itself notes for the sibling library: "`sensor_state_data` is a second-party library … which is not strictly required by Home Assistant" (`homeassistant/helpers/sensor.py`). Any install without another `*-ble` integration failed with `ModuleNotFoundError` during `async_setup_entry`. | **Fixed**: `requirements: ["bluetooth-sensor-state-data>=1.9.0", "sensor-state-data>=2.20.0"]` |
| F2 | **High** | Leaked BLE connection: the battery read (`read_gatt_char`) and the notification wait sat **outside** the `try`, and the `finally` called `stop_notify()` before `disconnect()`. A missing battery characteristic, a read error or a `stop_notify` failure after a failed `start_notify` left the client connected — the monitor then refuses new connections until HA restarts. | `medisana_bp/parser.py:async_poll` (pre-audit) | **Fixed**: `_async_read_battery()` never raises, the whole session is inside `try/finally`, `disconnect()` is the only cleanup step (notifications stop on disconnect, and reloads are not blocked). |
| F3 | **High** | `self._event` was created once and **never cleared**. From the second poll on, `asyncio.wait_for(self._event.wait(), 15)` returned immediately, so a poll that received no notification published the *previous* measurement as if it were current. | `medisana_bp/parser.py` (pre-audit) vs. `ActiveBluetoothProcessorCoordinator._async_poll` which dispatches whatever `poll_method` returns | **Fixed**: `self._event.clear()` before connecting. |
| F4 | **High** | Two problems in one flow: (a) the battery read happened *before* `start_notify`, so a slow or failing read delayed the subscription and the monitor's answer could arrive outside the 15 s window; (b) `notification_handler` was decorated with `@retry_bluetooth_connection_error()` although it is a synchronous callback — under bleak 3.0 the decorator turns it into a coroutine function, which bleak schedules as a **detached task**, decoupling the callback from the connection and making the "retry a BLE connection error" semantics meaningless. | `bleak/__init__.py` v3.0.2 `start_notify` (`inspect.iscoroutinefunction`) and `bleak_retry_connector.retry_bluetooth_connection_error` (`async def` wrapper) | **Fixed**: battery read first, then subscribe, then wait; decorator removed → the handler is a plain sync callable invoked inline. |
| F5 | **Medium** | Three bare `except:` clauses (date parsing, `start_notify`, the notification wait) plus deprecated `_LOGGER.warn`. Bare `except:` catches `BaseException`, including `asyncio.CancelledError`, so a reload/shutdown during a poll could be swallowed; it also hid real errors behind "Notify Bleak error". | `medisana_bp/parser.py` (pre-audit) | **Fixed**: `except (BleakError, EOFError)` / `except TimeoutError` / `except (TypeError, ValueError)`, `_LOGGER.warning`. |
| F6 | **Medium** | No `translations/` directory. HA loads only `<component>/translations/<language>.json` (`helpers/translation.py:_async_get_component_strings`) and `Integration.has_translations` is literally "a `translations` directory exists" (`loader.py`) — for custom integrations `strings.json` is not read at runtime (core's hassfest/pylint helpers say so explicitly: "core integrations use strings.json, custom integrations use translations/en.json"). The config flow therefore rendered no translated labels. | `homeassistant/helpers/translation.py`, `homeassistant/loader.py`, `script/hassfest/services.py` | **Fixed**: `translations/en.json` added (same content as `strings.json`). |
| F7 | **Low** | Coordinator kept in `hass.data[DOMAIN][entry.entry_id]` (legacy since HA 2024.6) and `async_unload_entry` popped it only when the platform unload succeeded, leaving a stale key otherwise. | `__init__.py` (pre-audit) | **Fixed**: `entry.runtime_data` with a PEP 695 typed alias; unload is now a single platform unload. |
| F8 | **Low** | Typing/modernisation: `FlowResult` (legacy alias) instead of `ConfigFlowResult`; `_async_current_ids()` used the default `include_ignore=True`, so a device the user had *ignored* was invisible in the manual picker (core's Bluetooth flows pass `include_ignore=False`); platform used `AddEntitiesCallback` instead of `AddConfigEntryEntitiesCallback`; `native_value` was annotated `str | int | None` although the date sensor returns a `datetime`. | `config_flow.py`, `sensor.py` (pre-audit) vs. core 2026.9.3 | **Fixed**. |
| F9 | **Low** | `hacs.json` declared `"homeassistant": "2023.11.0"`, far below what the code needs (`runtime_data` ≥ 2024.6, `ConfigFlowResult` ≥ 2024.4, active Bluetooth coordinator ≥ 2023.12). HACS would have offered the integration to installations it cannot run on. | `hacs.json` | **Fixed**: `"2026.9.0"` (the audited version). |
| F10 | **Info** | Dead code and tidies: unused imports `BinarySensorValue`/`SensorDescription` in `medisana_bp/__init__.py`; unused `user = data[16]`; unused `arter` (MAP) value; `device.py` documented itself as "Constants for MedisanaBP BLE"; import order inconsistent with HA's style; doubled blank lines. | static review | **Fixed** (MAP is now logged instead of discarded). |
| F11 | **Info** | `SIGNAL_STRENGTH` was suspected dead code but is **not**: `bluetooth_sensor_state_data.BluetoothData.update()` calls `update_signal_strength(data.rssi)` with the key `signal_strength`, which matches the description. Left untouched. | library source | Verified, no change. |
| F12 | **Info** | `iot_class: local_push` while the measurements only arrive via an active connection. | Core uses `local_push` for the same architecture (`eufylife_ble`, `tilt_ble`). | Left as is, documented in ACD AD-10. |

---

## 4. Changes on this branch

```text
custom_components/medisanabp_ble/manifest.json                  requirements, integration_type: device, version 1.4.0
custom_components/medisanabp_ble/__init__.py                    entry.runtime_data + typed config entry, import order
custom_components/medisanabp_ble/sensor.py                      runtime_data, AddConfigEntryEntitiesCallback, native_value type, import order
custom_components/medisanabp_ble/config_flow.py                 ConfigFlowResult, include_ignore=False, import order
custom_components/medisanabp_ble/device.py                      docstring, import order
custom_components/medisanabp_ble/medisana_bp/parser.py          disconnect guarantee, event clearing, battery-first, no retry decorator,
                                                                specific excepts, payload length guard, MAP logged, habluetooth import
custom_components/medisanabp_ble/medisana_bp/const.py           NOTIFICATION_TIMEOUT, comments
custom_components/medisanabp_ble/medisana_bp/__init__.py        unused imports removed
custom_components/medisanabp_ble/translations/en.json           NEW - the file HA actually loads
hacs.json                                                       homeassistant: 2026.9.0
docs/Architecture-Concept-Document.md                           NEW
docs/System-Design-Document.md                                  NEW
docs/Home-Assistant-2026.9-Compatibility-Report.md              NEW (this file)
```

No entity identifier, unique ID or config entry format changed, so existing entities, statistics and automations survive the update.

---

## 5. Not changed — recommendations

| ID | Recommendation | Why it is worth doing |
| --- | --- | --- |
| R-1 | Add a freshness/availability concept (e.g. mark the measurement sensors unavailable when the measured-date is older than N hours) | today the last measurement stays "current" forever |
| R-2 | Move the timezone handling of the measured date into the integration layer and use Home Assistant's configured timezone instead of the host's | exact timestamps also when `hass.config.time_zone` differs from the OS timezone |
| R-3 | Skip a poll when the last measurement is already known (or raise `UPDATE_INTERVAL`) | fewer BLE connect/disconnect cycles near the monitor |
| R-4 | Make the key lookup in `sensor_update_to_bluetooth_data_update` tolerant (`SENSOR_DESCRIPTIONS.get` + skip) | a new key from a future library version currently fails the whole device update |
| R-5 | Fork hygiene: point `documentation`/`issue_tracker` at the fork and adjust `codeowners` | user reports currently land upstream |
| R-6 | Add parser tests: feed a captured `0x2A35` frame into `notification_handler` with a stubbed `SensorData`, and a recorded advertisement into `_start_update` | the defects F2–F5 were all invisible without a device |
| R-7 | Expose MAP (`data[6]`), optionally the user id (`data[16]`) | clinically relevant value that is already decoded |
| R-8 | Publish the vendored `medisana_bp` as a PyPI package and depend on it | the parser can then be updated without a new integration release |
| R-9 | Add a diagnostics platform (`async_get_config_entry_diagnostics`) | one-click state dump for support cases |

---

## 6. How to re-verify

```text
1  hassfest / HACS validation: push the branch and watch .github/workflows/{hassfest,validate}.yaml
2  syntax:                    python -m py_compile custom_components\medisanabp_ble\**\*.py   (Python >= 3.12)
3  real HA:                    copy custom_components\medisanabp_ble into /config/custom_components,
                              restart, confirm "Medisana Blood Pressure BLE" is discovered,
                              watch for "Manifest ... requirements" messages and for
                              "Could not read battery level" / "Timeout getting measurement data"
4  measurement check:          put the monitor on the cuff, measure, and confirm
                              sensor.<device>_systolic / _diastolic / _pulse / _measured_date update
5  leak check:                 Settings -> Devices -> the monitor; after several polls the adapter must not
                              report the device as connected while idle in `bluetoothctl info <address>`
6  audit repeat:               on the next core release, re-diff the interfaces listed in section 2
```

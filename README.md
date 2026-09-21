[![GitHub Release](https://img.shields.io/github/release/acdcnow/Medisanabp_ble.svg?style=flat-square)](https://github.com/acdcnow/Medisanabp_ble/releases)
[![License](https://img.shields.io/github/license/acdcnow/Medisanabp_ble.svg?style=flat-square)](LICENSE)
[![hacs](https://img.shields.io/badge/HACS-custom-orange.svg?style=flat-square)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.9%2B-blue.svg?style=flat-square)](https://www.home-assistant.io)

# Medisana Blood Pressure BLE

Home Assistant custom integration for **Medisana blood pressure monitors with Bluetooth LE**
(Blood Pressure Service, `0x1810`). The monitor is discovered automatically, connects on demand and reports
every measurement to Home Assistant.

> **About this repository.** Maintained fork of
> [bkbilly/medisanabp_ble](https://github.com/bkbilly/medisanabp_ble) with a Home Assistant 2026.9 audit:
> the integration could not be installed on a clean Home Assistant (the manifest declared no requirements
> while importing libraries Home Assistant does not ship) and measurements could be republished as current
> after the first poll. See [CHANGELOG.md](CHANGELOG.md) for 1.4.0 and the
> [compatibility report](docs/Home-Assistant-2026.9-Compatibility-Report.md) for the evidence.

## Sensors

| Entity | Unit | Device class | Notes |
| --- | --- | --- | --- |
| Systolic | mmHg | pressure | |
| Diastolic | mmHg | pressure | |
| Pulse | bpm | – | |
| Measured Date | – | timestamp | device clock, interpreted in local time |
| Battery | % | battery | diagnostic, refreshed on every poll |
| Signal Strength | dBm | signal strength | diagnostic, disabled by default |

`available` stays `True` on purpose (the monitor is silent between measurements) and `assumed_state`
reflects whether the device is currently in range.

## How it works

* **Advertisements** (passive) provide discovery, the device name and the RSSI.
* **Active polling** opens a connection, reads the battery and subscribes to the Blood Pressure
  Measurement characteristic (`0x2A35`); the monitor answers with one frame per connection.
* Polling is triggered by advertisements, requires a **connectable** adapter or ESPHome proxy in range and
  is rate limited (`UPDATE_INTERVAL`, 10 s). The measurement itself arrives as a notification, with a 15 s
  timeout per attempt.

## Installation

Easiest install is via [HACS](https://hacs.xyz/) as a custom repository (the integration is not in the
default store):

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=acdcnow&repository=Medisanabp_ble&category=integration)

Manual: copy `custom_components/medisanabp_ble` into your `config/custom_components` folder and restart.

The device is autodiscovered as soon as an advertisement reaches any Bluetooth adapter or proxy. If it is
not, add the integration from **Settings → Devices & Services → Add integration → Medisana Blood Pressure
BLE**, which lists every discovered, not yet configured device.

## Documentation

| Document | Content |
| --- | --- |
| [Architecture Concept Document](docs/Architecture-Concept-Document.md) | scope, context, architecture decisions, runtime view |
| [System Design Document](docs/System-Design-Document.md) | data model, component and function reference, flows, extension guide |
| [Home Assistant 2026.9 Compatibility Report](docs/Home-Assistant-2026.9-Compatibility-Report.md) | audit against core 2026.9.3, findings and fixes |
| [GitDiagram](https://gitdiagram.com/acdcnow/Medisanabp_ble) | generated component graph of the default branch |
| [Changelog](CHANGELOG.md) | release history |

## Automations

```yaml
automation:
  - alias: Blood pressure measured
    triggers:
      - trigger: state
        entity_id: sensor.medisana_ee_ff_systolic
    actions:
      - action: notify.mobile_app_phone
        data:
          message: >-
            {{ states('sensor.medisana_ee_ff_systolic') }}/{{
            states('sensor.medisana_ee_ff_diastolic') }} mmHg,
            {{ states('sensor.medisana_ee_ff_pulse') }} bpm,
            measured {{ states('sensor.medisana_ee_ff_measured_date') }}
```

## Troubleshooting

| Symptom | Cause and what to do |
| --- | --- |
| `ModuleNotFoundError: No module named 'bluetooth_sensor_state_data'` | only affects versions before 1.4.0; update the integration |
| `No connectable device found for <address>` | the monitor is only seen by a passive-only scanner — add an ESPHome Bluetooth proxy or move the monitor closer to a connectable adapter |
| `Timeout getting measurement data` | the monitor did not answer within 15 s; measure again or move closer |
| `Could not read battery level: ...` | the battery characteristic could not be read; measurements are unaffected |
| Values do not change | a measurement only arrives when the monitor transmits one — check the *Measured Date* entity for its age |
| Entities are missing right after a restart | they are created with the first advertisement of the device |

## Development

```powershell
python testing\offline_smoke.py       # 20 checks, no Home Assistant, bleak or device needed
python testing\make_brand_assets.py   # regenerate the brand icons
```

Both scripts stub the Home Assistant and Bluetooth imports and therefore run on any machine with
Python 3.11+. The smoke test covers the advertisement and notification parsing, the complete poll lifecycle
including its error paths, the config flow, the entity mapping and the metadata rules that hassfest and
HACS enforce.

## Credits and license

Fork of [bkbilly/medisanabp_ble](https://github.com/bkbilly/medisanabp_ble). The vendored parser package
(`medisana_bp`) originates there and is kept as a standalone, Home Assistant agnostic module.
Released under the [MIT license](LICENSE).

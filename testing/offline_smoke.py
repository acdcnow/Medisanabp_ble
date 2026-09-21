"""Offline smoke test for the Medisanabp BLE integration.

Runs the real integration modules against stubbed Home Assistant, Bluetooth and
``sensor_state_data`` imports, so it needs neither Home Assistant, bleak, an
adapter nor a device:

    python testing/offline_smoke.py

Covered behaviour:

* advertisement parsing (device info, title, RSSI sensor injected by the library)
* the ``0x2A35`` decoder: measurement, short frame, unparseable date
* the poll lifecycle: battery read, subscribe, notification wait, and that the
  client is disconnected on *every* path (including failing ones)
* the regression that a later poll must wait for its own notification instead of
  reusing the previous measurement
* config entry setup/unload, including the coordinator keyword contract
* the config flow: discovery, confirmation, duplicate abort, manual picker
* ``SensorUpdate`` -> ``PassiveBluetoothDataUpdate`` conversion for every key

Plus the metadata rules hassfest/HACS enforce (manifest key order, matcher keys,
``hacs.json`` keys, translations parity, brand assets, version vs changelog) and
that the Mermaid blocks in ``docs/`` stay GitHub safe.

The stubs mirror the contracts of the real libraries as read from:
``homeassistant`` 2026.9.3 (``components/bluetooth``, ``helpers``,
``config_entries.py``), ``sensor_state_data`` 2.20.0, ``bluetooth_sensor_state_data``
1.9.0, ``bleak`` 3.0.2, ``bluetooth_data_tools`` and ``habluetooth``.
"""

from __future__ import annotations

import asyncio
import enum
import json
import logging
import pathlib
import re
import sys
import time
import types
from dataclasses import dataclass, field
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT_DIR = ROOT / "custom_components" / "medisanabp_ble"
DOCS_DIR = ROOT / "docs"
ADDRESS = "AA:BB:CC:DD:EE:FF"
OTHER_ADDRESS = "11:22:33:44:55:66"


# ---------------------------------------------------------------------------
# stub helper
# ---------------------------------------------------------------------------
def _module(name: str, *, package: bool = False, path: pathlib.Path | None = None, **attrs: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    if package:
        module.__path__ = [] if path is None else [str(path)]
    sys.modules[name] = module
    return module


# ---------------------------------------------------------------------------
# homeassistant stubs
# ---------------------------------------------------------------------------
class CoreState(enum.Enum):
    """Mirrors homeassistant.core.CoreState (only the members used here)."""

    not_running = "not_running"
    running = "running"
    stopping = "stopping"


def callback(func: Callable[..., Any]) -> Callable[..., Any]:
    """Mirrors homeassistant.core.callback (no-op for the test)."""
    return func


_module("homeassistant", package=True)
_module("homeassistant.components", package=True)
_module("homeassistant.helpers", package=True)
_module("homeassistant.util", package=True)
_module(
    "homeassistant.core",
    HomeAssistant=type("HomeAssistant", (), {}),
    CoreState=CoreState,
    callback=callback,
)


class Platform(enum.Enum):
    SENSOR = "sensor"


class EntityCategory(enum.Enum):
    DIAGNOSTIC = "diagnostic"


class UnitOfPressure(enum.Enum):
    MMHG = "mmHg"


_module(
    "homeassistant.const",
    Platform=Platform,
    EntityCategory=EntityCategory,
    UnitOfPressure=UnitOfPressure,
    PERCENTAGE="%",
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT="dBm",
    CONF_ADDRESS="address",
    ATTR_NAME="name",
    ATTR_MANUFACTURER="manufacturer",
    ATTR_MODEL="model",
    ATTR_CONNECTIONS="connections",
    ATTR_IDENTIFIERS="identifiers",
)


class SensorDeviceClass(enum.Enum):
    PRESSURE = "pressure"
    BATTERY = "battery"
    TIMESTAMP = "timestamp"
    SIGNAL_STRENGTH = "signal_strength"


class SensorStateClass(enum.Enum):
    MEASUREMENT = "measurement"


@dataclass
class SensorEntityDescription:
    """Mirrors homeassistant.components.sensor.SensorEntityDescription."""

    key: str
    native_unit_of_measurement: str | None = None
    device_class: Any = None
    state_class: Any = None
    icon: str | None = None
    entity_category: Any = None
    entity_registry_enabled_default: bool = True


class SensorEntity:
    """Marker base class for homeassistant.components.sensor.SensorEntity."""


_module(
    "homeassistant.components.sensor",
    SensorDeviceClass=SensorDeviceClass,
    SensorStateClass=SensorStateClass,
    SensorEntityDescription=SensorEntityDescription,
    SensorEntity=SensorEntity,
)


class BluetoothScanningMode(enum.Enum):
    PASSIVE = "passive"
    ACTIVE = "active"


class BluetoothServiceInfoBleak:
    """Marker base class; the tests use FakeServiceInfo."""


STUB_STATE: dict[str, Any] = {"discovered": [], "ble_devices": {}}


def async_ble_device_from_address(hass: Any, address: str, connectable: bool = True) -> Any:
    """Mirrors components.bluetooth.api.async_ble_device_from_address."""
    return STUB_STATE["ble_devices"].get(address)


def async_discovered_service_info(hass: Any, connectable: bool = True) -> list[Any]:
    """Mirrors habluetooth: connectable=False is the superset of all scanners."""
    if connectable:
        return [info for info in STUB_STATE["discovered"] if info.connectable]
    return list(STUB_STATE["discovered"])


_module(
    "homeassistant.components.bluetooth",
    BluetoothScanningMode=BluetoothScanningMode,
    BluetoothServiceInfoBleak=BluetoothServiceInfoBleak,
    async_ble_device_from_address=async_ble_device_from_address,
    async_discovered_service_info=async_discovered_service_info,
)


class ActiveBluetoothProcessorCoordinator:
    """Records the constructor arguments.

    ``KEYWORD_ONLY`` is the parameter list of
    homeassistant/components/bluetooth/active_update_processor.py as of core
    2026.9.3; a call with an unknown keyword fails the signature check.
    """

    KEYWORD_ONLY = frozenset(
        {
            "address",
            "mode",
            "update_method",
            "needs_poll_method",
            "poll_method",
            "poll_debouncer",
            "connectable",
            "scan_interval",
            "scan_duration",
        }
    )
    instances: list["ActiveBluetoothProcessorCoordinator"] = []

    # the real class is generic (ActiveBluetoothProcessorCoordinator[_DataT])
    __class_getitem__ = classmethod(lambda cls, _item: cls)

    def __init__(self, hass: Any, logger: logging.Logger, **kwargs: Any) -> None:
        self.hass = hass
        self.logger = logger
        self.kwargs = kwargs
        self.available = True
        self.started = False
        self.processors: list[tuple[Any, Any]] = []
        ActiveBluetoothProcessorCoordinator.instances.append(self)

    def async_start(self) -> Callable[[], None]:
        self.started = True
        return lambda: None

    def async_register_processor(
        self, processor: Any, entity_description_class: Any = None
    ) -> Callable[[], None]:
        self.processors.append((processor, entity_description_class))
        return lambda: None


_module(
    "homeassistant.components.bluetooth.active_update_processor",
    ActiveBluetoothProcessorCoordinator=ActiveBluetoothProcessorCoordinator,
)


@dataclass(frozen=True)
class PassiveBluetoothEntityKey:
    """Mirrors components.bluetooth.passive_update_processor.PassiveBluetoothEntityKey."""

    key: str
    device_id: str | None = None


@dataclass
class PassiveBluetoothDataUpdate:
    """Mirrors PassiveBluetoothDataUpdate (generic over the value type)."""

    devices: dict[Any, Any] = field(default_factory=dict)
    entity_descriptions: dict[Any, Any] = field(default_factory=dict)
    entity_names: dict[Any, Any] = field(default_factory=dict)
    entity_data: dict[Any, Any] = field(default_factory=dict)

    def update(self, new_data: "PassiveBluetoothDataUpdate") -> set[Any]:
        """Merge new data and return the changed entity keys (mirrors core)."""
        changed: set[Any] = set()
        for incoming, current in (
            (new_data.devices, self.devices),
            (new_data.entity_descriptions, self.entity_descriptions),
            (new_data.entity_names, self.entity_names),
            (new_data.entity_data, self.entity_data),
        ):
            for key, data in incoming.items():
                if current.get(key, _UNDEFINED) != data:
                    changed.add(key)
                    current[key] = data
        return changed


_UNDEFINED = object()


class PassiveBluetoothDataProcessor:
    """Mirrors PassiveBluetoothDataProcessor for the parts the platform uses.

    The accumulated data, the backwards compatible attributes, the listener
    bookkeeping and the entity creation match
    homeassistant/components/bluetooth/passive_update_processor.py.
    """

    def __init__(self, update_method: Callable[..., Any], restore_key: str | None = None) -> None:
        self.update_method = update_method
        self.restore_key = restore_key
        self.last_update_success = True
        self._available = True
        self.data = PassiveBluetoothDataUpdate()
        for attribute in ("entity_names", "entity_data", "entity_descriptions", "devices"):
            setattr(self, attribute, getattr(self.data, attribute))
        self._listeners: list[Callable[[Any], None]] = []
        self.entity_class: Any = None

    @property
    def available(self) -> bool:
        """Mirrors coordinator availability and the last update result."""
        return self._available and self.last_update_success

    def async_add_listener(self, update_callback: Callable[[Any], None]) -> Callable[[], None]:
        def remove_listener() -> None:
            self._listeners.remove(update_callback)

        self._listeners.append(update_callback)
        return remove_listener

    def async_update_listeners(self, data: Any) -> None:
        for update_callback in list(self._listeners):
            update_callback(data)

    def async_handle_update(self, update: Any) -> None:
        """Mirrors the coordinator -> processor hand-off."""
        new_data = self.update_method(update)
        if not isinstance(new_data, PassiveBluetoothDataUpdate):
            raise TypeError(f"update method returned {new_data!r}")
        self.data.update(new_data)
        self.async_update_listeners(new_data)

    def async_add_entities_listener(
        self, entity_class: Any, async_add_entities: Callable[[list[Any]], None]
    ) -> Callable[[], None]:
        """Mirrors the core implementation: one entity per new entity key."""
        self.entity_class = entity_class
        created: set[Any] = set()

        def _async_add_or_update_entities(data: PassiveBluetoothDataUpdate | None) -> None:
            if data is None or created.issuperset(data.entity_descriptions):
                return
            entities = []
            for entity_key, description in data.entity_descriptions.items():
                if entity_key not in created:
                    entities.append(entity_class(self, entity_key, description))
                    created.add(entity_key)
            if entities:
                async_add_entities(entities)

        return self.async_add_listener(_async_add_or_update_entities)


class PassiveBluetoothProcessorEntity:
    """Reduced PassiveBluetoothProcessorEntity: entity_key, description, processor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, processor: Any, entity_key: Any, description: Any, context: Any = None) -> None:
        self.processor = processor
        self.entity_key = entity_key
        self.entity_description = description
        self.processor_context = context
        if (name := processor.entity_names.get(entity_key)) is not None:
            self._attr_name = name


_module(
    "homeassistant.components.bluetooth.passive_update_processor",
    PassiveBluetoothEntityKey=PassiveBluetoothEntityKey,
    PassiveBluetoothDataUpdate=PassiveBluetoothDataUpdate,
    PassiveBluetoothDataProcessor=PassiveBluetoothDataProcessor,
    PassiveBluetoothProcessorEntity=PassiveBluetoothProcessorEntity,
)


class AddConfigEntryEntitiesCallback:
    """Mirrors the typing Protocol of the same name."""


_module(
    "homeassistant.helpers.entity_platform",
    AddConfigEntryEntitiesCallback=AddConfigEntryEntitiesCallback,
    AddEntitiesCallback=AddConfigEntryEntitiesCallback,
)
_module("homeassistant.helpers.device_registry", DeviceInfo=dict, CONNECTION_BLUETOOTH="bluetooth")


def sensor_device_info_to_hass_device_info(sensor_device_info: Any) -> dict[str, Any]:
    """Mirrors homeassistant.helpers.sensor.sensor_device_info_to_hass_device_info."""
    device_info: dict[str, Any] = {}
    if sensor_device_info.name is not None:
        device_info["name"] = sensor_device_info.name
    if sensor_device_info.manufacturer is not None:
        device_info["manufacturer"] = sensor_device_info.manufacturer
    if sensor_device_info.model is not None:
        device_info["model"] = sensor_device_info.model
    return device_info


_module("homeassistant.helpers.sensor", sensor_device_info_to_hass_device_info=sensor_device_info_to_hass_device_info)


class AbortFlow(Exception):
    """Mirrors homeassistant.data_entry_flow.AbortFlow."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ConfigEntry:
    """Reduced ConfigEntry: identity, ignored flag, runtime_data, unload callbacks."""

    def __init__(
        self,
        entry_id: str = "entry-id",
        unique_id: str | None = None,
        domain: str = "medisanabp_ble",
        ignored: bool = False,
    ) -> None:
        self.entry_id = entry_id
        self.unique_id = unique_id
        self.domain = domain
        self.ignored = ignored
        self.runtime_data: Any = None
        self.unload_callbacks: list[Callable[[], None]] = []

    __class_getitem__ = classmethod(lambda cls, _item: cls)

    def async_on_unload(self, func: Callable[[], None]) -> None:
        self.unload_callbacks.append(func)


class ConfigEntryManager:
    """Reduced ConfigEntries manager."""

    def __init__(self) -> None:
        self.entries: list[ConfigEntry] = []
        self.forwarded: list[tuple[Any, ...]] = []
        self.unloaded: list[tuple[Any, ...]] = []

    def async_entries(self, domain: str | None = None, include_ignore: bool = True) -> list[ConfigEntry]:
        return [
            entry
            for entry in self.entries
            if (domain is None or entry.domain == domain) and (include_ignore or not entry.ignored)
        ]

    async def async_forward_entry_setups(self, entry: ConfigEntry, platforms: Any) -> None:
        self.forwarded.append(tuple(platforms))

    async def async_unload_platforms(self, entry: ConfigEntry, platforms: Any) -> bool:
        self.unloaded.append(tuple(platforms))
        return True


class ConfigFlow:
    """Reduced ConfigFlow base for the steps the integration implements."""

    VERSION = 1
    domain: str | None = None

    def __init_subclass__(cls, *, domain: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.domain = domain

    def __init__(self) -> None:
        self.hass: Any = None
        self.context: dict[str, Any] = {}
        self.unique_id: str | None = None

    def _entries(self) -> list[ConfigEntry]:
        return self.hass.config_entries.async_entries(self.domain, include_ignore=True)

    async def async_set_unique_id(self, unique_id: str, raise_on_progress: bool = True) -> None:
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self) -> None:
        for entry in self._entries():
            if entry.unique_id == self.unique_id:
                raise AbortFlow("already_configured")

    def _async_current_ids(self, include_ignore: bool = True) -> set[str | None]:
        """Mirrors core: the ids of configured entries, optionally with ignored ones."""
        return {
            entry.unique_id
            for entry in self.hass.config_entries.async_entries(self.domain, include_ignore=include_ignore)
        }

    def _set_confirm_only(self) -> None:
        """Mirrors core: the flag is stored in the flow context, not on the flow."""
        self.context["confirm_only"] = True

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: Any = None,
        description_placeholders: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "description_placeholders": description_placeholders,
            "context": self.context,
            "confirm_only": self.context.get("confirm_only", False),
        }

    def async_create_entry(self, *, title: str | None = None, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": "create_entry", "title": title, "data": data}

    def async_abort(self, *, reason: str) -> dict[str, Any]:
        return {"type": "abort", "reason": reason}


_module(
    "homeassistant.config_entries",
    ConfigEntry=ConfigEntry,
    ConfigFlow=ConfigFlow,
    ConfigFlowResult=dict,
    AbortFlow=AbortFlow,
)


# ---------------------------------------------------------------------------
# voluptuous stub (config_flow only builds a schema)
# ---------------------------------------------------------------------------
class _Required:
    def __init__(self, key: str) -> None:
        self.key = key

    def __str__(self) -> str:
        return self.key


class _In:
    def __init__(self, options: Any) -> None:
        self.options = set(options)


class _Schema:
    def __init__(self, schema: dict[Any, Any]) -> None:
        self.data = {str(key): value for key, value in schema.items()}


_module("voluptuous", Schema=_Schema, Required=_Required, In=_In)


# ---------------------------------------------------------------------------
# sensor_state_data / bluetooth_sensor_state_data stubs
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeviceKey:
    """Mirrors sensor_state_data.device.DeviceKey."""

    key: str
    device_id: str | None = None


class _SensorDeviceClass(enum.Enum):
    PRESSURE = "pressure"
    BATTERY = "battery"
    SIGNAL_STRENGTH = "signal_strength"
    TEMPERATURE = "temperature"


class _BinarySensorDeviceClass(enum.Enum):
    PROBLEM = "problem"


class Units(enum.Enum):
    """Mirrors the members of sensor_state_data.units.Units that are used."""

    PRESSURE_MMHG = "mmHg"
    PERCENTAGE = "%"
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT = "dBm"


@dataclass
class SensorValue:
    name: str
    device_key: DeviceKey
    native_value: Any


@dataclass
class SensorDescription:
    device_key: DeviceKey
    native_unit_of_measurement: Any = None
    device_class: Any = None


@dataclass
class SensorDeviceInfo:
    name: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    sw_version: str | None = None
    hw_version: str | None = None


@dataclass(frozen=True)
class SensorUpdate:
    """Mirrors sensor_state_data.data.SensorUpdate."""

    title: str | None
    devices: dict[Any, Any]
    entity_descriptions: dict[Any, Any] = field(default_factory=dict)
    entity_values: dict[Any, Any] = field(default_factory=dict)
    binary_entity_descriptions: dict[Any, Any] = field(default_factory=dict)
    binary_entity_values: dict[Any, Any] = field(default_factory=dict)
    events: dict[Any, Any] = field(default_factory=dict)


_module(
    "sensor_state_data",
    DeviceKey=DeviceKey,
    SensorDeviceClass=_SensorDeviceClass,
    BinarySensorDeviceClass=_BinarySensorDeviceClass,
    Units=Units,
    SensorValue=SensorValue,
    SensorDescription=SensorDescription,
    SensorDeviceInfo=SensorDeviceInfo,
    SensorUpdate=SensorUpdate,
)
_module("sensor_state_data.enum", StrEnum=enum.StrEnum)


class BluetoothData:
    """Mirrors bluetooth_sensor_state_data.BluetoothData + the SensorData API.

    ``update()`` calls ``_start_update``, injects the RSSI sensor and finishes
    with ``_finish_update()``, exactly like the real 1.9.0 implementation. The
    update dictionaries are only reset for events, so accumulated values keep
    being reported - the behaviour the integration relies on.
    """

    def __init__(self) -> None:
        self._title: str | None = None
        self._device_id_info: dict[Any, SensorDeviceInfo] = {}
        self._device_id_to_name: dict[Any, str] = {}
        self._device_id_to_type: dict[Any, str] = {}
        self._sensor_values: dict[Any, SensorValue] = {}
        self._sensor_values_updates: dict[Any, SensorValue] = {}
        self._sensor_descriptions: dict[Any, SensorDescription] = {}
        self._sensor_descriptions_updates: dict[Any, SensorDescription] = {}

    # -- SensorData API ----------------------------------------------------
    def set_title(self, title: str) -> None:
        self._title = title

    @property
    def title(self) -> str | None:
        return self._title

    def _device_info(self, device_id: str | None) -> SensorDeviceInfo:
        if device_id not in self._device_id_info:
            self._device_id_info[device_id] = SensorDeviceInfo()
        return self._device_id_info[device_id]

    def set_device_name(self, name: str, device_id: str | None = None) -> None:
        self._device_id_to_name[device_id] = name
        self._device_info(device_id).name = name

    def set_device_type(self, device_type: str, device_id: str | None = None) -> None:
        self._device_id_to_type[device_id] = device_type
        self._device_info(device_id).model = device_type

    def set_device_manufacturer(self, manufacturer: str, device_id: str | None = None) -> None:
        self._device_info(device_id).manufacturer = manufacturer

    def get_device_name(self, device_id: str | None = None) -> str | None:
        return self._device_id_to_name.get(device_id) or self._device_id_to_type.get(device_id)

    def update_sensor(
        self,
        key: str,
        native_unit_of_measurement: Any,
        native_value: Any,
        device_class: Any = None,
        name: str | None = None,
        device_id: str | None = None,
    ) -> None:
        device_key = DeviceKey(key, device_id)
        self._sensor_values_updates[device_key] = SensorValue(
            name=name or key.replace("_", " ").title(),
            device_key=device_key,
            native_value=native_value,
        )
        self._sensor_descriptions_updates[device_key] = SensorDescription(
            device_key=device_key,
            native_unit_of_measurement=native_unit_of_measurement,
            device_class=device_class,
        )

    def _finish_update(self) -> SensorUpdate:
        self._sensor_values.update(self._sensor_values_updates)
        self._sensor_descriptions.update(self._sensor_descriptions_updates)
        return SensorUpdate(
            title=self._title,
            devices=self._device_id_info,
            entity_descriptions=self._sensor_descriptions_updates,
            entity_values=self._sensor_values_updates,
        )

    # -- BluetoothData API -------------------------------------------------
    def _start_update(self, data: Any) -> None:
        raise NotImplementedError

    def supported(self, data: Any) -> bool:
        self._start_update(data)
        return bool(self._device_id_to_type)

    def update_signal_strength(self, native_value: int | float) -> None:
        for device_id in self._device_id_to_type:
            self.update_sensor(
                key="signal_strength",
                native_unit_of_measurement=Units.SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
                native_value=native_value,
                device_class=_SensorDeviceClass.SIGNAL_STRENGTH,
                name="Signal Strength",
                device_id=device_id,
            )

    def update(self, data: Any) -> SensorUpdate:
        self._start_update(data)
        self.update_signal_strength(data.rssi)
        return self._finish_update()


_module("bluetooth_sensor_state_data", BluetoothData=BluetoothData)


def short_address(address: str, divider: str = ":") -> str:
    """Mirrors bluetooth_data_tools.short_address."""
    split_address = address.replace("-", divider).split(divider)
    return divider.join(split_address[-2:])


_module("bluetooth_data_tools", short_address=short_address)


class BluetoothServiceInfo:
    """Marker base class, mirrors habluetooth.BluetoothServiceInfo."""


_module("habluetooth", BluetoothServiceInfo=BluetoothServiceInfo, BluetoothServiceInfoBleak=BluetoothServiceInfoBleak)


@dataclass
class BLEDevice:
    """Mirrors bleak.backends.device.BLEDevice (address/name are what is used)."""

    address: str
    name: str | None = None


class BleakError(Exception):
    """Mirrors bleak.exc.BleakError."""


_module("bleak", BLEDevice=BLEDevice)
_module("bleak.exc", BleakError=BleakError)


class BleakClientWithServiceCache:
    """Marker class that the poll asserts on."""


def establish_connection(*args: Any, **kwargs: Any) -> Any:
    """Placeholder; each poll test replaces it with a fake."""
    raise NotImplementedError("establish_connection must be patched by the test")


_module(
    "bleak_retry_connector",
    BleakClientWithServiceCache=BleakClientWithServiceCache,
    establish_connection=establish_connection,
)


# ---------------------------------------------------------------------------
# load the real integration
# ---------------------------------------------------------------------------
_custom_components = types.ModuleType("custom_components")
_custom_components.__path__ = [str(COMPONENT_DIR.parent)]
sys.modules["custom_components"] = _custom_components

from custom_components.medisanabp_ble import (  # noqa: E402
    async_setup_entry,
    async_unload_entry,
)
from custom_components.medisanabp_ble import config_flow as config_flow_module  # noqa: E402
from custom_components.medisanabp_ble import device as device_module  # noqa: E402
from custom_components.medisanabp_ble import sensor as sensor_module  # noqa: E402
from custom_components.medisanabp_ble.medisana_bp import (  # noqa: E402
    MedisanaBPBluetoothDeviceData,
    MedisanaBPSensor,
)
from custom_components.medisanabp_ble.medisana_bp import const as parser_const  # noqa: E402
from custom_components.medisanabp_ble.medisana_bp import parser as parser_module  # noqa: E402

PARSER_LOGGER = "custom_components.medisanabp_ble.medisana_bp.parser"


# ---------------------------------------------------------------------------
# check harness
# ---------------------------------------------------------------------------
CHECKS: list[tuple[str, Callable[[], Any]]] = []


def check(title: str) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
    def decorator(func: Callable[[], Any]) -> Callable[[], Any]:
        CHECKS.append((title, func))
        return func

    return decorator


def expect(condition: Any, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class LogCapture(logging.Handler):
    """Collects records so warnings can be asserted."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


# ---------------------------------------------------------------------------
# test doubles and helpers
# ---------------------------------------------------------------------------
@dataclass
class FakeServiceInfo(BluetoothServiceInfo):
    """A Bluetooth advertisement, as home_assistant_bluetooth would deliver it."""

    address: str = ADDRESS
    name: str | None = "Medisana"
    rssi: int = -70
    connectable: bool = True
    source: str = "hci0"
    time: float = field(default_factory=time.monotonic)
    device: Any = None

    def __post_init__(self) -> None:
        if self.device is None:
            self.device = BLEDevice(self.address)


def measurement_frame(
    systolic: int = 128,
    diastolic: int = 84,
    map_value: int = 99,
    pulse: int = 72,
    measured: tuple[int, int, int, int, int, int] = (2026, 9, 22, 21, 5, 0),
    user: int = 1,
) -> bytearray:
    """Build a standard 0x2A35 Blood Pressure Measurement frame."""
    frame = bytearray(17)
    frame[0] = 0x1E  # flags: kPa? no - unit mmHg, timestamp present, pulse present
    frame[1:3] = systolic.to_bytes(2, "little")
    frame[3:5] = diastolic.to_bytes(2, "little")
    frame[5:7] = map_value.to_bytes(2, "little")
    year, month, day, hour, minute, second = measured
    frame[7:9] = year.to_bytes(2, "little")
    frame[9] = month
    frame[10] = day
    frame[11] = hour
    frame[12] = minute
    frame[13] = second
    frame[14:16] = pulse.to_bytes(2, "little")
    frame[16] = user
    return frame


class FakeServices:
    """Mirrors components/bluetooth/../bleak service collection lookup."""

    def __init__(self, battery_characteristic: bool) -> None:
        self._battery_characteristic = battery_characteristic

    def get_characteristic(self, uuid: str) -> Any:
        return "battery-characteristic" if self._battery_characteristic else None


class FakeClient:
    """A BleakClient stand-in that records the poll's transport usage."""

    def __init__(
        self,
        *,
        battery: int = 77,
        battery_characteristic: bool = True,
        read_error: Exception | None = None,
        notify_error: Exception | None = None,
        notify_payload: Any = None,
    ) -> None:
        self.battery = battery
        self.read_error = read_error
        self.notify_error = notify_error
        self.notify_payload = notify_payload
        self.services = FakeServices(battery_characteristic)
        self.read_calls = 0
        self.subscriptions: list[str] = []
        self.stop_notify_calls = 0
        self.disconnect_calls = 0

    async def read_gatt_char(self, characteristic: Any) -> bytearray:
        self.read_calls += 1
        if self.read_error is not None:
            raise self.read_error
        return bytearray([self.battery])

    async def start_notify(self, characteristic: str, callback: Callable[..., Any]) -> None:
        if self.notify_error is not None:
            raise self.notify_error
        self.subscriptions.append(characteristic)
        if self.notify_payload is not None:
            # bleak calls a plain function inline with (characteristic, data)
            callback(characteristic, self.notify_payload)

    async def stop_notify(self, characteristic: str) -> None:
        self.stop_notify_calls += 1

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


def new_device_data() -> Any:
    """Create a parser instance that already saw one advertisement."""
    data = MedisanaBPBluetoothDeviceData()
    data.update(FakeServiceInfo())
    return data


def run_poll(
    data: Any = None,
    *,
    payload: Any = None,
    timeout: float | None = None,
    **client_kwargs: Any,
) -> tuple[Any, FakeClient, list[Any], float]:
    """Run one real ``async_poll`` against a fake client.

    Returns the produced SensorUpdate, the fake client, the establish_connection
    arguments and the wall clock time the poll needed.
    """
    data = data or new_device_data()
    client = FakeClient(notify_payload=payload, **client_kwargs)
    calls: list[Any] = []

    async def fake_establish_connection(*args: Any) -> FakeClient:
        calls.append(args)
        return client

    original_establish = parser_module.establish_connection
    original_timeout = parser_module.NOTIFICATION_TIMEOUT
    parser_module.establish_connection = fake_establish_connection
    if timeout is not None:
        parser_module.NOTIFICATION_TIMEOUT = timeout
    try:
        started = time.monotonic()
        update = asyncio.run(data.async_poll(BLEDevice(ADDRESS)))
        elapsed = time.monotonic() - started
    finally:
        parser_module.establish_connection = original_establish
        parser_module.NOTIFICATION_TIMEOUT = original_timeout
    return update, client, calls, elapsed


class FakeHass:
    """Reduced HomeAssistant with the config entry manager."""

    def __init__(self) -> None:
        self.state = CoreState.running
        self.data: dict[str, Any] = {}
        self.config_entries = ConfigEntryManager()


def new_flow(hass: FakeHass) -> Any:
    """Create a config flow the way the flow manager does (hass + context)."""
    flow = config_flow_module.MedisanaBPConfigFlow()
    flow.hass = hass
    flow.context = {}
    return flow


# ---------------------------------------------------------------------------
# parser behaviour
# ---------------------------------------------------------------------------
@check("advertisement sets device info, title and the library-provided RSSI sensor")
def check_advertisement() -> None:
    data = MedisanaBPBluetoothDeviceData()
    update = data.update(FakeServiceInfo(address=ADDRESS, name="Medisana", rssi=-61))

    expect(data.title == "Medisana EE:FF", f"unexpected title {data.title!r}")
    expect(data.get_device_name() == "Medisana EE:FF", "device name must carry the short address")
    device_info = data._device_id_info[None]
    expect(device_info.manufacturer == "Medisana", "manufacturer must be set")
    expect(device_info.model == "Blood Pressure Measurement", "model must be set")
    rssi = update.entity_values[DeviceKey("signal_strength", None)]
    expect(rssi.native_value == -61, "the RSSI sensor is injected by bluetooth_sensor_state_data")
    expect(
        update.entity_descriptions[DeviceKey("signal_strength", None)].native_unit_of_measurement
        == Units.SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        "RSSI unit must be dBm",
    )
    expect(data.supported(FakeServiceInfo()) is True, "supported() must be true for a known device")

    nameless = MedisanaBPBluetoothDeviceData()
    nameless.update(FakeServiceInfo(name=None))
    expect(
        nameless.title == "Medisana BP EE:FF",
        f"a nameless advertisement must not produce 'None ...' (got {nameless.title!r})",
    )


@check("measurement notification publishes systolic, diastolic, pulse and measured date")
def check_notification() -> None:
    data = new_device_data()
    data.notification_handler(None, measurement_frame(systolic=128, diastolic=84, pulse=72))

    values = data._sensor_values_updates
    expect(values[DeviceKey("systolic", None)].native_value == 128, "systolic")
    expect(values[DeviceKey("diastolic", None)].native_value == 84, "diastolic")
    expect(values[DeviceKey("pulse", None)].native_value == 72, "pulse")
    expect(values[DeviceKey("systolic", None)].name == "Systolic", "systolic name")
    expect(
        values[DeviceKey("systolic", None)].device_key == DeviceKey("systolic", None),
        "values must be keyed by the parser key",
    )
    measured = values[DeviceKey("timestamp", None)].native_value
    expect(
        (measured.year, measured.month, measured.day, measured.hour, measured.minute)
        == (2026, 9, 22, 21, 5),
        f"measured date decoded incorrectly: {measured}",
    )
    expect(measured.tzinfo is not None, "the measured date must be timezone aware")
    expect(data._event.is_set(), "the notification must release the poll wait")


@check("short and unparseable frames are rejected without raising")
def check_malformed_frames() -> None:
    capture = LogCapture()
    logger = logging.getLogger(PARSER_LOGGER)
    logger.addHandler(capture)
    logger.setLevel(logging.DEBUG)
    try:
        data = new_device_data()
        published = set(data._sensor_values_updates)
        data.notification_handler(None, bytearray([0x1E, 0x80]))
        expect(
            set(data._sensor_values_updates) == published,
            "a short frame must not publish any sensor value",
        )
        expect(not data._event.is_set(), "a short frame must not release the poll")
        expect(
            any(record.levelno == logging.WARNING for record in capture.records),
            "a short frame must be logged as a warning",
        )

        broken_date = measurement_frame()
        broken_date[9] = 13  # month 13
        data.notification_handler(None, broken_date)
        expect(
            DeviceKey("systolic", None) in data._sensor_values_updates,
            "the pressure values must survive an unparseable date",
        )
        expect(
            DeviceKey("timestamp", None) not in data._sensor_values_updates,
            "no date sensor may be published for an invalid date",
        )
    finally:
        logger.removeHandler(capture)


@check("poll reads the battery, subscribes, and disconnects exactly once")
def check_poll_happy_path() -> None:
    update, client, calls, _ = run_poll(payload=measurement_frame())

    expect(client.disconnect_calls == 1, f"disconnect called {client.disconnect_calls} times")
    expect(client.stop_notify_calls == 0, "notifications stop on disconnect, stop_notify is redundant")
    expect(
        client.subscriptions == [parser_const.CHARACTERISTIC_BLOOD_PRESSURE],
        f"subscribed to {client.subscriptions}",
    )
    expect(calls[0][0] is BleakClientWithServiceCache, "the service caching client must be used")
    expect(calls[0][2] == ADDRESS, "the address must be passed to establish_connection")
    expect(
        update.entity_values[DeviceKey("battery_percent", None)].native_value == 77,
        "the battery must be published",
    )
    expect(
        update.entity_descriptions[DeviceKey("battery_percent", None)].native_unit_of_measurement
        == Units.PERCENTAGE,
        "the battery unit must be percent",
    )
    expect(
        update.entity_values[DeviceKey("systolic", None)].native_value == 128,
        "the measurement must be published",
    )


@check("a failing battery read still disconnects and keeps the measurement")
def check_poll_battery_error() -> None:
    update, client, _, _ = run_poll(payload=measurement_frame(), read_error=BleakError("battery read failed"))

    expect(client.disconnect_calls == 1, "the connection must be released after a battery read error")
    expect(DeviceKey("battery_percent", None) not in update.entity_values, "no battery value expected")
    expect(
        update.entity_values[DeviceKey("systolic", None)].native_value == 128,
        "the measurement must still be reported",
    )


@check("an unexpected error propagates but never leaks the connection")
def check_poll_unexpected_error() -> None:
    data = new_device_data()
    client = FakeClient(read_error=RuntimeError("boom"))

    async def fake_establish_connection(*args: Any) -> FakeClient:
        return client

    original = parser_module.establish_connection
    parser_module.establish_connection = fake_establish_connection
    raised: Exception | None = None
    try:
        asyncio.run(data.async_poll(BLEDevice(ADDRESS)))
    except RuntimeError as err:
        raised = err
    finally:
        parser_module.establish_connection = original

    expect(raised is not None, "an unknown error must propagate to the coordinator")
    expect(client.disconnect_calls == 1, "the connection must be released even on unexpected errors")


@check("a missing battery characteristic does not stop the measurement")
def check_poll_missing_characteristic() -> None:
    update, client, _, _ = run_poll(payload=measurement_frame(), battery_characteristic=False)

    expect(client.disconnect_calls == 1, "the connection must be released")
    expect(client.subscriptions, "notifications must still be enabled")
    expect(DeviceKey("battery_percent", None) not in update.entity_values, "no battery value expected")
    expect(
        update.entity_values[DeviceKey("systolic", None)].native_value == 128,
        "the measurement must still be reported",
    )


@check("a subscribe failure returns the battery and disconnects")
def check_poll_subscribe_error() -> None:
    update, client, _, _ = run_poll(payload=measurement_frame(), notify_error=BleakError("notify failed"))

    expect(client.disconnect_calls == 1, "the connection must be released")
    expect(client.subscriptions == [], "no subscription must be recorded")
    expect(
        update.entity_values[DeviceKey("battery_percent", None)].native_value == 77,
        "the battery read before the subscription must be reported",
    )
    expect(
        DeviceKey("systolic", None) not in update.entity_values,
        "no measurement can be expected without a subscription",
    )


@check("every poll waits for its own notification (regression: reused event)")
def check_poll_waits_each_time() -> None:
    data = new_device_data()

    first_update, first_client, _, first_elapsed = run_poll(data, payload=measurement_frame(), timeout=0.05)
    expect(first_client.disconnect_calls == 1, "first poll must disconnect")
    expect(
        first_elapsed < 0.05,
        f"a poll that receives data must not wait for the timeout (took {first_elapsed:.3f}s)",
    )
    expect(first_update.entity_values[DeviceKey("systolic", None)].native_value == 128, "first measurement")

    # Same parser instance, but this time the device stays silent: the poll must
    # wait for its own notification instead of returning immediately because the
    # event of the previous poll is still set.
    second_update, second_client, _, second_elapsed = run_poll(data, timeout=0.05)
    expect(second_client.disconnect_calls == 1, "second poll must disconnect")
    expect(
        second_elapsed >= 0.04,
        f"the second poll reused the previous notification event (took {second_elapsed:.3f}s)",
    )
    expect(second_update is not None, "a timed out poll must still return the accumulated data")


# ---------------------------------------------------------------------------
# integration wiring
# ---------------------------------------------------------------------------
@check("config entry setup wires the coordinator with a valid 2026.9 contract")
def check_setup_entry() -> None:
    hass = FakeHass()
    entry = ConfigEntry(entry_id="entry-1", unique_id=ADDRESS)

    expect(asyncio.run(async_setup_entry(hass, entry)) is True, "setup must succeed")

    coordinator = entry.runtime_data
    expect(coordinator is not None, "the coordinator must be stored in entry.runtime_data")
    kwargs = coordinator.kwargs
    unknown = set(kwargs) - ActiveBluetoothProcessorCoordinator.KEYWORD_ONLY
    expect(not unknown, f"the coordinator does not accept {sorted(unknown)} in HA 2026.9")
    expect(
        {"address", "mode", "update_method", "needs_poll_method", "poll_method"} <= set(kwargs),
        f"missing coordinator arguments: {sorted(kwargs)}",
    )
    expect(kwargs["address"] == ADDRESS, "the unique id must be the address")
    expect(kwargs["mode"] is BluetoothScanningMode.PASSIVE, "the coordinator must scan passively")
    expect(kwargs["connectable"] is False, "advertisements from passive-only scanners must be accepted")
    expect(hass.config_entries.forwarded == [(Platform.SENSOR,)], "the sensor platform must be forwarded")
    expect(coordinator.started, "the coordinator must be started after the platforms")
    expect(len(entry.unload_callbacks) == 1, "async_start must be registered via async_on_unload")


@check("the poll decision needs a running core, a due poll and a connectable device")
def check_needs_poll() -> None:
    hass = FakeHass()
    entry = ConfigEntry(unique_id=ADDRESS)
    asyncio.run(async_setup_entry(hass, entry))
    needs_poll = entry.runtime_data.kwargs["needs_poll_method"]

    STUB_STATE["ble_devices"].clear()
    expect(needs_poll(FakeServiceInfo(), None) is False, "no connectable device is reachable")

    STUB_STATE["ble_devices"][ADDRESS] = BLEDevice(ADDRESS)
    expect(needs_poll(FakeServiceInfo(), None) is True, "the first poll must be due")
    expect(needs_poll(FakeServiceInfo(), 5.0) is False, "a recent poll must not trigger another one")
    expect(needs_poll(FakeServiceInfo(), 11.0) is True, "a poll older than UPDATE_INTERVAL is due")

    hass.state = CoreState.not_running
    expect(needs_poll(FakeServiceInfo(), None) is False, "no polling while the core is not running")
    hass.state = CoreState.running
    STUB_STATE["ble_devices"].clear()


@check("the poll method resolves a connectable device and fails clearly otherwise")
def check_poll_method() -> None:
    hass = FakeHass()
    entry = ConfigEntry(unique_id=ADDRESS)
    asyncio.run(async_setup_entry(hass, entry))
    coordinator = entry.runtime_data
    poll_method = coordinator.kwargs["poll_method"]
    data = coordinator.kwargs["update_method"].__self__

    async def fake_poll(device: Any) -> tuple[str, str]:
        return ("polled", device.address)

    original = data.async_poll
    data.async_poll = fake_poll
    try:
        expect(
            asyncio.run(poll_method(FakeServiceInfo(connectable=True))) == ("polled", ADDRESS),
            "a connectable advertisement is used directly",
        )

        STUB_STATE["ble_devices"][ADDRESS] = BLEDevice(ADDRESS)
        expect(
            asyncio.run(poll_method(FakeServiceInfo(connectable=False))) == ("polled", ADDRESS),
            "a passive-only advertisement must be upgraded to a connectable device",
        )

        STUB_STATE["ble_devices"].clear()
        error: str | None = None
        try:
            asyncio.run(poll_method(FakeServiceInfo(connectable=False)))
        except RuntimeError as err:
            error = str(err)
        expect(
            error is not None and "No connectable device" in error,
            f"an unreachable device must raise a clear RuntimeError, got {error!r}",
        )
    finally:
        data.async_poll = original


@check("config entry unload unloads the platforms")
def check_unload_entry() -> None:
    hass = FakeHass()
    entry = ConfigEntry(unique_id=ADDRESS)
    asyncio.run(async_setup_entry(hass, entry))

    expect(asyncio.run(async_unload_entry(hass, entry)) is True, "unload must succeed")
    expect(hass.config_entries.unloaded == [(Platform.SENSOR,)], "the sensor platform must be unloaded")


# ---------------------------------------------------------------------------
# config flow
# ---------------------------------------------------------------------------
@check("config flow discovers, confirms and rejects an already configured device")
def check_config_flow_discovery() -> None:
    hass = FakeHass()
    flow = new_flow(hass)

    result = asyncio.run(flow.async_step_bluetooth(FakeServiceInfo(name="Medisana")))
    expect(result["type"] == "form", f"expected a form, got {result['type']}")
    expect(result["step_id"] == "bluetooth_confirm", f"unexpected step {result['step_id']}")
    expect(flow.unique_id == ADDRESS, "the address must become the unique id")
    expect(result["confirm_only"] is True, "a discovered device needs confirmation only")
    expect(
        flow.context["title_placeholders"] == {"name": "Medisana EE:FF"},
        f"unexpected title placeholders {flow.context['title_placeholders']}",
    )

    created = asyncio.run(flow.async_step_bluetooth_confirm({}))
    expect(created["type"] == "create_entry", f"expected an entry, got {created['type']}")
    expect(created["title"] == "Medisana EE:FF", f"unexpected title {created['title']}")
    expect(created["data"] == {}, "the address is the identity, no entry data is stored")

    configured = FakeHass()
    configured.config_entries.entries.append(ConfigEntry(unique_id=ADDRESS))
    duplicate = new_flow(configured)
    reason: str | None = None
    try:
        asyncio.run(duplicate.async_step_bluetooth(FakeServiceInfo()))
    except AbortFlow as err:
        reason = err.reason
    expect(reason == "already_configured", f"expected an already_configured abort, got {reason!r}")


@check("manual picker lists discovered devices, including ignored ones")
def check_config_flow_user_step() -> None:
    hass = FakeHass()
    STUB_STATE["discovered"] = [
        FakeServiceInfo(address=ADDRESS),
        FakeServiceInfo(address=OTHER_ADDRESS, name="Medisana"),
    ]

    def options(flow: Any) -> set[str]:
        result = asyncio.run(flow.async_step_user(None))
        if result["type"] != "form":
            raise AssertionError(f"expected the picker, got {result}")
        return set(result["data_schema"].data["address"].options)

    try:
        # A new flow is created per discovery, so every scenario starts from scratch.
        expect(
            options(new_flow(hass)) == {ADDRESS, OTHER_ADDRESS},
            "both discovered devices must be offered",
        )

        # A device the user ignored earlier must stay selectable (F8 regression).
        hass.config_entries.entries.append(ConfigEntry(unique_id=ADDRESS, ignored=True))
        expect(
            ADDRESS in options(new_flow(hass)),
            "an ignored device must still be offered when adding an integration manually",
        )

        # A configured device is filtered out, the ignored one stays offered.
        hass.config_entries.entries.append(ConfigEntry(unique_id=OTHER_ADDRESS))
        expect(
            options(new_flow(hass)) == {ADDRESS},
            "a configured device must not be offered again",
        )

        # Once every discovered device is configured the flow aborts instead of
        # showing an empty picker.
        hass.config_entries.entries = [
            ConfigEntry(unique_id=ADDRESS),
            ConfigEntry(unique_id=OTHER_ADDRESS),
        ]
        result = asyncio.run(new_flow(hass).async_step_user(None))
        expect(
            result["type"] == "abort" and result["reason"] == "no_devices_found",
            f"expected no_devices_found, got {result}",
        )

        # Selecting a device creates the entry with the advertised title.
        chosen = new_flow(FakeHass())
        asyncio.run(chosen.async_step_user(None))
        created = asyncio.run(chosen.async_step_user({"address": ADDRESS}))
        expect(created["type"] == "create_entry", f"expected an entry, got {created}")
        expect(created["title"] == "Medisana EE:FF", f"unexpected title {created['title']}")

        STUB_STATE["discovered"] = []
        result = asyncio.run(new_flow(FakeHass()).async_step_user(None))
        expect(result["reason"] == "no_devices_found", "a discovery-less installation must abort cleanly")
    finally:
        STUB_STATE["discovered"] = []


# ---------------------------------------------------------------------------
# sensor platform
# ---------------------------------------------------------------------------
@check("every parser key has a sensor description and maps to an entity key")
def check_sensor_conversion() -> None:
    data = new_device_data()
    # a poll publishes the battery, the notification the measurement
    run_poll(data, payload=measurement_frame())
    update = data._finish_update()

    converted = sensor_module.sensor_update_to_bluetooth_data_update(update)
    keys = {key.key for key in converted.entity_descriptions}
    expected = {sensor.value for sensor in MedisanaBPSensor}
    missing = expected - keys
    expect(not missing, f"no SensorEntityDescription for {sorted(missing)}")
    expect(converted.entity_data[PassiveBluetoothEntityKey("systolic", None)] == 128, "systolic value")
    expect(converted.entity_data[PassiveBluetoothEntityKey("signal_strength", None)] == -70, "RSSI value")
    expect(
        converted.entity_names[PassiveBluetoothEntityKey("timestamp", None)] == "Measured Date",
        "entity names must be carried over",
    )
    expect(
        converted.entity_descriptions[PassiveBluetoothEntityKey("battery_percent", None)].device_class
        is SensorDeviceClass.BATTERY,
        "the battery description must keep its device class",
    )
    expect(
        converted.devices[None]["manufacturer"] == "Medisana",
        f"device info must be converted: {converted.devices[None]}",
    )
    expect(
        device_module.device_key_to_bluetooth_entity_key(DeviceKey("battery_percent", None))
        == PassiveBluetoothEntityKey("battery_percent", None),
        "device keys must map to bluetooth entity keys",
    )


@check("sensor platform registers the processor and creates the entities")
def check_sensor_platform() -> None:
    hass = FakeHass()
    entry = ConfigEntry(unique_id=ADDRESS)
    asyncio.run(async_setup_entry(hass, entry))

    added: list[list[Any]] = []
    asyncio.run(sensor_module.async_setup_entry(hass, entry, added.append))

    coordinator = entry.runtime_data
    expect(len(coordinator.processors) == 1, "exactly one processor must be registered")
    processor, description_class = coordinator.processors[0]
    expect(
        description_class is SensorEntityDescription,
        "the processor needs the entity description class for state restore",
    )
    expect(
        processor.entity_class is sensor_module.MedisanaBPBluetoothSensorEntity,
        "the platform must register its own entity class",
    )
    expect(
        len(entry.unload_callbacks) == 3,
        f"listener, processor and coordinator cleanup expected, got {len(entry.unload_callbacks)}",
    )

    data = new_device_data()
    run_poll(data, payload=measurement_frame())
    processor.async_handle_update(data._finish_update())

    expect(len(added) == 1, f"entities must be created once, got {added}")
    entities = {entity.entity_key.key: entity for entity in added[0]}
    expect(set(entities) == {sensor.value for sensor in MedisanaBPSensor}, f"created {sorted(entities)}")
    expect(entities["systolic"].native_value == 128, "the systolic entity must expose the value")
    expect(entities["battery_percent"].native_value == 77, "the battery entity must expose the value")
    expect(entities["signal_strength"].native_value == -70, "the RSSI entity must expose the value")
    expect(entities["timestamp"].native_value is not None, "the measured date must be exposed")
    expect(entities["systolic"].available is True, "sleepy devices stay available")
    expect(entities["systolic"].assumed_state is False, "assumed_state mirrors the processor")

    processor._available = False
    expect(entities["systolic"].assumed_state is True, "assumed_state must follow the processor availability")
    processor._available = True

    processor.async_handle_update(data._finish_update())
    expect(len(added) == 1, "known entity keys must not be added twice")


# ---------------------------------------------------------------------------
# metadata and documentation
# ---------------------------------------------------------------------------
@check("manifest follows the hassfest 2026.9 rules")
def check_manifest() -> None:
    manifest = json.loads((COMPONENT_DIR / "manifest.json").read_text(encoding="utf-8"))
    keys = list(manifest)

    expect(keys[:2] == ["domain", "name"], f"domain and name must come first, got {keys[:2]}")
    expect(keys[2:] == sorted(keys[2:]), f"remaining keys must be alphabetical, got {keys[2:]}")
    expect(manifest["domain"] == COMPONENT_DIR.name, "the domain must match the folder name")
    expect(isinstance(manifest["version"], str) and manifest["version"], "a version string is required")
    expect(manifest["documentation"].startswith("https://"), "documentation must be an https URL")
    expect(manifest["issue_tracker"].startswith("https://"), "issue_tracker must be an https URL")
    expect(manifest["config_flow"] is True, "the integration needs a config flow")
    expect("version" in manifest and "codeowners" in manifest, "custom integrations need version and codeowners")
    expect(
        manifest["integration_type"] in {"device", "hub", "service", "entity", "system", "helper"},
        f"unexpected integration_type {manifest['integration_type']}",
    )
    expect(
        manifest["iot_class"] in {"local_push", "local_polling", "cloud_polling", "cloud_push", "assumed_state"},
        f"unexpected iot_class {manifest['iot_class']}",
    )

    matcher_keys = {"connectable", "service_uuid", "service_data_uuid", "local_name", "manufacturer_id", "manufacturer_data_start"}
    for entry in manifest["bluetooth"]:
        unknown = set(entry) - matcher_keys
        expect(not unknown, f"unsupported bluetooth matcher keys: {sorted(unknown)}")
        expect(
            {"manufacturer_id", "local_name", "service_uuid", "service_data_uuid"} & set(entry),
            f"a matcher needs at least one identifier: {entry}",
        )
    for requirement in manifest["requirements"]:
        expect(
            re.fullmatch(r"[A-Za-z0-9._-]+(\[[A-Za-z0-9,._-]+\])?([<>=!~].+)?", requirement) is not None,
            f"requirement does not look like a PEP 508 specifier: {requirement}",
        )
    expect(
        any(req.startswith("bluetooth-sensor-state-data") for req in manifest["requirements"])
        and any(req.startswith("sensor-state-data") for req in manifest["requirements"]),
        "the two libraries the parser imports must be declared (F1)",
    )


@check("hacs.json, changelog, translations and brand assets are consistent")
def check_packaging() -> None:
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    allowed_hacs_keys = {
        "name", "content_in_root", "zip_release", "filename", "hide_default_branch",
        "country", "homeassistant", "hacs", "persistent_directory", "render_readme",
    }
    unknown = set(hacs) - allowed_hacs_keys
    expect(not unknown, f"hacs.json does not accept {sorted(unknown)}")
    expect(hacs["name"] == "Medisana Blood Pressure BLE", "hacs.json needs the integration name")
    expect(
        re.fullmatch(r"\d{4}\.\d+\.\d+", hacs["homeassistant"]) is not None,
        f"homeassistant must be a version, got {hacs['homeassistant']!r}",
    )

    manifest = json.loads((COMPONENT_DIR / "manifest.json").read_text(encoding="utf-8"))
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    newest = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
    expect(newest is not None, "CHANGELOG.md must contain a released version heading")
    expect(
        newest.group(1) == manifest["version"],
        f"CHANGELOG {newest.group(1)} != manifest version {manifest['version']}",
    )

    strings = json.loads((COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    translations_dir = COMPONENT_DIR / "translations"
    expect(translations_dir.is_dir(), "a translations directory is required for custom integrations (F6)")
    english = json.loads((translations_dir / "en.json").read_text(encoding="utf-8"))
    expect(english == strings, "translations/en.json must mirror strings.json")

    brand = COMPONENT_DIR / "brand"
    expect(brand.is_dir(), "HACS validation needs brand assets")
    for name in ("icon.png", "icon@2x.png"):
        path = brand / name
        expect(path.is_file(), f"missing brand asset {name}")
        expect(path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{name} is not a PNG")
    expect("brand" in {path.name for path in COMPONENT_DIR.iterdir()}, "the brand folder must be at the top level")


@check("every Python file compiles and the docs/Mermaid stay valid")
def check_sources_and_docs() -> None:
    sources = sorted(COMPONENT_DIR.rglob("*.py")) + sorted((ROOT / "testing").glob("*.py"))
    for path in sources:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as err:  # pragma: no cover - only on a broken edit
            raise AssertionError(f"{path.relative_to(ROOT)}: {err}") from err

    for name in (
        "Architecture-Concept-Document.md",
        "System-Design-Document.md",
        "Home-Assistant-2026.9-Compatibility-Report.md",
    ):
        expect((DOCS_DIR / name).is_file(), f"missing document {name}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name in (
        "docs/Architecture-Concept-Document.md",
        "docs/System-Design-Document.md",
        "docs/Home-Assistant-2026.9-Compatibility-Report.md",
    ):
        expect(name in readme, f"README must link {name}")
    expect("gitdiagram.com/acdcnow/Medisanabp_ble" in readme, "README must link the GitDiagram flow")

    problems: list[str] = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for index, block in enumerate(re.findall(r"```mermaid\n(.*?)```", text, re.DOTALL), start=1):
            for line_no, line in enumerate(block.splitlines(), start=1):
                if ";" in line:
                    problems.append(
                        f"{path.name} block {index} line {line_no}: ';' terminates a Mermaid statement"
                    )
                message = re.match(r"^\s*\w+\s*-+[->]+\s*\w+\s*:\s*(?P<text>.+)$", line)
                if message and "->" in message.group("text"):
                    problems.append(
                        f"{path.name} block {index} line {line_no}: '->' in sequence text is re-parsed"
                    )
    expect(not problems, "Mermaid issues:\n     " + "\n     ".join(problems))


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------
def main() -> int:
    failures: list[tuple[str, Exception]] = []
    for title, func in CHECKS:
        try:
            result = func()
            if asyncio.iscoroutine(result):
                asyncio.run(result)
        except Exception as err:  # noqa: BLE001 - reporting failures is the point
            failures.append((title, err))
            print(f"FAIL {title}")
            print(f"     {type(err).__name__}: {err}")
        else:
            print(f"ok   {title}")

    passed = len(CHECKS) - len(failures)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

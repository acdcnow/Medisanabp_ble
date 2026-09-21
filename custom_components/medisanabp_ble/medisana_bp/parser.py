from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from bleak import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)
from bluetooth_data_tools import short_address
from bluetooth_sensor_state_data import BluetoothData
from habluetooth import BluetoothServiceInfo
from sensor_state_data import SensorDeviceClass, SensorUpdate, Units
from sensor_state_data.enum import StrEnum

from .const import (
    CHARACTERISTIC_BATTERY,
    CHARACTERISTIC_BLOOD_PRESSURE,
    NOTIFICATION_TIMEOUT,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class MedisanaBPSensor(StrEnum):

    SYSTOLIC = "systolic"
    DIASTOLIC = "diastolic"
    PULSE = "pulse"
    SIGNAL_STRENGTH = "signal_strength"
    BATTERY_PERCENT = "battery_percent"
    TIMESTAMP = "timestamp"


class MedisanaBPBluetoothDeviceData(BluetoothData):
    """Data for MedisanaBP BLE sensors."""

    def __init__(self) -> None:
        super().__init__()
        self._event = asyncio.Event()

    def _start_update(self, service_info: BluetoothServiceInfo) -> None:
        """Update from BLE advertisement data."""
        _LOGGER.debug("Parsing MedisanaBP BLE advertisement data: %s", service_info)
        self.set_device_manufacturer("Medisana")
        self.set_device_type("Blood Pressure Measurement")
        name = (
            f"{service_info.name or 'Medisana BP'} "
            f"{short_address(service_info.address)}"
        )
        self.set_device_name(name)
        self.set_title(name)

    def poll_needed(
        self, service_info: BluetoothServiceInfo, last_poll: float | None
    ) -> bool:
        """
        This is called every time we get a service_info for a device. It means the
        device is working and online.

        ``last_poll`` is the number of seconds since the last poll attempt, or
        None if the device has never been polled since startup.
        """
        return not last_poll or last_poll > UPDATE_INTERVAL

    def notification_handler(self, _sender: Any, data: bytearray) -> None:
        """Handle a blood pressure measurement notification.

        Called from the Bluetooth stack, so it must not raise.
        """
        if len(data) < 16:
            _LOGGER.warning("Unexpected blood pressure payload: %s", data)
            return

        syst = data[2] * 256 + data[1]
        diast = data[4] * 256 + data[3]
        arter = data[6] * 256 + data[5]
        dyear = data[8] * 256 + data[7]
        dmonth = data[9]
        dday = data[10]
        dhour = data[11]
        dminu = data[12]
        puls = data[15] * 256 + data[14]
        try:
            date = datetime.strptime(
                f"{dyear}/{dmonth}/{dday} {dhour}:{dminu:0>2}", "%Y/%m/%d %H:%M"
            )
            # The device does not know about timezones, so the measured
            # date is handed to Home Assistant in the local timezone.
            self.update_sensor(
                key=str(MedisanaBPSensor.TIMESTAMP),
                native_unit_of_measurement=None,
                native_value=date.replace(
                    tzinfo=datetime.now(timezone.utc).astimezone().tzinfo
                ),
                name="Measured Date",
            )
        except (TypeError, ValueError):
            _LOGGER.warning("Can't add Measured Date from %s", data)

        _LOGGER.info(
            "Got data from BPM device (syst: %s, diast: %s, pulse: %s, map: %s)",
            syst,
            diast,
            puls,
            arter,
        )

        self.update_sensor(
            key=str(MedisanaBPSensor.SYSTOLIC),
            native_unit_of_measurement=Units.PRESSURE_MMHG,
            native_value=syst,
            device_class=SensorDeviceClass.PRESSURE,
            name="Systolic",
        )
        self.update_sensor(
            key=str(MedisanaBPSensor.DIASTOLIC),
            native_unit_of_measurement=Units.PRESSURE_MMHG,
            native_value=diast,
            device_class=SensorDeviceClass.PRESSURE,
            name="Diastolic",
        )
        self.update_sensor(
            key=str(MedisanaBPSensor.PULSE),
            native_unit_of_measurement="bpm",
            native_value=puls,
            name="Pulse",
        )
        self._event.set()
        return

    async def _async_read_battery(self, client: BleakClientWithServiceCache) -> None:
        """Read the battery level, if the device exposes it."""
        try:
            battery_char = client.services.get_characteristic(CHARACTERISTIC_BATTERY)
            if battery_char is None:
                _LOGGER.debug("Device has no battery characteristic")
                return
            battery_payload = await client.read_gatt_char(battery_char)
        except (BleakError, EOFError) as err:
            _LOGGER.warning("Could not read battery level: %s", err)
            return

        self.update_sensor(
            key=str(MedisanaBPSensor.BATTERY_PERCENT),
            native_unit_of_measurement=Units.PERCENTAGE,
            native_value=battery_payload[0],
            device_class=SensorDeviceClass.BATTERY,
            name="Battery",
        )

    async def async_poll(self, ble_device: BLEDevice) -> SensorUpdate:
        """
        Poll the device to retrieve any values we can't get from passive listening.
        """
        _LOGGER.debug("Connecting to BLE device: %s", ble_device.address)
        # Clear before subscribing: this poll may only complete early if *this*
        # connection delivered a measurement, otherwise the values of the
        # previous poll would be reported as the current ones.
        self._event.clear()
        client = await establish_connection(
            BleakClientWithServiceCache, ble_device, ble_device.address
        )
        try:
            await self._async_read_battery(client)
            try:
                await client.start_notify(
                    CHARACTERISTIC_BLOOD_PRESSURE, self.notification_handler
                )
            except (BleakError, EOFError) as err:
                _LOGGER.warning("Could not enable notifications: %s", err)
            else:
                # Wait to see if a callback comes in.
                try:
                    await asyncio.wait_for(self._event.wait(), NOTIFICATION_TIMEOUT)
                except TimeoutError:
                    _LOGGER.warning("Timeout getting measurement data")
        finally:
            # Notifications stop on disconnect, so stop_notify() is not needed.
            # The disconnect must happen even if reading the battery failed,
            # otherwise the connection stays open and the device can no longer
            # be reached.
            await client.disconnect()
            _LOGGER.debug("Disconnected from active bluetooth client")
        return self._finish_update()

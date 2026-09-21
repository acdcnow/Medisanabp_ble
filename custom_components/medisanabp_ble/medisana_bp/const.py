"""Constants for MedisanaBP BLE parser"""

CHARACTERISTIC_BLOOD_PRESSURE = "00002A35-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_BATTERY = "00002A19-0000-1000-8000-00805F9B34FB"

# Minimum age (seconds) of the previous poll before a new one is started.
UPDATE_INTERVAL = 10
# Seconds to wait for the measurement notification after subscribing.
NOTIFICATION_TIMEOUT = 15

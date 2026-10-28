"""
Central Device Manager.
Coordinates scanning across Logitech HID++, Windows Bluetooth, and Vendor 2.4G drivers,
manages caching, polling intervals, and low-battery alerts.
"""

import os
import time
import threading
from typing import List, Dict, Optional, Callable
from .device_base import (
    BaseDeviceDriver,
    PeripheralDevice,
    BatteryInfo,
    ChargingStatus,
    DeviceCategory,
    ConnectionType,
)
from .win_raw_hid import WinRawHid
from .win_bluetooth import WinBluetoothScanner
from ..drivers.logitech_hidpp import LogitechHidppDriver
from ..drivers.bluetooth_driver import BluetoothDeviceDriver
from ..drivers.vendor_24g_driver import Vendor24GDriver


class DeviceManager:
    def __init__(self, enable_mock: bool = False):
        self.enable_mock = enable_mock
        self.raw_hid = WinRawHid()
        self.bt_scanner = WinBluetoothScanner()

        self.drivers: List[BaseDeviceDriver] = [
            LogitechHidppDriver(self.raw_hid),
            BluetoothDeviceDriver(self.bt_scanner),
            Vendor24GDriver(self.raw_hid),
        ]

        # In-memory device cache: device_id -> PeripheralDevice
        self.devices: Dict[str, PeripheralDevice] = {}
        self.listeners: List[Callable[[List[PeripheralDevice]], None]] = []
        self.last_scan_time: float = 0.0
        self.last_errors: Dict[str, str] = {}
        self._lock = threading.RLock()

    def register_listener(self, callback: Callable[[List[PeripheralDevice]], None]):
        """Registers a callback when devices are refreshed."""
        self.listeners.append(callback)

    def scan_all(self) -> List[PeripheralDevice]:
        """Polls all drivers and updates the cache. Safe for concurrent callers."""
        with self._lock:
            current_devices: List[PeripheralDevice] = []

            if self.enable_mock or not self.raw_hid.is_windows:
                current_devices = self._generate_mock_devices()
            else:
                for driver in self.drivers:
                    try:
                        found = driver.scan_devices()
                        current_devices.extend(found)
                        self.last_errors.pop(driver.name(), None)
                    except Exception as exc:  # keep going if one bus/driver fails
                        self.last_errors[driver.name()] = str(exc)
                        if os.environ.get("OMNITOYS_DEBUG"):
                            print(f"[DeviceManager] {driver.name()} failed: {exc}")

            new_cache: Dict[str, PeripheralDevice] = {}
            for dev in current_devices:
                new_cache[dev.device_id] = dev

            self.devices = new_cache
            self.last_scan_time = time.time()

            # Notify subscribers (RLock makes a listener that reads state safe).
            for cb in list(self.listeners):
                try:
                    cb(list(self.devices.values()))
                except Exception:
                    pass

            return list(self.devices.values())

    def get_devices(self, max_age: Optional[float] = None) -> List[PeripheralDevice]:
        """Returns cached devices; optionally rescans only when the cache is stale."""
        with self._lock:
            fresh = (
                max_age is not None
                and self.last_scan_time > 0
                and (time.time() - self.last_scan_time) <= max_age
            )
            if fresh:
                return list(self.devices.values())
        return self.scan_all()

    def get_primary_mouse(self) -> Optional[PeripheralDevice]:
        """Finds the main connected mouse for tray icon display."""
        with self._lock:
            mice = [
                d for d in self.devices.values()
                if d.category == DeviceCategory.MOUSE and d.is_online and d.battery.is_valid
            ]
            if not mice:
                return None
            # Prioritize 2.4G mouse over Bluetooth
            mice.sort(
                key=lambda d: 0
                if d.connection_type in (ConnectionType.LOGITECH_LIGHTSPEED, ConnectionType.VENDOR_24G)
                else 1
            )
            return mice[0]

    def _generate_mock_devices(self) -> List[PeripheralDevice]:
        """Mock data for non-Windows development or simulation."""
        return [
            PeripheralDevice(
                device_id="logi_gpw_superlight",
                name="Logitech G Pro X Superlight",
                category=DeviceCategory.MOUSE,
                connection_type=ConnectionType.LOGITECH_LIGHTSPEED,
                battery=BatteryInfo(
                    percentage=78,
                    is_charging=ChargingStatus.DISCHARGING,
                    voltage_mv=3980,
                ),
                is_online=True,
                vendor_id=0x046D,
                product_id=0xC547,
            ),
            PeripheralDevice(
                device_id="bt_airpods_pro",
                name="AirPods Pro (Bluetooth)",
                category=DeviceCategory.HEADSET,
                connection_type=ConnectionType.BLUETOOTH,
                battery=BatteryInfo(percentage=90, is_charging=ChargingStatus.CHARGING),
                is_online=True,
            ),
            PeripheralDevice(
                device_id="vxe_dragonfly_f1",
                name="VXE Dragonfly F1 Pro Max",
                category=DeviceCategory.MOUSE,
                connection_type=ConnectionType.VENDOR_24G,
                battery=BatteryInfo(percentage=65, is_charging=ChargingStatus.DISCHARGING),
                is_online=True,
                vendor_id=0x373B,
                product_id=0x1216,
            ),
        ]

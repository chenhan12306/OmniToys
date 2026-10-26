"""
Bluetooth Peripheral Battery Driver.
Discovers and reads battery level for any Bluetooth device connected to Windows.
"""

from typing import List
from ..core.device_base import BaseDeviceDriver, PeripheralDevice
from ..core.win_bluetooth import WinBluetoothScanner


class BluetoothDeviceDriver(BaseDeviceDriver):
    def __init__(self, scanner: WinBluetoothScanner):
        self.scanner = scanner

    def name(self) -> str:
        return "Windows Bluetooth Battery Driver"

    def scan_devices(self) -> List[PeripheralDevice]:
        return self.scanner.scan_devices()

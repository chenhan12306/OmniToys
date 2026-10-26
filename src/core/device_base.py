"""
Device Base Definitions
Defines common data structures and abstract base classes for peripheral battery monitoring.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any
import time


class DeviceCategory(Enum):
    MOUSE = "Mouse"
    KEYBOARD = "Keyboard"
    HEADSET = "Headset"
    GAMEPAD = "Gamepad"
    OTHER = "Other"


class ConnectionType(Enum):
    LOGITECH_LIGHTSPEED = "Logitech 2.4G"
    VENDOR_24G = "2.4G Wireless"
    BLUETOOTH = "Bluetooth"
    USB_WIRED = "USB Wired"


class ChargingStatus(Enum):
    DISCHARGING = "Discharging"
    CHARGING = "Charging"
    FULL = "Full"
    UNKNOWN = "Unknown"


@dataclass
class BatteryInfo:
    percentage: int  # 0 to 100 (-1 if offline or unknown)
    is_charging: ChargingStatus = ChargingStatus.UNKNOWN
    voltage_mv: Optional[int] = None
    last_updated: float = field(default_factory=time.time)
    raw_status: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return 0 <= self.percentage <= 100


@dataclass
class PeripheralDevice:
    device_id: str
    name: str
    category: DeviceCategory
    connection_type: ConnectionType
    battery: BatteryInfo
    is_online: bool = True
    vendor_id: Optional[int] = None
    product_id: Optional[int] = None
    extra_meta: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        status = "Online" if self.is_online else "Offline"
        if not self.is_online:
            return f"[{self.connection_type.value}] {self.name}: Offline"
        
        charge_icon = "⚡" if self.battery.is_charging == ChargingStatus.CHARGING else ""
        pct_str = f"{self.battery.percentage}%{charge_icon}" if self.battery.is_valid else "Unknown"
        volt_str = f" ({self.battery.voltage_mv}mV)" if self.battery.voltage_mv else ""
        return f"[{self.connection_type.value}] {self.name}: {pct_str}{volt_str} [{status}]"


class BaseDeviceDriver:
    """Abstract driver interface for discovering and reading peripheral battery levels."""

    def name(self) -> str:
        raise NotImplementedError

    def scan_devices(self) -> list[PeripheralDevice]:
        """Scan and return a list of current devices and their battery status."""
        raise NotImplementedError

    def refresh_device(self, device: PeripheralDevice) -> Optional[BatteryInfo]:
        """Optionally refresh a single device on demand."""
        return None

"""
Windows Bluetooth Peripheral Battery Reader.
Queries connected Bluetooth and BLE devices (Keyboards, Mice, Headsets, Gamepads)
via Windows Device Property DEVPKEY_Device_BatteryLevel ({104EA319-6EE2-4701-BD47-8DDBF425BBE5}, 2).
"""

import sys
import json
import subprocess
from typing import List, Dict, Any, Optional
from .device_base import PeripheralDevice, DeviceCategory, ConnectionType, BatteryInfo, ChargingStatus


class WinBluetoothScanner:
    """Discovers and queries battery status of Bluetooth peripherals in Windows."""

    # {104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2
    BATTERY_PROP_KEY = "{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2"

    def __init__(self):
        self.is_windows = sys.platform.startswith("win")

    def scan_devices(self) -> List[PeripheralDevice]:
        """Scans all Bluetooth devices with reported battery level."""
        if not self.is_windows:
            return []

        # Run PowerShell query to read PnP device battery metadata
        # Fast, robust, and works on all Windows 10/11 versions without requiring admin privileges
        ps_script = (
            "$ErrorActionPreference = 'SilentlyContinue'; "
            "$devices = Get-PnpDevice | Where-Object { "
            "  ($_.Status -eq 'OK') -and "
            "  (($_.Class -eq 'Bluetooth' -or $_.Class -eq 'System' -or $_.Class -eq 'AudioEndpoint' -or $_.Class -eq 'Media') -and "
            "   ($_.InstanceId -like 'BTHLE*' -or $_.InstanceId -like 'BTHENUM*')) "
            "}; "
            "$results = foreach ($d in $devices) { "
            f"  $p = Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName '{self.BATTERY_PROP_KEY}' -ErrorAction SilentlyContinue; "
            "  if ($p -and $p.Type -ne 'Empty' -and $null -ne $p.Data) { "
            "    [PSCustomObject]@{ "
            "      InstanceId = $d.InstanceId; "
            "      Name       = $d.FriendlyName; "
            "      Class      = $d.Class; "
            "      Battery    = [int]$p.Data; "
            "    } "
            "  } "
            "}; "
            "if ($results) { $results | ConvertTo-Json -Compress } else { '[]' }"
        )

        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=3.0,
                creationflags=0x08000000 if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            stdout = res.stdout.strip()
            if not stdout or stdout == "[]":
                return []

            data = json.loads(stdout)
            if isinstance(data, dict):
                data = [data]

            devices: List[PeripheralDevice] = []
            seen_names = set()

            for item in data:
                name = item.get("Name") or "Bluetooth Device"
                if name in seen_names:
                    continue
                seen_names.add(name)

                battery_val = item.get("Battery")
                if battery_val is None:
                    continue

                try:
                    battery_pct = int(battery_val)
                except (ValueError, TypeError):
                    continue

                inst_id = item.get("InstanceId", "")
                category = self._guess_category(name, item.get("Class", ""))

                device = PeripheralDevice(
                    device_id=inst_id or f"bt_{name}",
                    name=name,
                    category=category,
                    connection_type=ConnectionType.BLUETOOTH,
                    battery=BatteryInfo(
                        percentage=battery_pct,
                        is_charging=ChargingStatus.UNKNOWN
                    ),
                    is_online=True,
                    extra_meta={"instance_id": inst_id}
                )
                devices.append(device)

            return devices
        except Exception:
            return []

    def _guess_category(self, name: str, dev_class: str) -> DeviceCategory:
        lower = name.lower()
        if any(k in lower for k in ["mouse", "trackball", "pointer"]):
            return DeviceCategory.MOUSE
        if any(k in lower for k in ["keyboard", "keychron", "k380", "k580", "mx keys"]):
            return DeviceCategory.KEYBOARD
        if any(k in lower for k in ["headset", "headphone", "airpods", "buds", "wh-", "wf-", "freebuds", "audio", "earphones"]):
            return DeviceCategory.HEADSET
        if any(k in lower for k in ["controller", "gamepad", "xbox", "dualsense", "wireless controller"]):
            return DeviceCategory.GAMEPAD
        return DeviceCategory.OTHER

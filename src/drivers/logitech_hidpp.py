"""
Logitech HID++ 1.0 / 2.0+ Driver.
Reads battery levels and charging statuses from Logitech Lightspeed & Unifying receivers
and wired gaming mice without running Logitech G HUB or Logitech Options.
"""

import time
from typing import List, Optional, Tuple
from ..core.device_base import (
    BaseDeviceDriver, PeripheralDevice, DeviceCategory,
    ConnectionType, BatteryInfo, ChargingStatus
)
from ..core.win_raw_hid import WinRawHid, HidDeviceInfo

LOGITECH_VID = 0x046D

# Feature IDs in HID++ 2.0
FEATURE_ROOT = 0x0000
FEATURE_DEVICE_NAME = 0x0005
FEATURE_BATTERY_VOLTAGE = 0x1000
FEATURE_UNIFIED_BATTERY = 0x1004


def estimate_percentage_from_voltage(mv: int) -> int:
    """Estimates battery percentage from typical single-cell LiPo voltage (mV)."""
    if mv >= 4150:
        return 100
    if mv >= 4000:
        return 85 + int((mv - 4000) / 150.0 * 15)
    if mv >= 3850:
        return 65 + int((mv - 3850) / 150.0 * 20)
    if mv >= 3750:
        return 40 + int((mv - 3750) / 100.0 * 25)
    if mv >= 3650:
        return 15 + int((mv - 3650) / 100.0 * 25)
    if mv >= 3500:
        return 5 + int((mv - 3500) / 150.0 * 10)
    return max(0, min(5, int((mv - 3300) / 200.0 * 5)))


class LogitechHidppDriver(BaseDeviceDriver):
    """Direct communication with Logitech HID++ 2.0 / 1.0 devices."""

    def __init__(self, raw_hid: WinRawHid):
        self.raw_hid = raw_hid

    def name(self) -> str:
        return "Logitech HID++ Driver"

    def scan_devices(self) -> List[PeripheralDevice]:
        devices: List[PeripheralDevice] = []
        if not self.raw_hid.is_windows:
            return devices

        # Enumerate all Logitech HID endpoints
        hid_list = self.raw_hid.enumerate_devices(target_vid=LOGITECH_VID)

        # Filter for endpoints exposing Vendor-Defined Usage Pages (0xFF00 or 0xFF43)
        # Windows allows user-space opening of these interfaces without ACCESS_DENIED.
        target_endpoints: List[HidDeviceInfo] = [
            dev for dev in hid_list
            if dev.usage_page in (0xFF00, 0xFF43) or dev.output_len >= 7
        ]

        # In case usage page isn't matched due to drivers, try all endpoints
        if not target_endpoints:
            target_endpoints = hid_list

        seen_devices = set()

        for ep in target_endpoints:
            handle = self.raw_hid.open_device(ep.path)
            if not handle:
                continue

            try:
                # In Lightspeed / Unifying dongles, paired wireless peripherals are usually at index 0x01 to 0x04.
                # Direct wired devices / dongle itself are at 0xFF or 0x01.
                device_slots = [0x01, 0x02, 0xFF]

                for slot in device_slots:
                    bat_info, dev_name = self._query_slot_battery(handle, slot, ep.product_name)
                    if bat_info and bat_info.is_valid:
                        dev_key = f"{ep.pid}_{slot}_{dev_name}"
                        if dev_key in seen_devices:
                            continue
                        seen_devices.add(dev_key)

                        device = PeripheralDevice(
                            device_id=f"logi_{ep.pid:04x}_{slot}",
                            name=dev_name or f"Logitech Device (PID: 0x{ep.pid:04X})",
                            category=DeviceCategory.MOUSE,  # Mostly mice/keyboards
                            connection_type=ConnectionType.LOGITECH_LIGHTSPEED,
                            battery=bat_info,
                            is_online=True,
                            vendor_id=LOGITECH_VID,
                            product_id=ep.pid,
                            extra_meta={"slot": slot, "path": ep.path}
                        )
                        devices.append(device)
            finally:
                self.raw_hid.close_device(handle)

        return devices

    def _query_slot_battery(self, handle: int, slot: int, fallback_name: str) -> Tuple[Optional[BatteryInfo], str]:
        """Tries to query battery via HID++ 2.0 (0x1004 / 0x1000) or HID++ 1.0."""
        # 1. Try HID++ 2.0 Unified Battery (0x1004)
        feature_idx_1004 = self._get_feature_index(handle, slot, FEATURE_UNIFIED_BATTERY)
        if feature_idx_1004:
            bat = self._read_feature_1004_battery(handle, slot, feature_idx_1004)
            if bat:
                name = self._get_device_name(handle, slot) or fallback_name or "Logitech Wireless Device"
                return bat, name

        # 2. Try HID++ 2.0 Battery Voltage (0x1000)
        feature_idx_1000 = self._get_feature_index(handle, slot, FEATURE_BATTERY_VOLTAGE)
        if feature_idx_1000:
            bat = self._read_feature_1000_battery(handle, slot, feature_idx_1000)
            if bat:
                name = self._get_device_name(handle, slot) or fallback_name or "Logitech Wireless Device"
                return bat, name

        # 3. Fallback: HID++ 1.0 Battery Register (0x0D)
        bat = self._read_hidpp10_battery(handle, slot)
        if bat:
            name = fallback_name or "Logitech Legacy Device"
            return bat, name

        return None, ""

    def _send_and_read(self, handle: int, request: bytes, timeout_reads: int = 5) -> Optional[bytes]:
        """Sends an output report and reads back the matching response."""
        if not self.raw_hid.write_output_report(handle, request):
            return None

        for _ in range(timeout_reads):
            resp = self.raw_hid.read_input_report(handle, 32)
            if resp and len(resp) >= 7:
                # Check Report ID matches (0x10 or 0x11) and slot matches
                if resp[0] in (0x10, 0x11) and resp[1] == request[1]:
                    return resp
            time.sleep(0.01)
        return None

    def _get_feature_index(self, handle: int, slot: int, feature_id: int) -> Optional[int]:
        """Resolves dynamic feature index using Root Feature 0x0000 (IRoot.getFeature)."""
        # Long report: [0x11, slot, feature_idx=0x00, func=0x00, feat_msb, feat_lsb, ...]
        req = bytearray(20)
        req[0] = 0x11
        req[1] = slot
        req[2] = 0x00  # Root feature index
        req[3] = 0x00  # Function 0: getFeature
        req[4] = (feature_id >> 8) & 0xFF
        req[5] = feature_id & 0xFF

        resp = self._send_and_read(handle, bytes(req))
        if resp and len(resp) >= 6:
            # Check for error report (0x8F)
            if resp[2] == 0x8F:
                return None
            feature_index = resp[4]
            if feature_index != 0:
                return feature_index
        return None

    def _read_feature_1004_battery(self, handle: int, slot: int, feature_idx: int) -> Optional[BatteryInfo]:
        """Queries HID++ 2.0 Feature 0x1004 (Unified Battery)."""
        req = bytearray(20)
        req[0] = 0x11
        req[1] = slot
        req[2] = feature_idx
        req[3] = 0x00  # Function 0: getBatteryLevelStatus

        resp = self._send_and_read(handle, bytes(req))
        if resp and len(resp) >= 7:
            # resp[4]: battery level percentage (0 - 100)
            # resp[6]: charging status
            percentage = resp[4]
            status_code = resp[6]

            charging = ChargingStatus.DISCHARGING
            if status_code in (1, 3):
                charging = ChargingStatus.CHARGING
            elif status_code == 2:
                charging = ChargingStatus.FULL

            if 0 <= percentage <= 100:
                return BatteryInfo(percentage=percentage, is_charging=charging)
        return None

    def _read_feature_1000_battery(self, handle: int, slot: int, feature_idx: int) -> Optional[BatteryInfo]:
        """Queries HID++ 2.0 Feature 0x1000 (Battery Voltage)."""
        req = bytearray(20)
        req[0] = 0x11
        req[1] = slot
        req[2] = feature_idx
        req[3] = 0x00  # Function 0: getBatteryVoltage

        resp = self._send_and_read(handle, bytes(req))
        if resp and len(resp) >= 7:
            voltage_mv = (resp[4] << 8) | resp[5]
            status_code = resp[6]

            charging = ChargingStatus.CHARGING if status_code == 1 else ChargingStatus.DISCHARGING
            pct = estimate_percentage_from_voltage(voltage_mv)
            return BatteryInfo(percentage=pct, is_charging=charging, voltage_mv=voltage_mv)
        return None

    def _read_hidpp10_battery(self, handle: int, slot: int) -> Optional[BatteryInfo]:
        """Queries HID++ 1.0 register 0x0D for legacy devices."""
        # Short report: [0x10, slot, 0x80 | 0x0D, 0x00, 0x00, 0x00, 0x00]
        req = bytearray(7)
        req[0] = 0x10
        req[1] = slot
        req[2] = 0x8D  # 0x80 | 0x0D (read register 0x0D)

        resp = self._send_and_read(handle, bytes(req))
        if resp and len(resp) >= 5 and resp[2] == 0x8D:
            # resp[4] usually contains battery level or percentage
            val = resp[4]
            if 0 <= val <= 100:
                return BatteryInfo(percentage=val, is_charging=ChargingStatus.UNKNOWN)
        return None

    def _get_device_name(self, handle: int, slot: int) -> Optional[str]:
        """Attempts to read the internal device model name via Feature 0x0005."""
        feature_idx = self._get_feature_index(handle, slot, FEATURE_DEVICE_NAME)
        if not feature_idx:
            return None

        # Function 1: getDeviceName(nameIndex)
        req = bytearray(20)
        req[0] = 0x11
        req[1] = slot
        req[2] = feature_idx
        req[3] = 0x10  # Function 1 (getDeviceName)
        req[4] = 0x00

        resp = self._send_and_read(handle, bytes(req))
        if resp and len(resp) >= 8:
            # Extract ASCII characters
            raw_chars = resp[5:]
            name_bytes = bytearray()
            for b in raw_chars:
                if b == 0:
                    break
                if 32 <= b <= 126:
                    name_bytes.append(b)
            if name_bytes:
                return name_bytes.decode('ascii', errors='ignore')
        return None

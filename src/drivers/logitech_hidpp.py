"""
Logitech HID++ 1.0 / 2.0+ Driver (Hub-Resilient & Radio-Friendly Edition).
Optimized specifically for:
- Direct Motherboard USB Ports & Monitor USB Hubs / KVM Switches
- Dual transport fallback (Interrupt & Control pipes via HidD_SetOutputReport)
- Dynamic slot discovery (slots 1..4 and 0xFF)
- Fast-path single-packet battery reads with zero mouse radio wakeups
- Per-endpoint caching, so two receivers with the same PID never collide
"""

import time
import zlib
from typing import List, Optional, Tuple, Dict, Any
from ..core.device_base import (
    BaseDeviceDriver, PeripheralDevice, DeviceCategory,
    ConnectionType, BatteryInfo, ChargingStatus
)
from ..core.win_raw_hid import WinRawHid, HidDeviceInfo

LOGITECH_VID = 0x046D

FEATURE_ROOT = 0x0000
FEATURE_DEVICE_NAME = 0x0005
FEATURE_BATTERY_VOLTAGE = 0x1000
FEATURE_UNIFIED_BATTERY = 0x1004

READ_TIMEOUT_MS = 25
WRITE_TIMEOUT_MS = 60


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
    """
    Direct communication with Logitech HID++ 2.0 / 1.0 devices.
    Resilient across direct motherboard ports and Monitor Hubs / KVMs.
    """

    def __init__(self, raw_hid: WinRawHid):
        self.raw_hid = raw_hid
        # Cache keyed by (device_interface_path, slot) - stable across two receivers
        # that share the same USB PID.
        self._device_cache: Dict[Tuple[str, int], Dict[str, Any]] = {}
        self._empty_slot_skips: Dict[Tuple[str, int], int] = {}
        self._cached_endpoints: List[HidDeviceInfo] = []
        self._last_endpoint_scan: float = 0.0

    def name(self) -> str:
        return "Logitech HID++ Driver (Hub-Resilient)"

    def scan_devices(self) -> List[PeripheralDevice]:
        devices: List[PeripheralDevice] = []
        if not self.raw_hid.is_windows:
            return devices

        now = time.time()
        # Refresh endpoints periodically (every 45s) or on initial boot.
        if not self._cached_endpoints or (now - self._last_endpoint_scan > 45.0):
            hid_list = self.raw_hid.enumerate_devices(target_vid=LOGITECH_VID)
            # Hub-resilient: do NOT discard endpoints whose usage page differs on
            # monitor hubs. Prefer vendor-defined pages, then try the rest.
            vendor_eps = [ep for ep in hid_list if ep.usage_page in (0xFF00, 0xFF43)]
            other_eps = [ep for ep in hid_list if ep.usage_page not in (0xFF00, 0xFF43)]
            self._cached_endpoints = vendor_eps + other_eps
            self._last_endpoint_scan = now

        seen_keys = set()

        for ep in self._cached_endpoints:
            handle = self.raw_hid.open_device(ep.path)
            if not handle:
                continue

            try:
                # Probe slots: 0x01 (primary wireless), 0xFF (wired/receiver), 0x02..0x04
                for slot in (0x01, 0xFF, 0x02, 0x03, 0x04):
                    cache_key = (ep.path, slot)

                    # Back off probing inactive empty slots.
                    if cache_key in self._empty_slot_skips:
                        skips_left = self._empty_slot_skips[cache_key]
                        if skips_left > 0:
                            self._empty_slot_skips[cache_key] -= 1
                            continue

                    bat_info, dev_name = self._smart_query_slot(handle, ep.path, slot, ep.product_name)
                    if bat_info and bat_info.is_valid:
                        if cache_key in seen_keys:
                            continue
                        seen_keys.add(cache_key)

                        path_hash = zlib.crc32(ep.path.encode("utf-8", "ignore")) & 0xFFFFFFFF
                        device = PeripheralDevice(
                            device_id=f"logi_{ep.pid:04x}_{slot}_{path_hash:08x}",
                            name=dev_name or f"Logitech Device (0x{ep.pid:04X})",
                            category=DeviceCategory.MOUSE,
                            connection_type=ConnectionType.LOGITECH_LIGHTSPEED,
                            battery=bat_info,
                            is_online=True,
                            vendor_id=LOGITECH_VID,
                            product_id=ep.pid,
                            extra_meta={"slot": slot, "path": ep.path},
                        )
                        devices.append(device)
                    else:
                        if cache_key not in self._device_cache:
                            self._empty_slot_skips[cache_key] = 4

            finally:
                self.raw_hid.close_device(handle)

        return devices

    def _smart_query_slot(
        self, handle: int, path: str, slot: int, fallback_name: str
    ) -> Tuple[Optional[BatteryInfo], str]:
        cache_key = (path, slot)
        cached = self._device_cache.get(cache_key)

        if cached:
            if cached.get("offline_skips", 0) > 0:
                cached["offline_skips"] -= 1
                return None, cached["name"]

            if cached.get("feat_1004"):
                bat = self._read_feature_1004_battery(handle, slot, cached["feat_1004"])
                if bat:
                    cached["offline_skips"] = 0
                    return bat, cached["name"]
                cached["offline_skips"] = 2
                return None, cached["name"]

            if cached.get("feat_1000"):
                bat = self._read_feature_1000_battery(handle, slot, cached["feat_1000"])
                if bat:
                    cached["offline_skips"] = 0
                    return bat, cached["name"]
                cached["offline_skips"] = 2
                return None, cached["name"]

            if cached.get("is_10"):
                bat = self._read_hidpp10_battery(handle, slot)
                if bat:
                    cached["offline_skips"] = 0
                    return bat, cached["name"]
                cached["offline_skips"] = 2
                return None, cached["name"]

        return self._discover_and_cache_slot(handle, path, slot, fallback_name)

    def _discover_and_cache_slot(
        self, handle: int, path: str, slot: int, fallback_name: str
    ) -> Tuple[Optional[BatteryInfo], str]:
        # 1. Feature 0x1004 (Unified Battery)
        feature_idx_1004 = self._get_feature_index(handle, slot, FEATURE_UNIFIED_BATTERY)
        if feature_idx_1004:
            bat = self._read_feature_1004_battery(handle, slot, feature_idx_1004)
            if bat:
                name = self._get_device_name(handle, slot) or fallback_name or "Logitech Wireless Device"
                self._device_cache[(path, slot)] = {
                    "feat_1004": feature_idx_1004,
                    "feat_1000": None,
                    "is_10": False,
                    "name": name,
                    "offline_skips": 0,
                }
                return bat, name

        # 2. Feature 0x1000 (Battery Voltage)
        feature_idx_1000 = self._get_feature_index(handle, slot, FEATURE_BATTERY_VOLTAGE)
        if feature_idx_1000:
            bat = self._read_feature_1000_battery(handle, slot, feature_idx_1000)
            if bat:
                name = self._get_device_name(handle, slot) or fallback_name or "Logitech Wireless Device"
                self._device_cache[(path, slot)] = {
                    "feat_1004": None,
                    "feat_1000": feature_idx_1000,
                    "is_10": False,
                    "name": name,
                    "offline_skips": 0,
                }
                return bat, name

        # 3. Fallback: HID++ 1.0 Register 0x0D
        bat = self._read_hidpp10_battery(handle, slot)
        if bat:
            name = fallback_name or "Logitech Legacy Device"
            self._device_cache[(path, slot)] = {
                "feat_1004": None,
                "feat_1000": None,
                "is_10": True,
                "name": name,
                "offline_skips": 0,
            }
            return bat, name

        return None, ""

    def _send_and_read(
        self, handle: int, request: bytes, timeout_reads: int = 3
    ) -> Optional[bytes]:
        """
        Sends a report through the output pipe (with control-pipe fallback) and
        reads matching responses with a hard timeout per read.
        """
        sent = self.raw_hid.write_output_report(handle, request, timeout_ms=WRITE_TIMEOUT_MS)
        if not sent:
            # Some monitor hubs expose HID++ only through feature reports.
            sent = self.raw_hid.set_feature_report(handle, request)
        if not sent:
            return None

        for _ in range(timeout_reads):
            resp = self.raw_hid.read_input_report(handle, 32, timeout_ms=READ_TIMEOUT_MS)
            if resp and len(resp) >= 7 and resp[0] in (0x10, 0x11) and resp[1] == request[1]:
                return resp
            time.sleep(0.002)
        return None

    def _get_feature_index(self, handle: int, slot: int, feature_id: int) -> Optional[int]:
        req = bytearray(20)
        req[0] = 0x11
        req[1] = slot
        req[2] = 0x00
        req[3] = 0x00
        req[4] = (feature_id >> 8) & 0xFF
        req[5] = feature_id & 0xFF

        resp = self._send_and_read(handle, bytes(req), timeout_reads=3)
        if resp and len(resp) >= 6:
            if resp[2] == 0x8F:
                return None
            feature_index = resp[4]
            if feature_index != 0:
                return feature_index
        return None

    def _read_feature_1004_battery(
        self, handle: int, slot: int, feature_idx: int
    ) -> Optional[BatteryInfo]:
        req = bytearray(20)
        req[0] = 0x11
        req[1] = slot
        req[2] = feature_idx
        req[3] = 0x00

        resp = self._send_and_read(handle, bytes(req), timeout_reads=3)
        if resp and len(resp) >= 7:
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

    def _read_feature_1000_battery(
        self, handle: int, slot: int, feature_idx: int
    ) -> Optional[BatteryInfo]:
        req = bytearray(20)
        req[0] = 0x11
        req[1] = slot
        req[2] = feature_idx
        req[3] = 0x00

        resp = self._send_and_read(handle, bytes(req), timeout_reads=3)
        if resp and len(resp) >= 7:
            voltage_mv = (resp[4] << 8) | resp[5]
            status_code = resp[6]

            charging = (
                ChargingStatus.CHARGING if status_code == 1 else ChargingStatus.DISCHARGING
            )
            pct = estimate_percentage_from_voltage(voltage_mv)
            return BatteryInfo(percentage=pct, is_charging=charging, voltage_mv=voltage_mv)
        return None

    def _read_hidpp10_battery(self, handle: int, slot: int) -> Optional[BatteryInfo]:
        req = bytearray(7)
        req[0] = 0x10
        req[1] = slot
        req[2] = 0x8D

        resp = self._send_and_read(handle, bytes(req), timeout_reads=3)
        if resp and len(resp) >= 5 and resp[2] == 0x8D:
            val = resp[4]
            if 0 <= val <= 100:
                return BatteryInfo(percentage=val, is_charging=ChargingStatus.UNKNOWN)
        return None

    def _get_device_name(self, handle: int, slot: int) -> Optional[str]:
        feature_idx = self._get_feature_index(handle, slot, FEATURE_DEVICE_NAME)
        if not feature_idx:
            return None

        chunks: List[str] = []
        for chunk_index in range(4):
            req = bytearray(20)
            req[0] = 0x11
            req[1] = slot
            req[2] = feature_idx
            # Function 1 = getDeviceName, software id 0 -> 0x01
            req[3] = 0x01
            req[4] = chunk_index

            resp = self._send_and_read(handle, bytes(req), timeout_reads=2)
            if not resp or len(resp) < 6:
                break
            raw = bytes(b for b in resp[5:] if 32 <= b <= 126)
            if not raw:
                break
            chunks.append(raw.decode("ascii", errors="ignore"))
            if len(raw) < 14:
                break

        name = "".join(chunks).strip()
        return name or None

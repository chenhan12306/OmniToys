"""
Logitech HID++ 1.0 / 2.0+ Driver (Radio-Friendly & Low-Resource Edition).
Optimized specifically for ultra-low wireless power consumption, near-zero CPU usage,
and instant cached reads without waking the mouse RF chip repeatedly.
"""

import time
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
    Engineered with:
    - Smart Feature Index Caching (avoids repeated IRoot discovery RF packets)
    - Single-Packet Fast Battery Refresh (1 packet = ~1ms RF airtime)
    - RF Sleep Backoff (skips inactive/sleeping slots to allow mouse deep-sleep)
    """

    def __init__(self, raw_hid: WinRawHid):
        self.raw_hid = raw_hid
        # Cache device feature indices and names: key = (pid, slot)
        # Value = {"feat_1004": int, "feat_1000": int, "is_10": bool, "name": str, "offline_skips": int}
        self._device_cache: Dict[Tuple[int, int], Dict[str, Any]] = {}
        # Empty slots cache: key = (pid, slot), value = skip_counter
        self._empty_slot_skips: Dict[Tuple[int, int], int] = {}
        # Cached target HID endpoints
        self._cached_endpoints: List[HidDeviceInfo] = []
        self._last_endpoint_scan: float = 0.0

    def name(self) -> str:
        return "Logitech HID++ Driver (Radio-Friendly)"

    def scan_devices(self) -> List[PeripheralDevice]:
        devices: List[PeripheralDevice] = []
        if not self.raw_hid.is_windows:
            return devices

        now = time.time()
        # Refresh HID endpoints only once every 60s (prevents constant USB bus enumeration overhead)
        if not self._cached_endpoints or (now - self._last_endpoint_scan > 60.0):
            hid_list = self.raw_hid.enumerate_devices(target_vid=LOGITECH_VID)
            self._cached_endpoints = [
                dev for dev in hid_list
                if dev.usage_page in (0xFF00, 0xFF43) or dev.output_len >= 7
            ]
            if not self._cached_endpoints:
                self._cached_endpoints = hid_list
            self._last_endpoint_scan = now

        seen_keys = set()

        for ep in self._cached_endpoints:
            handle = self.raw_hid.open_device(ep.path)
            if not handle:
                continue

            try:
                # Slot 0x01 is the standard paired mouse in 99% of setups.
                # Direct wired devices or Powerplay mat receiver are 0xFF or 0x01.
                device_slots = [0x01, 0xFF, 0x02]

                for slot in device_slots:
                    cache_key = (ep.pid, slot)

                    # Check if this empty slot should be skipped to prevent waking RF
                    if cache_key in self._empty_slot_skips:
                        skips_left = self._empty_slot_skips[cache_key]
                        if skips_left > 0:
                            self._empty_slot_skips[cache_key] -= 1
                            continue

                    bat_info, dev_name = self._smart_query_slot(handle, ep.pid, slot, ep.product_name)
                    if bat_info and bat_info.is_valid:
                        dev_key = f"{ep.pid}_{slot}"
                        if dev_key in seen_keys:
                            continue
                        seen_keys.add(dev_key)

                        device = PeripheralDevice(
                            device_id=f"logi_{ep.pid:04x}_{slot}",
                            name=dev_name or f"Logitech Device (0x{ep.pid:04X})",
                            category=DeviceCategory.MOUSE,
                            connection_type=ConnectionType.LOGITECH_LIGHTSPEED,
                            battery=bat_info,
                            is_online=True,
                            vendor_id=LOGITECH_VID,
                            product_id=ep.pid,
                            extra_meta={"slot": slot, "path": ep.path}
                        )
                        devices.append(device)
                    else:
                        # Empty slot: back off probing for the next 5 scan cycles (approx 3~5 minutes)
                        if cache_key not in self._device_cache:
                            self._empty_slot_skips[cache_key] = 5

            finally:
                self.raw_hid.close_device(handle)

        return devices

    def _smart_query_slot(self, handle: int, pid: int, slot: int, fallback_name: str) -> Tuple[Optional[BatteryInfo], str]:
        """
        Fast-path: If feature index is already cached, sends ONLY ONE 20-byte battery read packet!
        Zero IRoot query, zero Name query, near-zero RF power consumption.
        """
        cache_key = (pid, slot)
        cached = self._device_cache.get(cache_key)

        if cached:
            # Check offline backoff (if mouse is in deep sleep, don't hammer it every cycle)
            if cached.get("offline_skips", 0) > 0:
                cached["offline_skips"] -= 1
                return None, cached["name"]

            # 1. Fast-path: Feature 0x1004 (Unified Battery) - 1 single packet
            if cached.get("feat_1004"):
                bat = self._read_feature_1004_battery(handle, slot, cached["feat_1004"])
                if bat:
                    cached["offline_skips"] = 0
                    return bat, cached["name"]
                else:
                    # Mouse didn't respond (likely entered RF deep-sleep)
                    cached["offline_skips"] = 2
                    return None, cached["name"]

            # 2. Fast-path: Feature 0x1000 (Battery Voltage) - 1 single packet
            if cached.get("feat_1000"):
                bat = self._read_feature_1000_battery(handle, slot, cached["feat_1000"])
                if bat:
                    cached["offline_skips"] = 0
                    return bat, cached["name"]
                else:
                    cached["offline_skips"] = 2
                    return None, cached["name"]

            # 3. Fast-path: HID++ 1.0 Register 0x0D - 1 single short packet
            if cached.get("is_10"):
                bat = self._read_hidpp10_battery(handle, slot)
                if bat:
                    cached["offline_skips"] = 0
                    return bat, cached["name"]
                else:
                    cached["offline_skips"] = 2
                    return None, cached["name"]

        # Slow-path: First-time device discovery (performed ONCE per device lifetime)
        return self._discover_and_cache_slot(handle, pid, slot, fallback_name)

    def _discover_and_cache_slot(self, handle: int, pid: int, slot: int, fallback_name: str) -> Tuple[Optional[BatteryInfo], str]:
        """Resolves feature indices and caches them permanently to minimize future RF traffic."""
        # 1. Try HID++ 2.0 Unified Battery (0x1004)
        feature_idx_1004 = self._get_feature_index(handle, slot, FEATURE_UNIFIED_BATTERY)
        if feature_idx_1004:
            bat = self._read_feature_1004_battery(handle, slot, feature_idx_1004)
            if bat:
                name = self._get_device_name(handle, slot) or fallback_name or "Logitech Wireless Device"
                self._device_cache[(pid, slot)] = {
                    "feat_1004": feature_idx_1004,
                    "feat_1000": None,
                    "is_10": False,
                    "name": name,
                    "offline_skips": 0
                }
                return bat, name

        # 2. Try HID++ 2.0 Battery Voltage (0x1000)
        feature_idx_1000 = self._get_feature_index(handle, slot, FEATURE_BATTERY_VOLTAGE)
        if feature_idx_1000:
            bat = self._read_feature_1000_battery(handle, slot, feature_idx_1000)
            if bat:
                name = self._get_device_name(handle, slot) or fallback_name or "Logitech Wireless Device"
                self._device_cache[(pid, slot)] = {
                    "feat_1004": None,
                    "feat_1000": feature_idx_1000,
                    "is_10": False,
                    "name": name,
                    "offline_skips": 0
                }
                return bat, name

        # 3. Fallback: HID++ 1.0 Battery Register (0x0D)
        bat = self._read_hidpp10_battery(handle, slot)
        if bat:
            name = fallback_name or "Logitech Legacy Device"
            self._device_cache[(pid, slot)] = {
                "feat_1004": None,
                "feat_1000": None,
                "is_10": True,
                "name": name,
                "offline_skips": 0
            }
            return bat, name

        return None, ""

    def _send_and_read(self, handle: int, request: bytes, timeout_reads: int = 3) -> Optional[bytes]:
        """Fast non-blocking read exchange."""
        if not self.raw_hid.write_output_report(handle, request):
            return None

        # Quick check for response (Logitech receivers respond in 1-5ms)
        for _ in range(timeout_reads):
            resp = self.raw_hid.read_input_report(handle, 32)
            if resp and len(resp) >= 7:
                if resp[0] in (0x10, 0x11) and resp[1] == request[1]:
                    return resp
            time.sleep(0.005)  # Minimal 5ms sleep
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

    def _read_feature_1004_battery(self, handle: int, slot: int, feature_idx: int) -> Optional[BatteryInfo]:
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

    def _read_feature_1000_battery(self, handle: int, slot: int, feature_idx: int) -> Optional[BatteryInfo]:
        req = bytearray(20)
        req[0] = 0x11
        req[1] = slot
        req[2] = feature_idx
        req[3] = 0x00

        resp = self._send_and_read(handle, bytes(req), timeout_reads=3)
        if resp and len(resp) >= 7:
            voltage_mv = (resp[4] << 8) | resp[5]
            status_code = resp[6]

            charging = ChargingStatus.CHARGING if status_code == 1 else ChargingStatus.DISCHARGING
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

        req = bytearray(20)
        req[0] = 0x11
        req[1] = slot
        req[2] = feature_idx
        req[3] = 0x10
        req[4] = 0x00

        resp = self._send_and_read(handle, bytes(req), timeout_reads=3)
        if resp and len(resp) >= 8:
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

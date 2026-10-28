"""
Vendor 2.4G Custom Driver (ATK, VXE, Razer, Jieli, etc.).
Allows loading custom reverse-engineered protocol configurations
similar to the 2.4G-battery-viewer architecture.
"""

import os
import json
import zlib
from typing import List, Optional, Dict, Any
from ..core.device_base import (
    BaseDeviceDriver, PeripheralDevice, DeviceCategory,
    ConnectionType, BatteryInfo, ChargingStatus
)
from ..core.win_raw_hid import WinRawHid, HidDeviceInfo


class Vendor24GDriver(BaseDeviceDriver):
    def __init__(self, raw_hid: WinRawHid, config_path: Optional[str] = None):
        self.raw_hid = raw_hid
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "custom_devices.json")
        self.config_path = config_path
        self.device_profiles = self._load_profiles()

    def name(self) -> str:
        return "Generic / Vendor 2.4G Protocol Driver"

    def _load_profiles(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.config_path):
            return []
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def scan_devices(self) -> List[PeripheralDevice]:
        devices: List[PeripheralDevice] = []
        if not self.raw_hid.is_windows:
            return devices

        seen_paths = set()
        for profile in self.device_profiles:
            try:
                vid = int(profile.get("vid", 0))
                pid = int(profile.get("pid", 0))
            except (TypeError, ValueError):
                continue
            if not vid or not pid:
                continue

            endpoints = self.raw_hid.enumerate_devices(target_vid=vid, target_pid=pid)
            if not endpoints:
                continue

            for ep in endpoints:
                if (ep.path, vid, pid) in seen_paths:
                    continue
                bat_info = self._read_profile_battery(ep, profile)
                if bat_info and bat_info.is_valid:
                    seen_paths.add((ep.path, vid, pid))
                    cat_str = str(profile.get("category", "Mouse"))
                    category = getattr(DeviceCategory, cat_str.upper(), DeviceCategory.MOUSE)
                    path_hash = zlib.crc32(ep.path.encode("utf-8", "ignore")) & 0xFFFFFFFF

                    dev = PeripheralDevice(
                        device_id=f"vendor_{vid:04x}_{pid:04x}_{path_hash:08x}",
                        name=profile.get("name", ep.product_name or "2.4G Device"),
                        category=category,
                        connection_type=ConnectionType.VENDOR_24G,
                        battery=bat_info,
                        is_online=True,
                        vendor_id=vid,
                        product_id=pid,
                        extra_meta={"path": ep.path, "profile": profile.get("name")},
                    )
                    devices.append(dev)
                    break

        return devices

    def _read_profile_battery(
        self, ep: HidDeviceInfo, profile: Dict[str, Any]
    ) -> Optional[BatteryInfo]:
        handle = self.raw_hid.open_device(ep.path)
        if not handle:
            return None

        try:
            method = str(profile.get("method", "feature_report"))
            req_hex = str(profile.get("request_hex", "")).replace(" ", "")
            try:
                req_bytes = bytes.fromhex(req_hex) if req_hex else b""
            except ValueError:
                return None

            try:
                bat_offset = int(profile.get("battery_byte_offset", 0))
                charge_offset = int(profile.get("charging_byte_offset", -1))
                report_id = int(profile.get("report_id", 0))
            except (TypeError, ValueError):
                return None
            if bat_offset < 0:
                return None

            if method == "feature_report":
                feature_length = int(profile.get("feature_report_length", 0) or 0)
                if req_bytes:
                    send_bytes = (
                        req_bytes.ljust(feature_length, b"\x00")
                        if feature_length > len(req_bytes)
                        else req_bytes
                    )
                    self.raw_hid.set_feature_report(handle, send_bytes)

                length = max(16, bat_offset + 2, feature_length)
                resp = self.raw_hid.get_feature_report(handle, report_id, length)
                if resp and len(resp) > bat_offset:
                    pct = resp[bat_offset]
                    charging = ChargingStatus.UNKNOWN
                    if charge_offset >= 0 and len(resp) > charge_offset:
                        charging = (
                            ChargingStatus.CHARGING
                            if resp[charge_offset] == 1
                            else ChargingStatus.DISCHARGING
                        )
                    if 0 <= pct <= 100:
                        return BatteryInfo(percentage=pct, is_charging=charging)

            elif method == "output_report":
                if req_bytes:
                    self.raw_hid.write_output_report(handle, req_bytes)
                resp = self.raw_hid.read_input_report(
                    handle, max(32, bat_offset + 2), timeout_ms=120
                )
                if resp and len(resp) > bat_offset:
                    pct = resp[bat_offset]
                    if 0 <= pct <= 100:
                        charging = ChargingStatus.UNKNOWN
                        if charge_offset >= 0 and len(resp) > charge_offset:
                            charging = (
                                ChargingStatus.CHARGING
                                if resp[charge_offset] == 1
                                else ChargingStatus.DISCHARGING
                            )
                        return BatteryInfo(percentage=pct, is_charging=charging)

            elif method == "razer_protocol":
                # Razer 90-byte Feature Report structure
                razer_req = bytearray(90)
                razer_req[0] = 0x00  # Report ID
                razer_req[1] = 0x1F  # Status
                razer_req[2] = 0x00  # Transaction ID
                razer_req[5] = 0x02  # Data size
                razer_req[6] = 0x07  # Command Class: Power
                razer_req[7] = 0x80  # Command ID: Get Battery
                csum = 0
                for b in razer_req[2:88]:
                    csum ^= b
                razer_req[88] = csum

                if self.raw_hid.set_feature_report(handle, bytes(razer_req)):
                    resp = self.raw_hid.get_feature_report(handle, 0, 90)
                    if resp and len(resp) >= 11:
                        raw_level = resp[bat_offset if bat_offset < len(resp) else 9]
                        pct = int(raw_level / 255.0 * 100) if raw_level > 100 else raw_level
                        is_chg = resp[10] == 1
                        return BatteryInfo(
                            percentage=pct,
                            is_charging=(
                                ChargingStatus.CHARGING if is_chg else ChargingStatus.DISCHARGING
                            ),
                        )

        finally:
            self.raw_hid.close_device(handle)

        return None

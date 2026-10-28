"""
OmniBattery Module for OmniToys.
Performs background scanning of Logitech Lightspeed, Bluetooth, and 2.4G peripherals.
"""

import threading
import time
from typing import Dict, Any, List, Optional
from ..base_module import ToyModule
from ...core.device_manager import DeviceManager
from ...core.device_base import ChargingStatus


class OmniBatteryModule(ToyModule):
    def __init__(self, enable_mock: bool = False):
        super().__init__(
            module_id="omni_battery",
            name="外设电量监控 (OmniBattery)",
            description="全协议监控罗技 Lightspeed、蓝牙鼠标键盘耳机及国产 2.4G 接收器电量，无需安装各家专有驱动。",
            icon="battery",
        )
        self.device_manager = DeviceManager(enable_mock=enable_mock)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_devices: List[Dict[str, Any]] = []

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "poll_interval": 30,
            "alert_threshold": 20,
            "show_percentage_in_tray": True,
        }

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="OmniToysBatteryThread"
        )
        self._thread.start()

    def stop(self):
        self._running = False
        thread = self._thread
        self._thread = None
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)

    def _worker_loop(self):
        while self._running:
            try:
                self._scan_once()
            except Exception as exc:
                print(f"[OmniBattery] scan failed: {exc}")
            interval = max(5, int(self.config.get("poll_interval", 30) or 30))
            for _ in range(interval * 2):
                if not self._running:
                    break
                time.sleep(0.5)

    def _scan_once(self):
        devs = self.device_manager.scan_all()
        formatted = []
        for d in devs:
            formatted.append(
                {
                    "id": d.device_id,
                    "name": d.name,
                    "category": d.category.value,
                    "connection": d.connection_type.value,
                    "percentage": d.battery.percentage,
                    "charging": d.battery.is_charging == ChargingStatus.CHARGING,
                    "voltage_mv": d.battery.voltage_mv,
                    "is_online": d.is_online,
                }
            )
        self._last_devices = formatted

    def get_state(self) -> Dict[str, Any]:
        primary = self.device_manager.get_primary_mouse()
        primary_info = None
        if primary:
            primary_info = {
                "name": primary.name,
                "percentage": primary.battery.percentage,
                "charging": primary.battery.is_charging == ChargingStatus.CHARGING,
            }
        return {
            "devices": self._last_devices,
            "primary_mouse": primary_info,
            "last_scanned": self.device_manager.last_scan_time,
            "poll_interval": int(self.config.get("poll_interval", 30) or 30),
            "alert_threshold": int(self.config.get("alert_threshold", 20) or 20),
        }

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "refresh":
            self._scan_once()
            return {"status": "ok", "state": self.get_state()}

        elif action == "diagnose_usb":
            # Live diagnostic scanner for Monitor Hubs / KVMs / USB Ports
            all_eps = self.device_manager.raw_hid.enumerate_devices()
            diag_list = []
            seen_devs = set()
            for ep in all_eps:
                key = (ep.vid, ep.pid, ep.usage_page, ep.usage)
                if key in seen_devs:
                    continue
                seen_devs.add(key)
                diag_list.append(
                    {
                        "vid": ep.vid,
                        "pid": ep.pid,
                        "vid_hex": f"0x{ep.vid:04X}",
                        "pid_hex": f"0x{ep.pid:04X}",
                        "name": ep.product_name or "Generic HID Device",
                        "usage_page": f"0x{ep.usage_page:04X}",
                        "path_snippet": ep.path[:50] + "..." if len(ep.path) > 50 else ep.path,
                    }
                )
            return {"status": "ok", "diagnostics": diag_list}

        elif action == "update_settings":
            if "poll_interval" in payload:
                try:
                    self.config["poll_interval"] = max(5, min(3600, int(payload["poll_interval"])))
                except (TypeError, ValueError):
                    pass
            if "alert_threshold" in payload:
                try:
                    self.config["alert_threshold"] = max(1, min(100, int(payload["alert_threshold"])))
                except (TypeError, ValueError):
                    pass
            if "show_percentage_in_tray" in payload:
                self.config["show_percentage_in_tray"] = bool(payload["show_percentage_in_tray"])
            return {"status": "ok", "config": self.config}

        return {"status": "unknown_action"}

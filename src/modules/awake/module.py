"""
PowerToys-style Awake Module.
Keeps the computer and display awake on demand using SetThreadExecutionState.
"""

import sys
import ctypes
from typing import Dict, Any
from ..base_module import ToyModule

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


class AwakeModule(ToyModule):
    def __init__(self):
        super().__init__(
            module_id="awake",
            name="保持清醒 (Awake)",
            description="阻止电脑进入睡眠休眠或关闭显示器。适合挂机下载、编译代码或长时渲染，无需修改系统电源计划。",
            icon="coffee"
        )
        self.is_active = False

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "mode": "indefinite",  # "indefinite" or "passive"
            "keep_screen_on": True
        }

    def start(self):
        if self.config.get("enabled", False):
            self._apply_awake_state(True)

    def stop(self):
        self._apply_awake_state(False)

    def _apply_awake_state(self, active: bool):
        self.is_active = active
        if not sys.platform.startswith("win"):
            return

        try:
            kernel32 = ctypes.windll.kernel32
            if active:
                flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
                if self.config.get("keep_screen_on", True):
                    flags |= ES_DISPLAY_REQUIRED
                kernel32.SetThreadExecutionState(flags)
            else:
                kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception as e:
            print(f"[AwakeModule] Failed to set execution state: {e}")

    def get_state(self) -> Dict[str, Any]:
        return {
            "is_active": self.is_active,
            "mode": self.config.get("mode", "indefinite"),
            "keep_screen_on": self.config.get("keep_screen_on", True)
        }

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "toggle_active":
            new_state = not self.is_active
            self.config["enabled"] = new_state
            self._apply_awake_state(new_state)
            return {"status": "ok", "is_active": self.is_active}
        elif action == "update_settings":
            for k, v in payload.items():
                self.config[k] = v
            if self.is_active:
                self._apply_awake_state(True)
            return {"status": "ok", "config": self.config}
        return {"status": "unknown_action"}

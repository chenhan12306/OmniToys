"""
PowerToys-style Window Pinner (Always on Top) Module.
Allows pinning active windows on top of all others.
"""

import sys
import ctypes
from typing import Dict, Any
from ..base_module import ToyModule

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
WS_EX_TOPMOST = 0x00000008
GWL_EXSTYLE = -20


class WindowPinnerModule(ToyModule):
    def __init__(self):
        super().__init__(
            module_id="window_pinner",
            name="窗口置顶 (Always on Top)",
            description="一键将任意前台窗口（如计算器、记事本、播放器、参考文档）保持在最顶层显示。",
            icon="pin"
        )
        self.pinned_windows = []

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "shortcut": "Ctrl+Win+T",
            "border_highlight": True
        }

    def start(self):
        pass

    def stop(self):
        pass

    def pin_foreground_window(self) -> Dict[str, Any]:
        """Toggles topmost state for the currently focused foreground window."""
        if not sys.platform.startswith("win"):
            return {"status": "unsupported_platform"}

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"status": "no_window"}

        # Get window title
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value or "Untitled Window"

        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        is_topmost = bool(ex_style & WS_EX_TOPMOST)

        new_flag = HWND_NOTOPMOST if is_topmost else HWND_TOPMOST
        user32.SetWindowPos(hwnd, new_flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

        state_str = "unpinned" if is_topmost else "pinned"
        return {"status": "ok", "hwnd": hwnd, "title": title, "state": state_str}

    def get_state(self) -> Dict[str, Any]:
        return {
            "shortcut": self.config.get("shortcut", "Ctrl+Win+T"),
            "pinned_count": len(self.pinned_windows)
        }

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "pin_current":
            return self.pin_foreground_window()
        return {"status": "unknown_action"}

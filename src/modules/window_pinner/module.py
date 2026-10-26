"""
PowerToys-style Window Pinner (Always on Top) Module.
Allows pinning active windows on top of all others with safe cleanup on exit.
"""

import sys
import ctypes
from typing import Dict, Any, Set
from ..base_module import ToyModule
from ...core.safety_guard import register_shutdown_handler

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
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
        self.pinned_windows: Set[int] = set()
        register_shutdown_handler(self.unpin_all_safe)

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "shortcut": "Ctrl+Win+T",
            "border_highlight": True
        }

    def start(self):
        pass

    def stop(self):
        self.unpin_all_safe()

    def unpin_all_safe(self):
        """Emergency restoration: restores all pinned windows so none are permanently stuck topmost."""
        if not sys.platform.startswith("win") or not self.pinned_windows:
            return

        try:
            user32 = ctypes.windll.user32
            for hwnd in list(self.pinned_windows):
                if user32.IsWindow(hwnd):
                    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            self.pinned_windows.clear()
        except Exception:
            pass

    def pin_foreground_window(self) -> Dict[str, Any]:
        """Toggles topmost state for the currently focused foreground window."""
        if not sys.platform.startswith("win"):
            return {"status": "unsupported_platform"}

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"status": "no_window"}

        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value or "Untitled Window"

        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        is_topmost = bool(ex_style & WS_EX_TOPMOST)

        if is_topmost:
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            self.pinned_windows.discard(hwnd)
            state_str = "unpinned"
        else:
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            self.pinned_windows.add(hwnd)
            state_str = "pinned"

        return {"status": "ok", "hwnd": hwnd, "title": title, "state": state_str, "pinned_count": len(self.pinned_windows)}

    def get_state(self) -> Dict[str, Any]:
        return {
            "shortcut": self.config.get("shortcut", "Ctrl+Win+T"),
            "pinned_count": len(self.pinned_windows)
        }

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "pin_current":
            return self.pin_foreground_window()
        return {"status": "unknown_action"}

"""
Desktop Fences Module for OmniToys (Zero-CPU & Ultra-Smooth Edition).
Manages multi-container desktop fences, folder portals, roll-ups, and desktop layout.
"""

import sys
import os
import ctypes
from ctypes import wintypes
import threading
import time
import uuid
from typing import Dict, Any, List, Optional
from ..base_module import ToyModule
from ...core.safety_guard import register_shutdown_handler
from .fence_window import (
    Win32FenceWindow, WM_PAINT, WM_LBUTTONDOWN, WM_LBUTTONDBLCLK,
    WM_MOUSEMOVE, WM_MOUSELEAVE, WM_NCHITTEST, WM_WINDOWPOSCHANGED,
    WM_DESTROY, TITLE_BAR_HEIGHT, HTCLIENT
)

FENCE_WND_CLASS = "OmniToys_FenceContainerClass"
WM_QUIT = 0x0012


class DesktopFencesModule(ToyModule):
    def __init__(self):
        super().__init__(
            module_id="desktop_fences",
            name="桌面栅栏 (Desktop Fences)",
            description="微软 Windows 桌面图标与文件分区整理神器（对标 Stardock Fences）。支持半透明毛玻璃容器、双击卷起折叠、文件夹传送门与一键隐藏。",
            icon="fences"
        )
        self.fences: Dict[str, Win32FenceWindow] = {}
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._running: bool = False
        self._wnd_proc_ref = None
        self._is_all_hidden: bool = False
        self.is_windows = sys.platform.startswith("win")
        register_shutdown_handler(self.stop)

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "double_click_desktop_hide": True,
            "fences": [
                {
                    "id": "fence_shortcuts",
                    "title": "常用软件与快捷方式",
                    "folder_path": os.path.expanduser("~/Desktop/常用软件"),
                    "x": 80,
                    "y": 80,
                    "width": 260,
                    "height": 320,
                    "opacity": 210,
                    "is_rolled_up": False
                },
                {
                    "id": "fence_documents",
                    "title": "临时文档与表格",
                    "folder_path": os.path.expanduser("~/Desktop/工作文件"),
                    "x": 370,
                    "y": 80,
                    "width": 280,
                    "height": 320,
                    "opacity": 210,
                    "is_rolled_up": False
                }
            ]
        }

    def start(self):
        if not self.is_windows:
            return
        self._running = True
        self._thread = threading.Thread(target=self._win32_thread_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if not self.is_windows:
            return
        if self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        for fence in list(self.fences.values()):
            fence.destroy()
        self.fences.clear()

    def _win32_thread_loop(self):
        """Dedicated Win32 message thread with 0.0% idle CPU and 144Hz+ response."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()

        # 1. Register Class
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        def fence_wnd_proc(hwnd, msg, wparam, lparam):
            fence = self._get_fence_by_hwnd(hwnd)
            if fence:
                if msg == WM_NCHITTEST:
                    # Low-word = X, High-word = Y (screen coordinates)
                    screen_x = ctypes.c_short(lparam & 0xFFFF).value
                    screen_y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                    hit = fence.handle_nchittest(screen_x, screen_y)
                    if hit != HTCLIENT:
                        return hit

                elif msg == WM_PAINT:
                    fence.on_paint(hwnd)
                    return 0

                elif msg == WM_LBUTTONDOWN:
                    x = lparam & 0xFFFF
                    y = (lparam >> 16) & 0xFFFF
                    fence.handle_lbuttondown(x, y)
                    return 0

                elif msg == WM_LBUTTONDBLCLK:
                    # Double click on title bar -> roll up/down
                    y = (lparam >> 16) & 0xFFFF
                    if y <= TITLE_BAR_HEIGHT:
                        fence.toggle_roll_up()
                    return 0

                elif msg == WM_MOUSEMOVE:
                    x = lparam & 0xFFFF
                    y = (lparam >> 16) & 0xFFFF
                    fence.handle_mousemove(x, y)
                    return 0

                elif msg == WM_MOUSELEAVE:
                    fence.handle_mouseleave()
                    return 0

                elif msg == WM_WINDOWPOSCHANGED:
                    fence.handle_windowposchanged()
                    return 0

                elif msg == WM_DESTROY:
                    return 0

            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wnd_proc_ref = WNDPROC(fence_wnd_proc)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        wnd_class = WNDCLASSW()
        wnd_class.style = 0x0008  # CS_DBLCLKS
        wnd_class.lpfnWndProc = self._wnd_proc_ref
        wnd_class.lpszClassName = FENCE_WND_CLASS
        wnd_class.hCursor = user32.LoadCursorW(0, 32512)
        user32.RegisterClassW(ctypes.byref(wnd_class))

        # 2. Instantiate and create all fences from config
        saved_fences = self.config.get("fences", [])
        for f_data in saved_fences:
            fence = Win32FenceWindow(
                fence_id=f_data.get("id", str(uuid.uuid4())[:8]),
                title=f_data.get("title", "未命名栅栏"),
                folder_path=f_data.get("folder_path", os.path.expanduser("~/Desktop")),
                x=f_data.get("x", 100),
                y=f_data.get("y", 100),
                width=f_data.get("width", 260),
                height=f_data.get("height", 320),
                opacity=f_data.get("opacity", 210),
                is_rolled_up=f_data.get("is_rolled_up", False),
                on_change_callback=self._on_fence_changed
            )
            fence.create_window(FENCE_WND_CLASS)
            self.fences[fence.fence_id] = fence

        # 3. High-performance GetMessageW wait-state loop (0.00% idle CPU)
        msg = wintypes.MSG()
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret <= 0:  # WM_QUIT or error
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _get_fence_by_hwnd(self, hwnd) -> Optional[Win32FenceWindow]:
        for f in self.fences.values():
            if f.hwnd == hwnd:
                return f
        return None

    def _on_fence_changed(self, fence_id: str, updated_dict: Dict[str, Any]):
        fences_list = [f.to_dict() for f in self.fences.values()]
        self.config["fences"] = fences_list

    def get_state(self) -> Dict[str, Any]:
        fences_summary = []
        if self.fences:
            fences_summary = [f.to_dict() for f in self.fences.values()]
        else:
            fences_summary = self.config.get("fences", [])
        return {
            "is_all_hidden": self._is_all_hidden,
            "fences_count": len(fences_summary),
            "fences": fences_summary
        }

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "create_fence":
            title = payload.get("title", "新建栅栏")
            folder = payload.get("folder_path", os.path.expanduser(f"~/Desktop/{title}"))
            new_id = f"fence_{str(uuid.uuid4())[:8]}"

            new_fence_data = {
                "id": new_id,
                "title": title,
                "folder_path": folder,
                "x": 200,
                "y": 200,
                "width": 260,
                "height": 320,
                "opacity": 210,
                "is_rolled_up": False
            }
            self.config.setdefault("fences", []).append(new_fence_data)

            if self.is_windows and self._running:
                fence = Win32FenceWindow(
                    fence_id=new_id,
                    title=title,
                    folder_path=folder,
                    x=200, y=200, width=260, height=320, opacity=210,
                    on_change_callback=self._on_fence_changed
                )
                fence.create_window(FENCE_WND_CLASS)
                self.fences[new_id] = fence

            return {"status": "ok", "fence": new_fence_data}

        elif action == "delete_fence":
            f_id = payload.get("id")
            if f_id in self.fences:
                self.fences[f_id].destroy()
                del self.fences[f_id]
            self.config["fences"] = [f for f in self.config.get("fences", []) if f.get("id") != f_id]
            return {"status": "ok"}

        elif action == "toggle_rollup":
            f_id = payload.get("id")
            if f_id in self.fences:
                self.fences[f_id].toggle_roll_up()
                return {"status": "ok", "is_rolled_up": self.fences[f_id].is_rolled_up}
            return {"status": "not_found"}

        elif action == "toggle_all_visibility":
            self._is_all_hidden = not self._is_all_hidden
            if self.is_windows:
                user32 = ctypes.windll.user32
                cmd = 0 if self._is_all_hidden else 5
                for f in self.fences.values():
                    if f.hwnd:
                        user32.ShowWindow(f.hwnd, cmd)
            return {"status": "ok", "is_all_hidden": self._is_all_hidden}

        return {"status": "unknown_action"}

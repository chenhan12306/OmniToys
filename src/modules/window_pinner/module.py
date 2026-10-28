"""
PowerToys-style Window Pinner (Always on Top) Module.
Allows pinning the active window on top of all others with safe cleanup on exit.
The advertised Ctrl+Win+T hotkey is now registered with RegisterHotKey on a
dedicated message-loop thread.
"""

import sys
import ctypes
from ctypes import wintypes
import threading
from typing import Dict, Any, Set, Optional
from ..base_module import ToyModule
from ...core.safety_guard import register_shutdown_handler

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
WS_EX_TOPMOST = 0x00000008
GWL_EXSTYLE = -20

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUIT = 0x0012
WM_HOTKEY = 0x0312

MOD_CONTROL = 0x0002
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
HOTKEY_ID = 0xA17
HWND_MESSAGE = -3
HOTKEY_CLASS = "OmniToysHotkeyWindowClass"


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class WindowPinnerModule(ToyModule):
    def __init__(self):
        super().__init__(
            module_id="window_pinner",
            name="窗口置顶 (Always on Top)",
            description="一键将任意前台窗口（如计算器、记事本、播放器、参考文档）保持在最顶层显示。",
            icon="pin",
        )
        self.pinned_windows: Set[int] = set()
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._hwnd = None
        self._wnd_proc_ref = None
        self._hotkey_registered = False
        self._running = False
        self.is_windows = sys.platform.startswith("win")
        register_shutdown_handler(self.stop)

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "shortcut": "Ctrl+Win+T",
            "border_highlight": True,
        }

    # ------------------------------------------------------------- lifecycle
    def start(self):
        if not self.is_windows:
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._hotkey_thread, daemon=True, name="OmniToysHotkeyThread"
            )
            self._thread.start()

    def stop(self):
        with self._lock:
            self._running = False
            hwnd = self._hwnd
            thread = self._thread
            thread_id = self._thread_id
            self._thread = None

        if self.is_windows and hwnd:
            try:
                ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
            if thread.is_alive() and thread_id:
                try:
                    ctypes.windll.user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
                except Exception:
                    pass

        self._hotkey_registered = False
        self.unpin_all_safe()

    # ----------------------------------------------------------- hotkey thread
    def _hotkey_thread(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.CreateWindowExW.restype = wintypes.HWND
        self._thread_id = kernel32.GetCurrentThreadId()

        def sig(fn, restype, *argtypes):
            fn.restype = restype
            fn.argtypes = list(argtypes)

        sig(user32.CreateWindowExW, wintypes.HWND,
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HANDLE, wintypes.HINSTANCE, wintypes.LPVOID)
        sig(user32.DefWindowProcW, ctypes.c_ssize_t,
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        sig(user32.DestroyWindow, wintypes.BOOL, wintypes.HWND)
        sig(user32.PostMessageW, wintypes.BOOL, wintypes.HWND, wintypes.UINT,
            wintypes.WPARAM, wintypes.LPARAM)
        sig(user32.PostThreadMessageW, wintypes.BOOL, wintypes.DWORD, wintypes.UINT,
            wintypes.WPARAM, wintypes.LPARAM)
        sig(user32.PostQuitMessage, None, ctypes.c_int)
        sig(user32.RegisterHotKey, wintypes.BOOL, wintypes.HWND, ctypes.c_int,
            wintypes.UINT, wintypes.UINT)
        sig(user32.UnregisterHotKey, wintypes.BOOL, wintypes.HWND, ctypes.c_int)
        sig(user32.GetMessageW, wintypes.BOOL, ctypes.POINTER(wintypes.MSG),
            wintypes.HWND, wintypes.UINT, wintypes.UINT)
        sig(user32.TranslateMessage, wintypes.BOOL, ctypes.POINTER(wintypes.MSG))
        sig(user32.DispatchMessageW, ctypes.c_ssize_t, ctypes.POINTER(wintypes.MSG))
        sig(user32.GetForegroundWindow, wintypes.HWND)
        sig(user32.GetWindowTextW, ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        sig(get_long, ctypes.c_ssize_t, wintypes.HWND, ctypes.c_int)
        sig(user32.IsWindow, wintypes.BOOL, wintypes.HWND)
        sig(user32.SetWindowPos, wintypes.BOOL, wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)

        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_HOTKEY:
                if wparam == HOTKEY_ID:
                    self.pin_foreground_window()
                return 0
            if msg == WM_CLOSE:
                try:
                    user32.UnregisterHotKey(hwnd, HOTKEY_ID)
                except Exception:
                    pass
                self._hotkey_registered = False
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wnd_proc_ref = WNDPROC(wnd_proc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = ctypes.cast(self._wnd_proc_ref, ctypes.c_void_p).value
        wc.lpszClassName = HOTKEY_CLASS
        user32.RegisterClassW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(
            0,
            HOTKEY_CLASS,
            "OmniToysHotkey",
            0,
            0,
            0,
            0,
            0,
            wintypes.HWND(HWND_MESSAGE),
            0,
            0,
            None,
        )
        self._hwnd = hwnd
        if not hwnd:
            print("[WindowPinner] Could not create hotkey message window")
            self._running = False
            return

        try:
            ok = user32.RegisterHotKey(
                hwnd, HOTKEY_ID, MOD_CONTROL | MOD_WIN | MOD_NOREPEAT, ord("T")
            )
            self._hotkey_registered = bool(ok)
            if not ok:
                print(
                    "[WindowPinner] RegisterHotKey(Ctrl+Win+T) failed; "
                    "the hotkey may be reserved by another application."
                )

            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            try:
                user32.UnregisterHotKey(hwnd, HOTKEY_ID)
            except Exception:
                pass
            self._hotkey_registered = False
            self._hwnd = None

    # ------------------------------------------------------------------ pinning
    def unpin_all_safe(self):
        """Restores all pinned windows so none is permanently stuck topmost."""
        if not self.is_windows:
            return
        with self._lock:
            handles = list(self.pinned_windows)
            self.pinned_windows.clear()

        try:
            user32 = ctypes.windll.user32
            for hwnd in handles:
                if user32.IsWindow(hwnd):
                    user32.SetWindowPos(
                        hwnd,
                        HWND_NOTOPMOST,
                        0,
                        0,
                        0,
                        0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                    )
        except Exception:
            pass

    def pin_foreground_window(self) -> Dict[str, Any]:
        """Toggles the topmost state of the currently focused foreground window."""
        if not self.is_windows:
            return {"status": "unsupported_platform"}

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"status": "no_window"}

        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value or "Untitled Window"

        get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        get_long.restype = ctypes.c_ssize_t
        ex_style = get_long(hwnd, GWL_EXSTYLE)
        is_topmost = bool(ex_style & WS_EX_TOPMOST)

        with self._lock:
            if is_topmost:
                user32.SetWindowPos(
                    hwnd,
                    HWND_NOTOPMOST,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                )
                self.pinned_windows.discard(hwnd)
                state_str = "unpinned"
            else:
                user32.SetWindowPos(
                    hwnd,
                    HWND_TOPMOST,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                )
                self.pinned_windows.add(hwnd)
                state_str = "pinned"
            count = len(self.pinned_windows)

        return {
            "status": "ok",
            "hwnd": hwnd,
            "title": title,
            "state": state_str,
            "pinned_count": count,
        }

    # ---------------------------------------------------------------- UI state
    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "shortcut": self.config.get("shortcut", "Ctrl+Win+T"),
                "hotkey_registered": self._hotkey_registered,
                "pinned_count": len(self.pinned_windows),
            }

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "pin_current":
            return self.pin_foreground_window()
        return {"status": "unknown_action"}

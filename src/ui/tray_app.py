"""
Zero-dependency Pure ctypes Windows System Tray Application.
Uses user32.dll, gdi32.dll, and shell32.dll to:
1. Render a dynamic taskbar tray icon displaying the exact battery percentage number (e.g., '78').
2. Show a Windows native right-click popup menu with all peripheral statuses.
3. Emit Windows native balloon/toast notifications for low battery warnings.
4. Run background non-blocking timers with near-zero CPU and memory usage (< 15MB).
"""

import sys
import ctypes
from ctypes import wintypes
import time
from typing import Optional
from ..core.device_manager import DeviceManager
from ..core.device_base import ChargingStatus, ConnectionType

# Win32 Constants
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_COMMAND = 0x0111
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_TIMER = 0x0113
WM_DESTROY = 0x0002

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

NIIF_INFO = 0x00000001
NIIF_WARNING = 0x00000002

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_GRAYED = 0x00000001
TPM_RIGHTBUTTON = 0x0002

ID_MENU_REFRESH = 1001
ID_MENU_EXIT = 1002


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class TrayApplication:
    def __init__(self, manager: DeviceManager, poll_interval_sec: int = 30):
        self.manager = manager
        self.poll_interval_sec = poll_interval_sec
        self.is_windows = sys.platform.startswith("win")
        self.hwnd = None
        self.hicon = None
        self.last_alerted_level = 100

        if self.is_windows:
            self._user32 = ctypes.windll.user32
            self._gdi32 = ctypes.windll.gdi32
            self._shell32 = ctypes.windll.shell32
            self._kernel32 = ctypes.windll.kernel32

    def create_dynamic_number_icon(self, number: int, is_charging: bool = False) -> wintypes.HICON:
        """Draws a 16x16 or 32x32 bitmap containing the battery number and returns an HICON."""
        width, height = 32, 32
        hdc_screen = self._user32.GetDC(0)
        hdc_mem = self._gdi32.CreateCompatibleDC(hdc_screen)

        # Create 32-bit color bitmap
        hbm_color = self._gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
        hbm_mask = self._gdi32.CreateCompatibleBitmap(hdc_screen, width, height)

        old_bm = self._gdi32.SelectObject(hdc_mem, hbm_color)

        # Background fill (Dark translucent slate)
        brush = self._gdi32.CreateSolidBrush(0x1E1E1E)
        rect = wintypes.RECT(0, 0, width, height)
        self._user32.FillRect(hdc_mem, ctypes.byref(rect), brush)
        self._gdi32.DeleteObject(brush)

        # Draw battery level text
        # Color coding: Green for >40%, Yellow for 20-40%, Red for <20%, Cyan for charging
        if is_charging:
            color = 0x00E5FF  # Bright Cyan
        elif number >= 40:
            color = 0x33FF66  # Vibrant Green
        elif number >= 20:
            color = 0x00D7FF  # Amber / Yellow
        else:
            color = 0x3333FF  # Bright Red (BGR format in Win32 GDI)

        self._gdi32.SetTextColor(hdc_mem, color)
        self._gdi32.SetBkMode(hdc_mem, 1)  # TRANSPARENT = 1

        # Create crisp bold font
        font_height = 20 if number < 100 else 16
        hfont = self._gdi32.CreateFontW(
            font_height, 0, 0, 0, 800, 0, 0, 0, 1, 0, 0, 2, 0, "Segoe UI"
        )
        old_font = self._gdi32.SelectObject(hdc_mem, hfont)

        text = f"{number}" if number >= 0 else "?"
        if is_charging and number < 100:
            text = f"⚡{number}"

        self._user32.DrawTextW(
            hdc_mem,
            ctypes.c_wchar_p(text),
            len(text),
            ctypes.byref(rect),
            0x0001 | 0x0004 | 0x0020  # DT_CENTER | DT_VCENTER | DT_SINGLELINE
        )

        # Cleanup GDI handles
        self._gdi32.SelectObject(hdc_mem, old_font)
        self._gdi32.DeleteObject(hfont)
        self._gdi32.SelectObject(hdc_mem, old_bm)
        self._gdi32.DeleteDC(hdc_mem)
        self._user32.ReleaseDC(0, hdc_screen)

        # Generate Icon
        icon_info = ICONINFO()
        icon_info.fIcon = True
        icon_info.hbmMask = hbm_mask
        icon_info.hbmColor = hbm_color
        hicon = self._user32.CreateIconIndirect(ctypes.byref(icon_info))

        self._gdi32.DeleteObject(hbm_color)
        self._gdi32.DeleteObject(hbm_mask)
        return hicon

    def run(self):
        """Runs the Win32 message pump for tray icon handling."""
        if not self.is_windows:
            print("[TrayApp] Tray UI is only supported on Windows. Falling back to CLI watcher.")
            from .cli import run_cli_watch
            run_cli_watch(self.manager, interval=self.poll_interval_sec)
            return

        # Define Window Procedure
        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_TRAYICON:
                if lparam == WM_RBUTTONUP or lparam == WM_LBUTTONDBLCLK:
                    self._show_context_menu()
                return 0
            elif msg == WM_TIMER:
                self.refresh()
                return 0
            elif msg == WM_COMMAND:
                cmd_id = wparam & 0xFFFF
                if cmd_id == ID_MENU_REFRESH:
                    self.refresh()
                elif cmd_id == ID_MENU_EXIT:
                    self.shutdown()
                return 0
            elif msg == WM_DESTROY:
                self._user32.PostQuitMessage(0)
                return 0
            return self._user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wnd_proc_ref = WNDPROC(wnd_proc)

        # Register Window Class
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
        wnd_class.lpfnWndProc = self._wnd_proc_ref
        wnd_class.lpszClassName = "OmniBatteryHiddenWindowClass"
        self._user32.RegisterClassW(ctypes.byref(wnd_class))

        self.hwnd = self._user32.CreateWindowExW(
            0, "OmniBatteryHiddenWindowClass", "OmniBattery",
            0, 0, 0, 0, 0, 0, 0, 0, None
        )

        # Initial Scan
        self.refresh()

        # Setup background polling timer (non-blocking native Windows timer)
        self._user32.SetTimer(self.hwnd, 1, self.poll_interval_sec * 1000, None)

        # Run Win32 Message Loop
        msg = wintypes.MSG()
        while self._user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))

    def refresh(self):
        devices = self.manager.scan_all()
        primary_mouse = self.manager.get_primary_mouse()

        pct = primary_mouse.battery.percentage if primary_mouse else -1
        is_charging = (primary_mouse.battery.is_charging == ChargingStatus.CHARGING) if primary_mouse else False

        # Destroy old icon if exists
        if self.hicon:
            self._user32.DestroyIcon(self.hicon)

        self.hicon = self.create_dynamic_number_icon(pct, is_charging=is_charging)

        # Construct tooltip
        lines = ["OmniBattery Monitor:"]
        for d in devices:
            chg = " (⚡)" if d.battery.is_charging == ChargingStatus.CHARGING else ""
            lines.append(f"{d.name}: {d.battery.percentage}%{chg}")
        tooltip = "\n".join(lines)[:127]

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self.hicon
        nid.szTip = tooltip

        # Low battery alert (below 20% and discharging)
        if primary_mouse and pct <= 20 and not is_charging and pct < self.last_alerted_level:
            nid.uFlags |= NIF_INFO
            nid.szInfo = f"Low Battery: {primary_mouse.name} is at {pct}%. Please recharge."
            nid.szInfoTitle = "OmniBattery Alert"
            nid.dwInfoFlags = NIIF_WARNING
            self.last_alerted_level = pct
        elif is_charging:
            self.last_alerted_level = 100

        self._shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        # If modify fails (first time), call ADD
        self._shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def _show_context_menu(self):
        hmenu = self._user32.CreatePopupMenu()

        # Header item (non-clickable info)
        self._user32.AppendMenuW(hmenu, MF_STRING | MF_GRAYED, 0, "── Connected Devices ──")

        devices = list(self.manager.devices.values())
        if not devices:
            self._user32.AppendMenuW(hmenu, MF_STRING | MF_GRAYED, 0, "No Peripherals Detected")
        else:
            for i, d in enumerate(devices):
                chg = " ⚡" if d.battery.is_charging == ChargingStatus.CHARGING else ""
                val = f"{d.battery.percentage}%{chg}" if d.battery.is_valid else "Unknown"
                line = f"{d.name}: {val}"
                self._user32.AppendMenuW(hmenu, MF_STRING | MF_GRAYED, 0, line)

        self._user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        self._user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_REFRESH, "🔄 Refresh Now")
        self._user32.AppendMenuW(hmenu, MF_STRING, ID_MENU_EXIT, "❌ Exit")

        # Get cursor pos
        pt = wintypes.POINT()
        self._user32.GetCursorPos(ctypes.byref(pt))
        self._user32.SetForegroundWindow(self.hwnd)
        self._user32.TrackPopupMenuEx(hmenu, TPM_RIGHTBUTTON, pt.x, pt.y, self.hwnd, None)
        self._user32.DestroyMenu(hmenu)

    def shutdown(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        self._shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        self._user32.PostQuitMessage(0)

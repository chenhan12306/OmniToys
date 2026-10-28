"""
Windows "run at login" integration.

Uses HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run, so it needs no
administrator rights and never touches machine-wide settings.
"""

import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "OmniToys"


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.abspath(sys.argv[0])
    executable = sys.executable
    if not executable:
        return f'"{script}"'
    # Prefer pythonw.exe so the login item never flashes a console window.
    pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
    if os.path.exists(pythonw):
        executable = pythonw
    return f'"{executable}" "{script}"'


def is_enabled() -> bool:
    if not _is_windows():
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """Creates or removes the HKCU Run entry. Returns True on success."""
    if not _is_windows():
        return False
    try:
        import winreg

        if enabled:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
        return True
    except OSError as exc:
        print(f"[startup] Could not update login item: {exc}")
        return False

"""
Safety Guard & Clean Shutdown Engine for OmniToys.
Ensures zero system pollution and safe state restoration even on unexpected / forced exits:
1. Automatically resets Windows thread execution state (SetThreadExecutionState -> ES_CONTINUOUS).
2. Unpins all topmost windows pinned by Window Pinner.
3. Deletes system tray icon (eliminates ghost icons on the Windows taskbar).
4. Closes all fence windows and destroys GDI handles.
5. Catches SIGINT, SIGTERM, atexit, and Windows Console Ctrl Events (logoff, shutdown, close).
"""

import sys
import os
import atexit
import signal
from typing import List, Callable

_shutdown_handlers: List[Callable[[], None]] = []
_has_cleaned_up: bool = False


def register_shutdown_handler(handler: Callable[[], None]):
    """Registers a cleanup callback to be called unconditionally on exit."""
    _shutdown_handlers.append(handler)


def execute_emergency_cleanup():
    """Runs all registered shutdown handlers safely."""
    global _has_cleaned_up
    if _has_cleaned_up:
        return
    _has_cleaned_up = True

    for handler in _shutdown_handlers:
        try:
            handler()
        except Exception:
            pass


def init_safety_guard():
    """Initializes global exit hooks for Windows and Unix."""
    # 1. Standard Python exit
    atexit.register(execute_emergency_cleanup)

    # 2. Posix & Windows signals
    try:
        signal.signal(signal.SIGINT, lambda s, f: (execute_emergency_cleanup(), sys.exit(0)))
    except Exception:
        pass

    try:
        signal.signal(signal.SIGTERM, lambda s, f: (execute_emergency_cleanup(), sys.exit(0)))
    except Exception:
        pass

    # 3. Native Windows Console & System Session Handlers
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            PHANDLER_ROUTINE = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

            def win_ctrl_handler(dwCtrlType):
                # 0: CTRL_C, 1: CTRL_BREAK, 2: CTRL_CLOSE, 5: CTRL_LOGOFF, 6: CTRL_SHUTDOWN
                execute_emergency_cleanup()
                return False  # Pass to default handler

            _global_ctrl_ref = PHANDLER_ROUTINE(win_ctrl_handler)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_global_ctrl_ref, True)
        except Exception:
            pass

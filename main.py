"""
OmniToys - Main Entry Point.
Modern PowerToys-like Toolbox for Windows:
- Multi-protocol peripheral battery monitoring (Logitech Lightspeed, Bluetooth, 2.4G)
- Keep-Awake module (prevent sleep/screen-off)
- Window Pinner (Always on Top)
- System Tray presence with dynamic battery badge
- Modern Windows 11 Fluent Design Dashboard
"""

import os
import sys
import argparse
import threading
from src.core.app_host import AppHost
from src.gui.window import ModernWindowHost
from src.ui.cli import run_cli_once, run_cli_watch
from src.ui.tray_app import TrayApplication
from src.core.safety_guard import init_safety_guard


def main():
    # Initialize global safety guard for clean exits
    init_safety_guard()

    parser = argparse.ArgumentParser(
        description="OmniToys - Modern PowerToys-style Peripheral & Efficiency Toolbox"
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the modern Fluent UI Dashboard window (Default)",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="Run silently in background system tray mode only (no initial GUI popup)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Query device batteries once in terminal and exit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output device battery data in JSON format",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously watch device battery statuses in terminal",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in simulation/mock mode for development",
    )

    args = parser.parse_args()

    host = AppHost(enable_mock=args.mock)

    # CLI modes must not start tray / hotkey machinery.
    if args.once or args.json or args.watch:
        battery_mod = host.modules.get("omni_battery")
        if battery_mod:
            if args.watch:
                run_cli_watch(battery_mod.device_manager)
            else:
                run_cli_once(battery_mod.device_manager, as_json=args.json)
        return

    # Full toolbox: start enabled modules, then tray + optional dashboard.
    host.start_all()
    window = ModernWindowHost(host)
    battery_mod = host.modules.get("omni_battery")
    tray_app = None
    tray_thread = None

    if battery_mod:
        def on_open_gui():
            window.show_or_focus()

        def on_exit():
            # Called on the tray thread. Clean what we can, then leave immediately;
            # os._exit avoids hanging on a cross-thread WebView destroy.
            try:
                tray_app.shutdown()
            except Exception:
                pass
            host.stop_all()
            os._exit(0)

        tray_app = TrayApplication(
            battery_mod.device_manager,
            on_open_gui=on_open_gui,
            on_exit=on_exit,
            alert_threshold_getter=lambda: int(
                battery_mod.config.get("alert_threshold", 20) or 20
            ),
            enabled_getter=lambda: battery_mod.is_enabled,
            poll_interval_getter=lambda: int(
                battery_mod.config.get("poll_interval", 30) or 30
            ),
        )

        if sys.platform.startswith("win"):
            # Non-daemon keeps the tray alive even if the GUI window is hidden.
            tray_thread = threading.Thread(
                target=tray_app.run, daemon=False, name="OmniToysTrayThread"
            )
            tray_thread.start()
        elif args.tray:
            # Fallback on non-Windows CLI if explicit --tray requested
            tray_app.run()
            return

    if args.tray:
        print("[OmniToys] Running resident in system tray. Double-click tray badge to open GUI.")
        if tray_thread:
            try:
                tray_thread.join()
            except KeyboardInterrupt:
                tray_app.shutdown()
                host.stop_all()
        return

    # Default: show the Modern Fluent UI Dashboard.
    gui_running = window.show()

    if gui_running:
        # The native WebView returned, i.e. the user really closed the window.
        host.stop_all()
        if tray_app:
            tray_app.shutdown()
        if tray_thread and tray_thread.is_alive():
            tray_thread.join(timeout=1.5)
        window.stop_server()
    else:
        # Browser fallback: stay resident in the tray until the user exits.
        if tray_thread:
            try:
                tray_thread.join()
            except KeyboardInterrupt:
                tray_app.shutdown()
                host.stop_all()
        else:
            window.stop_server()


if __name__ == "__main__":
    main()

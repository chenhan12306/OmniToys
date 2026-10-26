"""
OmniToys - Main Entry Point.
Modern PowerToys-like Toolbox for Windows:
- Multi-protocol peripheral battery monitoring (Logitech Lightspeed, Bluetooth, 2.4G)
- Keep-Awake module (prevent sleep/screen-off)
- Window Pinner (Always on Top)
- System Tray presence with dynamic battery badge
- Modern Windows 11 Fluent Design Dashboard
"""

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
        "--gui", action="store_true",
        help="Launch the modern Fluent UI Dashboard window (Default)"
    )
    parser.add_argument(
        "--tray", action="store_true",
        help="Run silently in background system tray mode only (no initial GUI popup)"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Query device batteries once in terminal and exit"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output device battery data in JSON format"
    )
    parser.add_argument(
        "--watch", action="store_true",
        help="Continuously watch device battery statuses in terminal"
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="Run in simulation/mock mode for development"
    )

    args = parser.parse_args()

    # Initialize PowerToys Core Host
    host = AppHost(enable_mock=args.mock)
    host.start_all()

    if args.json or args.once:
        battery_mod = host.modules.get("omni_battery")
        if battery_mod:
            run_cli_once(battery_mod.device_manager, as_json=args.json)
        return

    if args.watch:
        battery_mod = host.modules.get("omni_battery")
        if battery_mod:
            run_cli_watch(battery_mod.device_manager)
        return

    window = ModernWindowHost(host)
    battery_mod = host.modules.get("omni_battery")
    tray_app = None
    tray_thread = None

    if battery_mod:
        def on_open_gui():
            window.show_or_focus()

        def on_exit():
            window.destroy()
            host.stop_all()
            sys.exit(0)

        tray_app = TrayApplication(
            battery_mod.device_manager,
            on_open_gui=on_open_gui,
            on_exit=on_exit
        )

        if sys.platform.startswith("win"):
            # Resident tray application running in dedicated message loop thread
            # Non-daemon ensures tray stays alive even if GUI window is closed/hidden
            tray_thread = threading.Thread(
                target=tray_app.run, daemon=False, name="OmniToysTrayThread"
            )
            tray_thread.start()
        elif args.tray:
            # Fallback on non-windows CLI if explicit --tray requested
            tray_app.run()
            return

    if args.tray:
        print("[OmniToys] Running resident in system tray. Double-click tray badge to open GUI.")
        if tray_thread:
            try:
                tray_thread.join()
            except KeyboardInterrupt:
                host.stop_all()
        return

    # Default: Show Modern Fluent UI Dashboard
    # Tray icon is already resident in taskbar notification area
    window.show()


if __name__ == "__main__":
    main()

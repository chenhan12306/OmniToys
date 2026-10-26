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
        help="Run in background system tray mode only"
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

    if args.tray:
        # Background tray mode
        battery_mod = host.modules.get("omni_battery")
        if battery_mod:
            app = TrayApplication(battery_mod.device_manager)
            app.run()
        return

    # Default: Modern Fluent UI Dashboard
    window = ModernWindowHost(host)
    window.show()


if __name__ == "__main__":
    main()

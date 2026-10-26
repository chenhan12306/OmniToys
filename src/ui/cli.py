"""
Command Line Interface for OmniBattery.
Provides fast querying, JSON formatting, or continuous terminal watch mode.
"""

import sys
import time
import json
from ..core.device_manager import DeviceManager
from ..core.device_base import ChargingStatus


def print_colored(text: str, color: str = ""):
    colors = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "cyan": "\033[96m",
        "bold": "\033[1m",
        "reset": "\033[0m"
    }
    prefix = colors.get(color, "")
    suffix = colors["reset"] if prefix else ""
    print(f"{prefix}{text}{suffix}")


def format_battery_bar(pct: int, length: int = 15) -> str:
    if pct < 0:
        return "[Unknown]"
    filled = int(length * pct / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {pct}%"


def run_cli_once(manager: DeviceManager, as_json: bool = False):
    devices = manager.scan_all()
    if as_json:
        data = []
        for d in devices:
            data.append({
                "id": d.device_id,
                "name": d.name,
                "category": d.category.value,
                "type": d.connection_type.value,
                "percentage": d.battery.percentage,
                "charging": d.battery.is_charging.value,
                "voltage_mv": d.battery.voltage_mv,
                "online": d.is_online
            })
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    print_colored("\n================ OmniBattery Device Battery Status ================", "bold")
    if not devices:
        print_colored("  No compatible 2.4G / Bluetooth / Logitech devices found.", "yellow")
        print_colored("===================================================================\n", "bold")
        return

    for dev in devices:
        pct = dev.battery.percentage
        color = "green" if pct >= 50 else ("yellow" if pct >= 20 else "red")
        chg_mark = " ⚡ [Charging]" if dev.battery.is_charging == ChargingStatus.CHARGING else ""
        bar = format_battery_bar(pct)
        print(f" • {dev.name} ({dev.connection_type.value})")
        print_colored(f"     Battery: {bar}{chg_mark}", color)
        if dev.battery.voltage_mv:
            print(f"     Voltage: {dev.battery.voltage_mv} mV")
        print()
    print_colored("===================================================================\n", "bold")


def run_cli_watch(manager: DeviceManager, interval: int = 5):
    print_colored("Starting OmniBattery Watcher (Press Ctrl+C to exit)...", "cyan")
    try:
        while True:
            # Clear screen (ANSI or cls)
            print("\033[2J\033[H", end="")
            run_cli_once(manager)
            print_colored(f"Refreshed at {time.strftime('%H:%M:%S')}. Next scan in {interval}s...", "cyan")
            time.sleep(interval)
    except KeyboardInterrupt:
        print_colored("\nExited.", "yellow")

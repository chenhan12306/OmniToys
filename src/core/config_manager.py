"""
Persistent Configuration Manager.
Stores user settings and per-module configs in a local JSON file.
"""

import os
import json
from typing import Dict, Any


DEFAULT_CONFIG: Dict[str, Any] = {
    "global": {
        "run_on_startup": False,
        "minimize_to_tray": True,
        "theme": "dark",
        "close_to_tray": True
    },
    "modules": {
        "omni_battery": {
            "enabled": True,
            "poll_interval": 30,
            "alert_threshold": 20,
            "show_percentage_in_tray": True
        },
        "awake": {
            "enabled": False,
            "mode": "indefinite",  # indefinite, timed, passive
            "keep_screen_on": True
        },
        "window_pinner": {
            "enabled": True,
            "hotkey": "Ctrl+Win+T",
            "play_sound": True
        }
    }
}


class ConfigManager:
    def __init__(self, config_path: str = "omnitoys_config.json"):
        self.config_path = config_path
        self.config = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Merge with default config
                    merged = DEFAULT_CONFIG.copy()
                    merged["global"].update(data.get("global", {}))
                    merged_modules = merged["modules"].copy()
                    merged_modules.update(data.get("modules", {}))
                    merged["modules"] = merged_modules
                    return merged
            except Exception:
                pass
        return DEFAULT_CONFIG.copy()

    def save(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ConfigManager] Error saving config: {e}")

    def get_global(self, key: str, default: Any = None) -> Any:
        return self.config.get("global", {}).get(key, default)

    def set_global(self, key: str, value: Any):
        self.config.setdefault("global", {})[key] = value
        self.save()

    def get_module_config(self, module_id: str) -> Dict[str, Any]:
        return self.config.get("modules", {}).get(module_id, {})

    def set_module_config(self, module_id: str, new_conf: Dict[str, Any]):
        self.config.setdefault("modules", {})[module_id] = new_conf
        self.save()

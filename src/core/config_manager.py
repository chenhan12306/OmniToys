"""
Persistent Configuration Manager.
Stores user settings and per-module configs in a local JSON file.

The file lives in %APPDATA%\\OmniToys by default (never the current working
directory), is written atomically, and all default dictionaries are deep-copied
so one ConfigManager instance can never mutate the module-level defaults.
"""

import copy
import os
import json
import tempfile
import threading
from typing import Dict, Any, Optional


DEFAULT_CONFIG: Dict[str, Any] = {
    "global": {
        "run_on_startup": False,
        "minimize_to_tray": True,
        "theme": "dark",
        "close_to_tray": True,
    },
    "modules": {
        "omni_battery": {
            "enabled": True,
            "poll_interval": 30,
            "alert_threshold": 20,
            "show_percentage_in_tray": True,
        },
        "awake": {
            "enabled": False,
            "mode": "indefinite",
            "keep_screen_on": True,
        },
        "window_pinner": {
            "enabled": True,
            "shortcut": "Ctrl+Win+T",
            "border_highlight": True,
        },
    },
}


def default_config_path() -> str:
    """Returns the per-user configuration path (never the process CWD)."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "OmniToys", "omnitoys_config.json")


class ConfigManager:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = os.path.abspath(config_path) if config_path else default_config_path()
        self._lock = threading.RLock()
        self.config = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = copy.deepcopy(DEFAULT_CONFIG)
                if isinstance(data.get("global"), dict):
                    merged["global"].update(data["global"])
                saved_modules = data.get("modules", {})
                if isinstance(saved_modules, dict):
                    for module_id, module_conf in saved_modules.items():
                        current = merged["modules"].get(module_id)
                        if isinstance(current, dict) and isinstance(module_conf, dict):
                            current.update(module_conf)
                        else:
                            merged["modules"][module_id] = copy.deepcopy(module_conf)
                return merged
            except Exception as exc:
                print(f"[ConfigManager] Could not read {self.config_path}: {exc}")
        return copy.deepcopy(DEFAULT_CONFIG)

    def save(self):
        with self._lock:
            try:
                folder = os.path.dirname(self.config_path)
                if folder:
                    os.makedirs(folder, exist_ok=True)
                fd, tmp_path = tempfile.mkstemp(
                    prefix=".omnitoys-", suffix=".json", dir=folder or "."
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(self.config, f, indent=2, ensure_ascii=False)
                    os.replace(tmp_path, self.config_path)
                except Exception:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    raise
            except Exception as e:
                print(f"[ConfigManager] Error saving config: {e}")

    def get_global(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.config.get("global", {}).get(key, default)

    def get_global_settings(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self.config.get("global", {}))

    def set_global(self, key: str, value: Any):
        with self._lock:
            self.config.setdefault("global", {})[key] = value
            self.save()

    def get_module_config(self, module_id: str) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self.config.get("modules", {}).get(module_id, {}))

    def set_module_config(self, module_id: str, new_conf: Dict[str, Any]):
        with self._lock:
            self.config.setdefault("modules", {})[module_id] = copy.deepcopy(new_conf)
            self.save()

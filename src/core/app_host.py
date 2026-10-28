"""
Central AppHost Engine.
The runner lifecycle coordinator that manages modules, configuration, and UI bridges.
"""

from typing import Dict, List, Any, Optional
import copy
from .config_manager import ConfigManager
from . import startup
from ..modules.base_module import ToyModule
from ..modules.omni_battery.module import OmniBatteryModule
from ..modules.awake.module import AwakeModule
from ..modules.window_pinner.module import WindowPinnerModule
from ..modules.power_rename.module import PowerRenameModule


class AppHost:
    ALLOWED_GLOBAL_KEYS = {"run_on_startup", "minimize_to_tray", "theme", "close_to_tray"}

    def __init__(
        self,
        enable_mock: bool = False,
        config_path: Optional[str] = None,
    ):
        self.config_manager = ConfigManager(config_path)
        self.enable_mock = enable_mock
        self.modules: Dict[str, ToyModule] = {}
        self._started: set = set()

        # Register default modules
        self._register_default_modules()

    def _register_default_modules(self):
        default_list = [
            OmniBatteryModule(enable_mock=self.enable_mock),
            PowerRenameModule(),
            AwakeModule(),
            WindowPinnerModule(),
        ]
        for mod in default_list:
            self.register_module(mod)

    def register_module(self, module: ToyModule):
        saved_conf = self.config_manager.get_module_config(module.module_id)
        module.init_config(saved_conf)
        module.set_config_saver(
            lambda m=module: self.config_manager.set_module_config(m.module_id, m.config)
        )
        self.modules[module.module_id] = module

    # ------------------------------------------------------------- Lifecycle
    def start_module(self, module_id: str, force: bool = False) -> bool:
        mod = self.modules.get(module_id)
        if not mod:
            return False
        if not force and not mod.is_enabled:
            return False
        if module_id in self._started:
            return True
        mod.start()
        self._started.add(module_id)
        return True

    def stop_module(self, module_id: str) -> bool:
        mod = self.modules.get(module_id)
        if not mod:
            return False
        try:
            mod.stop()
        except Exception as exc:
            print(f"[AppHost] Error stopping module '{mod.name}': {exc}")
        self._started.discard(module_id)
        return True

    def start_all(self):
        """Starts all enabled modules."""
        for module_id, mod in self.modules.items():
            if not mod.is_enabled:
                continue
            try:
                self.start_module(module_id)
            except Exception as e:
                print(f"[AppHost] Failed to start module '{mod.name}': {e}")

    def stop_all(self):
        """Gracefully stops all running modules."""
        for module_id in list(self._started):
            self.stop_module(module_id)

    def toggle_module(self, module_id: str, enabled: bool) -> bool:
        """Enables or disables a module at runtime."""
        mod = self.modules.get(module_id)
        if not mod:
            return False
        if mod.is_enabled == enabled:
            return True

        previous = mod.is_enabled
        mod.is_enabled = enabled
        mod.config["enabled"] = enabled
        try:
            if enabled:
                self.start_module(module_id, force=True)
            else:
                self.stop_module(module_id)
        except Exception as exc:
            # Roll back so the UI and the actual state stay consistent.
            mod.is_enabled = previous
            mod.config["enabled"] = previous
            print(f"[AppHost] Could not toggle '{mod.name}': {exc}")
            return False

        self.config_manager.set_module_config(module_id, mod.config)
        return True

    # ------------------------------------------------------------- Dashboard
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Provides an aggregated summary for the main Dashboard overview."""
        modules_info = []
        for mod in self.modules.values():
            modules_info.append(
                {
                    "id": mod.module_id,
                    "name": mod.name,
                    "description": mod.description,
                    "icon": mod.icon,
                    "enabled": mod.is_enabled,
                    "state": mod.get_state(),
                }
            )
        global_settings = self.config_manager.get_global_settings()
        # Reflect the real registry state instead of a possibly stale JSON value.
        try:
            global_settings["run_on_startup"] = startup.is_enabled()
        except Exception:
            pass
        return {
            "app_name": "OmniToys (全能工具箱)",
            "version": "1.0.0",
            "global_settings": global_settings,
            "modules": modules_info,
        }

    def set_global_setting(self, key: str, value: Any) -> Dict[str, Any]:
        if key not in self.ALLOWED_GLOBAL_KEYS:
            return {"status": "error", "message": f"Unknown setting: {key}"}

        if key == "run_on_startup":
            if not startup.set_enabled(bool(value)):
                return {
                    "status": "error",
                    "message": "无法写入开机启动项（仅支持 Windows 或权限不足）",
                }
            value = bool(value)
        elif key in ("minimize_to_tray", "close_to_tray"):
            value = bool(value)
        elif key == "theme":
            value = str(value)

        self.config_manager.set_global(key, value)
        return {"status": "ok", "key": key, "value": value}

    # ---------------------------------------------------------------- Actions
    def dispatch_action(
        self, module_id: str, action: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Routes UI actions to the respective module."""
        mod = self.modules.get(module_id)
        if not mod:
            return {"status": "error", "message": f"Module {module_id} not found"}
        before = copy.deepcopy(mod.config)
        try:
            res = mod.handle_action(action, payload)
        except Exception as exc:
            return {"status": "error", "message": str(exc)}
        # Avoid writing the config file for read-only actions such as
        # preview/scan/refresh on every keystroke.
        if mod.config != before:
            self.config_manager.set_module_config(module_id, mod.config)
        return res

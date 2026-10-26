"""
Central AppHost Engine.
The runner lifecycle coordinator that manages modules, configuration, and UI bridges.
"""

from typing import Dict, List, Any, Optional
from .config_manager import ConfigManager
from ..modules.base_module import ToyModule
from ..modules.omni_battery.module import OmniBatteryModule
from ..modules.awake.module import AwakeModule
from ..modules.window_pinner.module import WindowPinnerModule
from ..modules.power_rename.module import PowerRenameModule


class AppHost:
    def __init__(self, enable_mock: bool = False, config_path: str = "omnitoys_config.json"):
        self.config_manager = ConfigManager(config_path)
        self.enable_mock = enable_mock
        self.modules: Dict[str, ToyModule] = {}

        # Register default modules
        self._register_default_modules()

    def _register_default_modules(self):
        default_list = [
            OmniBatteryModule(enable_mock=self.enable_mock),
            PowerRenameModule(),
            AwakeModule(),
            WindowPinnerModule()
        ]
        for mod in default_list:
            self.register_module(mod)

    def register_module(self, module: ToyModule):
        saved_conf = self.config_manager.get_module_config(module.module_id)
        module.init_config(saved_conf)
        self.modules[module.module_id] = module

    def start_all(self):
        """Starts all enabled modules."""
        for mod in self.modules.values():
            if mod.is_enabled:
                try:
                    mod.start()
                except Exception as e:
                    print(f"[AppHost] Failed to start module '{mod.name}': {e}")

    def stop_all(self):
        """Gracefully stops all running modules."""
        for mod in self.modules.values():
            try:
                mod.stop()
            except Exception as e:
                print(f"[AppHost] Error stopping module '{mod.name}': {e}")

    def toggle_module(self, module_id: str, enabled: bool) -> bool:
        """Enables or disables a module at runtime."""
        mod = self.modules.get(module_id)
        if not mod:
            return False

        if mod.is_enabled == enabled:
            return True

        mod.is_enabled = enabled
        mod.config["enabled"] = enabled
        self.config_manager.set_module_config(module_id, mod.config)

        if enabled:
            mod.start()
        else:
            mod.stop()
        return True

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Provides an aggregated summary for the main Dashboard overview."""
        modules_info = []
        for mod in self.modules.values():
            modules_info.append({
                "id": mod.module_id,
                "name": mod.name,
                "description": mod.description,
                "icon": mod.icon,
                "enabled": mod.is_enabled,
                "state": mod.get_state()
            })
        return {
            "app_name": "OmniToys (全能工具箱)",
            "version": "1.0.0",
            "global_settings": self.config_manager.config.get("global", {}),
            "modules": modules_info
        }

    def dispatch_action(self, module_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Routes UI actions to the respective module."""
        mod = self.modules.get(module_id)
        if not mod:
            return {"status": "error", "message": f"Module {module_id} not found"}
        res = mod.handle_action(action, payload)
        self.config_manager.set_module_config(module_id, mod.config)
        return res

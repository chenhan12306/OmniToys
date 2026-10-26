"""
Base Module Interface for OmniToys (PowerToys-like extensible architecture).
Every utility/toy implements this interface to be managed by the AppHost.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class ToyModule(ABC):
    """Abstract base class for all pluggable toolbox modules."""

    def __init__(self, module_id: str, name: str, description: str, icon: str = "widgets"):
        self.module_id = module_id
        self.name = name
        self.description = description
        self.icon = icon  # Icon identifier (e.g. 'battery', 'coffee', 'pin')
        self.is_enabled: bool = True
        self.config: Dict[str, Any] = {}

    def init_config(self, saved_config: Optional[Dict[str, Any]] = None):
        """Initializes module configuration with saved user settings or defaults."""
        defaults = self.default_config()
        if saved_config:
            defaults.update(saved_config)
        self.config = defaults
        self.is_enabled = self.config.get("enabled", True)

    @abstractmethod
    def default_config(self) -> Dict[str, Any]:
        """Returns the default configuration dictionary for this module."""
        return {"enabled": True}

    @abstractmethod
    def start(self):
        """Invoked when module is enabled or host starts."""
        pass

    @abstractmethod
    def stop(self):
        """Invoked when module is disabled or host shuts down."""
        pass

    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """Returns current dynamic runtime state for UI rendering."""
        return {}

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handles actions sent from the frontend UI (e.g. toggle setting, click button)."""
        return {"status": "ok"}

"""
PowerToys-style Awake Module.
Keeps the computer and display awake on demand using SetThreadExecutionState.

The execution state is thread-affine in Win32, so it is applied by one
long-lived worker thread. Without that, toggling the module from a short-lived
HTTP request thread would lose the state as soon as the request finished.
"""

import sys
import ctypes
import threading
from typing import Dict, Any, Optional
from ..base_module import ToyModule
from ...core.safety_guard import register_shutdown_handler

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


class AwakeModule(ToyModule):
    def __init__(self):
        super().__init__(
            module_id="awake",
            name="保持清醒 (Awake)",
            description="阻止电脑进入睡眠休眠或关闭显示器。适合挂机下载、编译代码或长时渲染，无需修改系统电源计划。",
            icon="coffee",
        )
        self._active = False
        self._force = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self.is_windows = sys.platform.startswith("win")
        register_shutdown_handler(self.stop)

    def default_config(self) -> Dict[str, Any]:
        return {"enabled": False, "mode": "indefinite", "keep_screen_on": True}

    # ------------------------------------------------------------- lifecycle
    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._active = bool(self.config.get("enabled", False))
                self._force = True
                return

            self._active = bool(self.config.get("enabled", False))
            self._force = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker_loop, daemon=True, name="OmniToysAwakeThread"
            )
            self._thread.start()

    def stop(self):
        with self._lock:
            self._active = False
            self._force = True
            self._stop_event.set()
            thread = self._thread
            self._thread = None

        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)

        # Belt-and-braces for the case where the worker never ran.
        if self.is_windows:
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            except Exception:
                pass

    # ---------------------------------------------------------------- worker
    def _worker_loop(self):
        last_applied = None
        try:
            while not self._stop_event.is_set():
                with self._lock:
                    active = self._active
                    force = self._force
                    self._force = False

                if active != last_applied or force:
                    self._apply_execution_state(active)
                    last_applied = active

                self._stop_event.wait(0.2)
        finally:
            self._apply_execution_state(False)

    def _apply_execution_state(self, active: bool):
        if not self.is_windows:
            return
        try:
            kernel32 = ctypes.windll.kernel32
            if active:
                flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
                if self.config.get("keep_screen_on", True):
                    flags |= ES_DISPLAY_REQUIRED
                kernel32.SetThreadExecutionState(flags)
            else:
                kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception as e:
            print(f"[AwakeModule] Failed to set execution state: {e}")

    # -------------------------------------------------------------- UI state
    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "is_active": self._active,
                "mode": self.config.get("mode", "indefinite"),
                "keep_screen_on": self.config.get("keep_screen_on", True),
            }

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "toggle_active":
            with self._lock:
                new_state = not self._active
                self._active = new_state
                self._force = True
                self.config["enabled"] = new_state
            if new_state and (not self._thread or not self._thread.is_alive()):
                self.start()
            return {"status": "ok", "is_active": new_state}
        elif action == "update_settings":
            with self._lock:
                for k, v in payload.items():
                    if k in ("mode", "keep_screen_on"):
                        self.config[k] = v
                self._force = True
            return {"status": "ok", "config": self.config}
        return {"status": "unknown_action"}

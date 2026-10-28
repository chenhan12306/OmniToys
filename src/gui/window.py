"""
Modern Window Host & Embedded API Server.
Hosts the Fluent UI frontend with a lightweight local REST API.
Attempts to use pywebview (Windows native WebView2) or falls back to system browser.

Security: the API is bound to 127.0.0.1 and every mutating POST requires a
per-process random token that is injected into index.html. A cross-origin page
cannot read the token, and a custom header would force a CORS preflight, so
drive-by localhost CSRF is blocked.
"""

import os
import json
import hmac
import secrets
import socket
import threading
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from typing import Optional
from urllib.parse import urlsplit

from ..core.app_host import AppHost

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
TOKEN_PLACEHOLDER = "__OMNITOYS_TOKEN__"


class AppRequestHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args,
        host_ref: Optional[AppHost] = None,
        token: str = "",
        **kwargs,
    ):
        self.host_ref = host_ref
        self.token = token
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging
        pass

    # ------------------------------------------------------------------ helpers
    def _writable(self) -> bool:
        origin = self.headers.get("Origin")
        if origin and not (
            origin.startswith("http://127.0.0.1:")
            or origin.startswith("http://localhost:")
        ):
            return False
        supplied = self.headers.get("X-OmniToys-Token", "")
        return bool(self.token) and hmac.compare_digest(supplied, self.token)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_index(self):
        path = os.path.join(WEB_DIR, "index.html")
        try:
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
        except OSError as exc:
            self.send_error(500, f"Cannot read index.html: {exc}")
            return

        body = html.replace(TOKEN_PLACEHOLDER, self.token).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def list_directory(self, path):
        # Never expose a directory listing.
        self.send_error(404, "Not Found")
        return None

    # --------------------------------------------------------------------- GET
    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._serve_index()
            return

        if path == "/api/dashboard":
            summary = self.host_ref.get_dashboard_summary() if self.host_ref else {}
            self._send_json(summary)
            return

        # Static assets only (query string stripped).
        self.path = path
        super().do_GET()

    # -------------------------------------------------------------------- POST
    def do_POST(self):
        if not self._writable():
            self.send_error(403, "Forbidden")
            return

        length = int(self.headers.get("Content-Length", 0) or 0)
        body_bytes = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}

        if self.path == "/api/toggle_module":
            mod_id = body.get("module_id")
            enabled = bool(body.get("enabled", True))
            res = self.host_ref.toggle_module(mod_id, enabled) if self.host_ref else False
            self._send_json({"status": "ok" if res else "error"})
        elif self.path == "/api/action":
            mod_id = body.get("module_id")
            action = body.get("action")
            payload = body.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            res = (
                self.host_ref.dispatch_action(mod_id, action, payload)
                if self.host_ref
                else {}
            )
            self._send_json(res)
        elif self.path == "/api/global":
            key = body.get("key")
            value = body.get("value")
            res = (
                self.host_ref.set_global_setting(key, value)
                if self.host_ref
                else {"status": "error"}
            )
            self._send_json(res)
        else:
            self.send_error(404, "Not Found")


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class ModernWindowHost:
    def __init__(self, host: AppHost):
        self.host = host
        self.port = find_free_port()
        self.token = secrets.token_urlsafe(32)
        self.server: Optional[ThreadingHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.webview_window = None
        self.gui_started = False

    def start_server(self):
        if self.server:
            return

        def handler_factory(*args, **kwargs):
            return AppRequestHandler(
                *args, host_ref=self.host, token=self.token, **kwargs
            )

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), handler_factory)
        self.server.daemon_threads = True
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, daemon=True, name="OmniToysHttpThread"
        )
        self.server_thread.start()

    def stop_server(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None
        self.server_thread = None

    def show(self, use_browser: bool = False) -> bool:
        """Shows the dashboard. Returns True when a blocking native GUI ran."""
        self.start_server()
        url = f"http://127.0.0.1:{self.port}/index.html"

        if not use_browser:
            try:
                import webview
            except ImportError:
                webview = None

            if webview is not None:
                try:
                    self.webview_window = webview.create_window(
                        title="OmniToys - 外设与桌面效率工具箱",
                        url=url,
                        width=1040,
                        height=700,
                        min_size=(800, 600),
                        text_select=False,
                    )

                    def on_closing():
                        # Minimize to tray instead of quitting when configured.
                        if self.host.config_manager.get_global("close_to_tray", True):
                            try:
                                self.webview_window.hide()
                                return False
                            except Exception:
                                return True
                        return True

                    self.webview_window.events.closing += on_closing
                    self.gui_started = True
                    webview.start()
                    return True
                except Exception as exc:
                    print(f"[OmniToys] WebView start failed, using browser: {exc}")
                finally:
                    self.gui_started = False

        print(f"[OmniToys] Opening Dashboard at: {url}")
        webbrowser.open(url)
        return False

    def show_or_focus(self):
        """Restores or opens the dashboard on demand."""
        self.start_server()
        url = f"http://127.0.0.1:{self.port}/index.html"
        if self.webview_window:
            try:
                self.webview_window.show()
                self.webview_window.restore()
                return
            except Exception:
                pass
        webbrowser.open(url)

    def destroy(self):
        """Forces true window destruction upon full application exit."""
        if self.webview_window:
            try:
                self.webview_window.destroy()
            except Exception:
                pass
            self.webview_window = None

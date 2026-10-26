"""
Modern Window Host & Embedded API Server.
Hosts the Fluent UI frontend with a lightweight local REST API.
Attempts to use pywebview (Windows native WebView2) or falls back to system browser.
"""

import os
import json
import socket
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Optional
from ..core.app_host import AppHost

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")


class AppRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, host_ref: Optional[AppHost] = None, **kwargs):
        self.host_ref = host_ref
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging
        pass

    def do_GET(self):
        if self.path == "/api/dashboard":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            summary = self.host_ref.get_dashboard_summary() if self.host_ref else {}
            self.wfile.write(json.dumps(summary, ensure_ascii=False).encode("utf-8"))
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body = {}

        if self.path == "/api/toggle_module":
            mod_id = body.get("module_id")
            enabled = body.get("enabled", True)
            res = self.host_ref.toggle_module(mod_id, enabled) if self.host_ref else False
            self._send_json({"status": "ok" if res else "error"})
        elif self.path == "/api/action":
            mod_id = body.get("module_id")
            action = body.get("action")
            payload = body.get("payload", {})
            res = self.host_ref.dispatch_action(mod_id, action, payload) if self.host_ref else {}
            self._send_json(res)
        else:
            self.send_error(404, "Not Found")

    def _send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class ModernWindowHost:
    def __init__(self, host: AppHost):
        self.host = host
        self.port = find_free_port()
        self.server: Optional[HTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None

    def start_server(self):
        def handler_factory(*args, **kwargs):
            return AppRequestHandler(*args, host_ref=self.host, **kwargs)

        self.server = HTTPServer(("127.0.0.1", self.port), handler_factory)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def show(self, use_browser: bool = False):
        self.start_server()
        url = f"http://127.0.0.1:{self.port}/index.html"

        # Check for pywebview
        if not use_browser:
            try:
                import webview
                webview.create_window(
                    title="OmniToys - 外设与桌面效率工具箱",
                    url=url,
                    width=1040,
                    height=700,
                    min_size=(800, 600),
                    text_select=False
                )
                webview.start()
                return
            except ImportError:
                pass

        # Fallback to system browser
        print(f"[OmniToys] Opening Dashboard at: {url}")
        webbrowser.open(url)

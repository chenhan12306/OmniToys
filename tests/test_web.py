import json
import os
import re
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
import uuid

from src.core.app_host import AppHost
from src.gui.window import ModernWindowHost


class TestLocalApi(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = os.path.join(
            tempfile.gettempdir(), "omnitoys_web_" + uuid.uuid4().hex
        )
        os.makedirs(self.tmp_dir)
        self.host = AppHost(
            enable_mock=True, config_path=os.path.join(self.tmp_dir, "cfg.json")
        )
        self.window = ModernWindowHost(self.host)
        self.window.start_server()
        self.base = f"http://127.0.0.1:{self.window.port}"

    def tearDown(self):
        self.window.stop_server()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _post(self, path, payload, token=None):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("X-OmniToys-Token", token)
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.loads(res.read().decode("utf-8"))

    def test_index_injects_token_and_post_is_protected(self):
        with urllib.request.urlopen(self.base + "/", timeout=5) as res:
            html = res.read().decode("utf-8")
        self.assertNotIn("__OMNITOYS_TOKEN__", html)
        match = re.search(r'name="omni-token" content="([^"]+)"', html)
        self.assertIsNotNone(match)
        token = match.group(1)

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post(
                "/api/toggle_module",
                {"module_id": "power_rename", "enabled": False},
            )
        self.assertEqual(ctx.exception.code, 403)
        ctx.exception.close()

        status, body = self._post(
            "/api/toggle_module",
            {"module_id": "power_rename", "enabled": False},
            token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_global_setting_persists(self):
        with urllib.request.urlopen(self.base + "/", timeout=5) as res:
            token = re.search(
                r'name="omni-token" content="([^"]+)"', res.read().decode("utf-8")
            ).group(1)

        status, body = self._post(
            "/api/global",
            {"key": "close_to_tray", "value": False},
            token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertFalse(self.host.config_manager.get_global("close_to_tray"))


if __name__ == "__main__":
    unittest.main()

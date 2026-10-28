import os
import shutil
import tempfile
import unittest
import uuid

from src.core.device_base import BatteryInfo, ChargingStatus, DeviceCategory, ConnectionType
from src.core.device_manager import DeviceManager
from src.drivers.logitech_hidpp import estimate_percentage_from_voltage
from src.drivers.vendor_24g_driver import Vendor24GDriver
from src.core.win_raw_hid import WinRawHid
from src.modules.power_rename.module import PowerRenameModule
from src.core.app_host import AppHost


def make_temp_dir() -> str:
    """Creates a temp dir with inherited ACLs (mkdtemp's 0700 breaks restricted tokens)."""
    path = os.path.join(tempfile.gettempdir(), "omnitoys_test_" + uuid.uuid4().hex)
    os.makedirs(path)
    return path


class TestOmniBattery(unittest.TestCase):
    def test_voltage_estimation(self):
        self.assertEqual(estimate_percentage_from_voltage(4200), 100)
        self.assertTrue(70 <= estimate_percentage_from_voltage(3900) <= 80)
        self.assertTrue(10 <= estimate_percentage_from_voltage(3650) <= 20)
        self.assertEqual(estimate_percentage_from_voltage(3200), 0)

    def test_mock_device_manager(self):
        manager = DeviceManager(enable_mock=True)
        devices = manager.scan_all()
        self.assertGreaterEqual(len(devices), 3)

        primary = manager.get_primary_mouse()
        self.assertIsNotNone(primary)
        self.assertEqual(primary.category, DeviceCategory.MOUSE)
        self.assertTrue(primary.battery.is_valid)

    def test_custom_profiles_load(self):
        raw_hid = WinRawHid()
        driver = Vendor24GDriver(raw_hid)
        self.assertGreater(len(driver.device_profiles), 0)
        p0 = driver.device_profiles[0]
        self.assertIn("vid", p0)
        self.assertIn("pid", p0)
        self.assertIn("name", p0)

    def test_hid_open_missing_device_returns_none(self):
        raw_hid = WinRawHid()
        self.assertIsNone(raw_hid.open_device(r"\\?\hid#vid_0000&pid_0000"))

    def test_power_rename_logic(self):
        pr = PowerRenameModule()
        items = [
            {"full_path": "/tmp/IMG_001.JPG", "dir": "/tmp", "original_name": "IMG_001.JPG", "name_without_ext": "IMG_001", "ext": ".JPG"},
            {"full_path": "/tmp/IMG_002.JPG", "dir": "/tmp", "original_name": "IMG_002.JPG", "name_without_ext": "IMG_002", "ext": ".JPG"},
        ]
        rule = {
            "search_pattern": r"IMG_(\d+)",
            "replace_with": r"Vacation_\1",
            "use_regex": True,
            "apply_to": "name_only",
            "text_formatting": "none",
        }
        res = pr.compute_preview(items, rule)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["new_name"], "Vacation_001.JPG")
        self.assertEqual(res[1]["new_name"], "Vacation_002.JPG")
        self.assertTrue(res[0]["valid"])

    def test_power_rename_disk_and_undo(self):
        pr = PowerRenameModule()
        tmp_dir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmp_dir, True)
        try:
            f1 = os.path.join(tmp_dir, "test_file_a.txt")
            with open(f1, "w", encoding="utf-8") as f:
                f.write("hello")

            tasks = [{"full_path": f1, "dir": tmp_dir, "new_name": "renamed_file_a.txt"}]
            apply_res = pr.execute_rename(tasks)
            self.assertEqual(apply_res["status"], "ok")
            self.assertEqual(apply_res["success_count"], 1)
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "renamed_file_a.txt")))
            self.assertFalse(os.path.exists(f1))

            undo_res = pr.undo_last_rename()
            self.assertEqual(undo_res["status"], "ok")
            self.assertEqual(undo_res["reverted_count"], 1)
            self.assertTrue(os.path.exists(f1))
            self.assertFalse(os.path.exists(os.path.join(tmp_dir, "renamed_file_a.txt")))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_power_rename_case_only(self):
        pr = PowerRenameModule()
        tmp_dir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmp_dir, True)
        try:
            old = os.path.join(tmp_dir, "lower.txt")
            with open(old, "w", encoding="utf-8") as f:
                f.write("x")
            res = pr.execute_rename(
                [{"full_path": old, "dir": tmp_dir, "new_name": "Lower.txt"}]
            )
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["success_count"], 1)
            self.assertIn("Lower.txt", os.listdir(tmp_dir))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_power_rename_rejects_path_traversal(self):
        pr = PowerRenameModule()
        tmp_dir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmp_dir, True)
        try:
            old = os.path.join(tmp_dir, "safe.txt")
            with open(old, "w", encoding="utf-8") as f:
                f.write("x")
            res = pr.execute_rename(
                [{"full_path": old, "dir": tmp_dir, "new_name": r"..\evil.txt"}]
            )
            self.assertEqual(res["success_count"], 0)
            self.assertTrue(os.path.exists(old))
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(tmp_dir), "evil.txt")))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_power_rename_chain(self):
        pr = PowerRenameModule()
        tmp_dir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmp_dir, True)
        try:
            a = os.path.join(tmp_dir, "a.txt")
            b = os.path.join(tmp_dir, "b.txt")
            with open(a, "w", encoding="utf-8") as f:
                f.write("A")
            with open(b, "w", encoding="utf-8") as f:
                f.write("B")
            res = pr.execute_rename(
                [
                    {"full_path": a, "dir": tmp_dir, "new_name": "b.txt"},
                    {"full_path": b, "dir": tmp_dir, "new_name": "c.txt"},
                ]
            )
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["success_count"], 2)
            with open(os.path.join(tmp_dir, "b.txt"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "A")
            with open(os.path.join(tmp_dir, "c.txt"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "B")
            self.assertFalse(os.path.exists(a))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_config_defaults_are_isolated(self):
        from src.core.config_manager import ConfigManager, DEFAULT_CONFIG

        tmp_dir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmp_dir, True)
        try:
            c1 = ConfigManager(os.path.join(tmp_dir, "one.json"))
            c1.config["global"]["theme"] = "light"
            c1.save()

            c2 = ConfigManager(os.path.join(tmp_dir, "two.json"))
            self.assertEqual(c2.config["global"]["theme"], "dark")
            self.assertEqual(DEFAULT_CONFIG["global"]["theme"], "dark")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_app_host_integration(self):
        tmp_dir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmp_dir, True)
        try:
            host = AppHost(
                enable_mock=True, config_path=os.path.join(tmp_dir, "cfg.json")
            )
            summary = host.get_dashboard_summary()
            mod_ids = [m["id"] for m in summary["modules"]]
            self.assertIn("power_rename", mod_ids)
            self.assertIn("omni_battery", mod_ids)
            self.assertIn("window_pinner", mod_ids)
            self.assertNotIn("desktop_fences", mod_ids)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_safety_guard(self):
        from src.core.safety_guard import (
            register_shutdown_handler,
            execute_emergency_cleanup,
        )

        cleaned = []
        register_shutdown_handler(lambda: cleaned.append(True))
        execute_emergency_cleanup()
        self.assertTrue(len(cleaned) > 0)


if __name__ == "__main__":
    unittest.main()

import unittest
import os
import tempfile
import shutil
from src.core.device_base import BatteryInfo, ChargingStatus, DeviceCategory, ConnectionType
from src.core.device_manager import DeviceManager
from src.drivers.logitech_hidpp import estimate_percentage_from_voltage
from src.drivers.vendor_24g_driver import Vendor24GDriver
from src.core.win_raw_hid import WinRawHid
from src.modules.power_rename.module import PowerRenameModule
from src.core.app_host import AppHost


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

    def test_power_rename_logic(self):
        pr = PowerRenameModule()
        items = [
            {"full_path": "/tmp/IMG_001.JPG", "dir": "/tmp", "original_name": "IMG_001.JPG", "name_without_ext": "IMG_001", "ext": ".JPG"},
            {"full_path": "/tmp/IMG_002.JPG", "dir": "/tmp", "original_name": "IMG_002.JPG", "name_without_ext": "IMG_002", "ext": ".JPG"}
        ]
        # Regex replacement test
        rule = {
            "search_pattern": r"IMG_(\d+)",
            "replace_with": r"Vacation_\1",
            "use_regex": True,
            "apply_to": "name_only",
            "text_formatting": "none"
        }
        res = pr.compute_preview(items, rule)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["new_name"], "Vacation_001.JPG")
        self.assertEqual(res[1]["new_name"], "Vacation_002.JPG")

    def test_power_rename_disk_and_undo(self):
        pr = PowerRenameModule()
        tmp_dir = tempfile.mkdtemp()
        try:
            f1 = os.path.join(tmp_dir, "test_file_a.txt")
            with open(f1, "w") as f:
                f.write("hello")

            tasks = [{"full_path": f1, "dir": tmp_dir, "new_name": "renamed_file_a.txt"}]
            apply_res = pr.execute_rename(tasks)
            self.assertEqual(apply_res["status"], "ok")
            self.assertEqual(apply_res["success_count"], 1)
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "renamed_file_a.txt")))
            self.assertFalse(os.path.exists(f1))

            # Undo test
            undo_res = pr.undo_last_rename()
            self.assertEqual(undo_res["status"], "ok")
            self.assertEqual(undo_res["reverted_count"], 1)
            self.assertTrue(os.path.exists(f1))
            self.assertFalse(os.path.exists(os.path.join(tmp_dir, "renamed_file_a.txt")))
        finally:
            shutil.rmtree(tmp_dir)

    def test_app_host_integration(self):
        host = AppHost(enable_mock=True)
        summary = host.get_dashboard_summary()
        mod_ids = [m["id"] for m in summary["modules"]]
        self.assertIn("power_rename", mod_ids)
        self.assertIn("omni_battery", mod_ids)
        self.assertIn("desktop_fences", mod_ids)

    def test_desktop_fences_module(self):
        from src.modules.desktop_fences.module import DesktopFencesModule
        fences_mod = DesktopFencesModule()
        fences_mod.init_config()
        state = fences_mod.get_state()
        self.assertGreaterEqual(state["fences_count"], 2)

        # Test creating a new fence
        create_res = fences_mod.handle_action("create_fence", {"title": "游戏快捷方式", "folder_path": "/tmp/games"})
        self.assertEqual(create_res["status"], "ok")
        new_id = create_res["fence"]["id"]

        # Test deleting the fence
        del_res = fences_mod.handle_action("delete_fence", {"id": new_id})
        self.assertEqual(del_res["status"], "ok")


if __name__ == "__main__":
    unittest.main()

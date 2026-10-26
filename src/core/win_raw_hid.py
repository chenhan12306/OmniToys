"""
Windows Raw HID API wrapper using pure ctypes (Zero 3rd-party dependencies).
Enhanced for USB Hubs, Monitor Hubs, KVM Switches, and Docking Stations:
- Full sharing rights (FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE)
- Path-based VID/PID regex extraction fallback if query handle is blocked by hub
- 3-stage open fallback (Read/Write -> ReadOnly -> Zero Access)
- Dual transport: WriteFile with HidD_SetOutputReport fallback, ReadFile with HidD_GetInputReport fallback
"""

import sys
import re
import ctypes
from ctypes import wintypes
from typing import List, Optional, Tuple, Dict, Any

# Windows Constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
FILE_SHARE_ALL = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE

OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
    ]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


class HidDeviceInfo:
    def __init__(self, path: str, vid: int, pid: int, usage_page: int = 0, usage: int = 0,
                 input_len: int = 0, output_len: int = 0, feature_len: int = 0, product_name: str = ""):
        self.path = path
        self.vid = vid
        self.pid = pid
        self.usage_page = usage_page
        self.usage = usage
        self.input_len = input_len
        self.output_len = output_len
        self.feature_len = feature_len
        self.product_name = product_name

    def __repr__(self) -> str:
        return (f"<HidDeviceInfo VID=0x{self.vid:04X} PID=0x{self.pid:04X} "
                f"Page=0x{self.usage_page:04X} Usage=0x{self.usage:04X} Name='{self.product_name}'>")


class WinRawHid:
    """Provides pure-ctypes Windows HID access robust across direct ports and monitor hubs."""

    def __init__(self):
        self.is_windows = sys.platform.startswith("win")
        if self.is_windows:
            self._hid = ctypes.windll.hid
            self._setupapi = ctypes.windll.setupapi
            self._kernel32 = ctypes.windll.kernel32
        else:
            self._hid = None
            self._setupapi = None
            self._kernel32 = None

    def enumerate_devices(self, target_vid: Optional[int] = None, target_pid: Optional[int] = None) -> List[HidDeviceInfo]:
        """Enumerates connected HID devices filtered optionally by VID/PID, including hub-connected devices."""
        if not self.is_windows:
            return []

        hid_guid = GUID()
        self._hid.HidD_GetHidGuid(ctypes.byref(hid_guid))

        dev_info_set = self._setupapi.SetupDiGetClassDevsW(
            ctypes.byref(hid_guid),
            None,
            None,
            DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        )
        if dev_info_set == INVALID_HANDLE_VALUE:
            return []

        found_devices: List[HidDeviceInfo] = []
        try:
            device_interface_data = SP_DEVICE_INTERFACE_DATA()
            device_interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            member_index = 0

            while self._setupapi.SetupDiEnumDeviceInterfaces(
                dev_info_set,
                None,
                ctypes.byref(hid_guid),
                member_index,
                ctypes.byref(device_interface_data)
            ):
                member_index += 1
                required_size = wintypes.DWORD()

                self._setupapi.SetupDiGetDeviceInterfaceDetailW(
                    dev_info_set,
                    ctypes.byref(device_interface_data),
                    None,
                    0,
                    ctypes.byref(required_size),
                    None
                )

                if required_size.value == 0:
                    continue

                detail_buffer = ctypes.create_string_buffer(required_size.value)
                cb_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 5
                ctypes.memmove(detail_buffer, ctypes.byref(wintypes.DWORD(cb_size)), ctypes.sizeof(wintypes.DWORD))

                if self._setupapi.SetupDiGetDeviceInterfaceDetailW(
                    dev_info_set,
                    ctypes.byref(device_interface_data),
                    detail_buffer,
                    required_size.value,
                    None,
                    None
                ):
                    device_path = ctypes.wstring_at(ctypes.addressof(detail_buffer) + 4)
                    info = self._probe_device_path(device_path)
                    if info:
                        if target_vid is not None and info.vid != target_vid:
                            continue
                        if target_pid is not None and info.pid != target_pid:
                            continue
                        found_devices.append(info)

        finally:
            self._setupapi.SetupDiDestroyDeviceInfoList(dev_info_set)

        return found_devices

    def _probe_device_path(self, path: str) -> Optional[HidDeviceInfo]:
        """Probes a device path to get VID, PID, Caps, and Product String with hub fallbacks."""
        # Step 1: Attempt to open query handle with FULL sharing flags (critical for monitor hubs)
        handle = self._kernel32.CreateFileW(
            path,
            0,
            FILE_SHARE_ALL,
            None,
            OPEN_EXISTING,
            0,
            None
        )

        vid, pid = 0, 0
        product_name = ""
        usage_page, usage = 0, 0
        in_len, out_len, feat_len = 0, 0, 0

        if handle and handle != INVALID_HANDLE_VALUE:
            try:
                attrs = HIDD_ATTRIBUTES()
                attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
                if self._hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
                    vid = attrs.VendorID
                    pid = attrs.ProductID

                prod_buf = ctypes.create_unicode_buffer(128)
                if self._hid.HidD_GetProductString(handle, prod_buf, ctypes.sizeof(prod_buf)):
                    product_name = prod_buf.value

                preparsed = ctypes.c_void_p()
                if self._hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
                    try:
                        caps = HIDP_CAPS()
                        if self._hid.HidP_GetCaps(preparsed, ctypes.byref(caps)):
                            usage_page = caps.UsagePage
                            usage = caps.Usage
                            in_len = caps.InputReportByteLength
                            out_len = caps.OutputReportByteLength
                            feat_len = caps.FeatureReportByteLength
                    finally:
                        self._hid.HidD_FreePreparsedData(preparsed)
            finally:
                self._kernel32.CloseHandle(handle)
        else:
            # Step 2: Fallback - Extract VID & PID directly from device path string!
            # Example path: \\?\hid#vid_046d&pid_c547&mi_02#...
            vid_match = re.search(r"vid_([0-9a-fA-F]{4})", path, re.IGNORECASE)
            pid_match = re.search(r"pid_([0-9a-fA-F]{4})", path, re.IGNORECASE)
            if vid_match and pid_match:
                vid = int(vid_match.group(1), 16)
                pid = int(pid_match.group(1), 16)
                product_name = f"USB Hub Device (0x{vid:04X}:0x{pid:04X})"

        if vid == 0 and pid == 0:
            return None

        return HidDeviceInfo(
            path=path,
            vid=vid,
            pid=pid,
            usage_page=usage_page,
            usage=usage,
            input_len=in_len,
            output_len=out_len,
            feature_len=feat_len,
            product_name=product_name
        )

    def open_device(self, path: str) -> Optional[int]:
        """
        Opens a handle to a device with a 3-tier fallback designed for Monitor Hubs:
        Tier 1: GENERIC_READ | GENERIC_WRITE (Full R/W)
        Tier 2: GENERIC_READ (Read Only)
        Tier 3: 0 (Zero Desired Access - allows HidD_SetFeature/HidD_GetFeature even on locked endpoints)
        """
        if not self.is_windows:
            return None

        # Tier 1
        handle = self._kernel32.CreateFileW(
            path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_ALL,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None
        )
        if handle and handle != INVALID_HANDLE_VALUE:
            return handle

        # Tier 2
        handle = self._kernel32.CreateFileW(
            path,
            GENERIC_READ,
            FILE_SHARE_ALL,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None
        )
        if handle and handle != INVALID_HANDLE_VALUE:
            return handle

        # Tier 3 (Critical for monitor hubs & composite collections)
        handle = self._kernel32.CreateFileW(
            path,
            0,
            FILE_SHARE_ALL,
            None,
            OPEN_EXISTING,
            0,
            None
        )
        if handle and handle != INVALID_HANDLE_VALUE:
            return handle

        return None

    def close_device(self, handle: int):
        if handle and handle != INVALID_HANDLE_VALUE and self.is_windows:
            self._kernel32.CloseHandle(handle)

    def write_output_report(self, handle: int, data: bytes) -> bool:
        """
        Dual transport:
        1. WriteFile (standard Interrupt OUT endpoint)
        2. HidD_SetOutputReport (Control pipe fallback for hubs lacking interrupt out)
        """
        if not self.is_windows or not handle:
            return False

        written = wintypes.DWORD()
        buf = ctypes.create_string_buffer(data)

        # Attempt 1: Standard WriteFile
        success = self._kernel32.WriteFile(
            handle, buf, len(data), ctypes.byref(written), None
        )
        if success and written.value == len(data):
            return True

        # Attempt 2: HidD_SetOutputReport fallback
        try:
            if self._hid.HidD_SetOutputReport(handle, buf, len(data)):
                return True
        except Exception:
            pass

        return False

    def read_input_report(self, handle: int, length: int) -> Optional[bytes]:
        """
        Dual transport:
        1. ReadFile (standard Interrupt IN endpoint)
        2. HidD_GetInputReport (Control pipe fallback for hubs)
        """
        if not self.is_windows or not handle:
            return None

        buf = ctypes.create_string_buffer(length)
        bytes_read = wintypes.DWORD()

        # Attempt 1: Standard ReadFile
        success = self._kernel32.ReadFile(
            handle, buf, length, ctypes.byref(bytes_read), None
        )
        if success and bytes_read.value > 0:
            return bytes(buf[:bytes_read.value])

        # Attempt 2: HidD_GetInputReport fallback
        try:
            if self._hid.HidD_GetInputReport(handle, buf, length):
                return bytes(buf.raw)
        except Exception:
            pass

        return None

    def set_feature_report(self, handle: int, data: bytes) -> bool:
        """Sends a Feature Report via HidD_SetFeature."""
        if not self.is_windows or not handle:
            return False
        buf = ctypes.create_string_buffer(data)
        return bool(self._hid.HidD_SetFeature(handle, buf, len(data)))

    def get_feature_report(self, handle: int, report_id: int, length: int) -> Optional[bytes]:
        """Reads a Feature Report via HidD_GetFeature. Report ID must be first byte."""
        if not self.is_windows or not handle:
            return None
        buf = ctypes.create_string_buffer(length)
        buf[0] = report_id
        if self._hid.HidD_GetFeature(handle, buf, length):
            return bytes(buf.raw)
        return None

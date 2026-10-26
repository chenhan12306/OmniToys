"""
Windows Raw HID API wrapper using pure ctypes (Zero 3rd-party dependencies).
Wraps hid.dll, setupapi.dll, and kernel32.dll for device enumeration,
feature report reading/writing, and output/input report exchange.
"""

import sys
import ctypes
from ctypes import wintypes
from typing import List, Optional, Tuple, Dict, Any

# Windows Constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010


# Structures
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
    """Provides pure-ctypes Windows HID access."""

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
        """Enumerates connected HID devices filtered optionally by VID/PID."""
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

                # Allocate buffer for SP_DEVICE_INTERFACE_DETAIL_DATA_W
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
                    # Path starts at offset 4
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
        """Probes a device path to get VID, PID, Caps, and Product String."""
        # Non-exclusive open for probing metadata
        handle = self._kernel32.CreateFileW(
            path,
            0,  # Query access only
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None
        )
        if handle == INVALID_HANDLE_VALUE or handle is None:
            return None

        try:
            attrs = HIDD_ATTRIBUTES()
            attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
            if not self._hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
                return None

            vid = attrs.VendorID
            pid = attrs.ProductID

            # Read Product String
            prod_buf = ctypes.create_unicode_buffer(128)
            product_name = ""
            if self._hid.HidD_GetProductString(handle, prod_buf, ctypes.sizeof(prod_buf)):
                product_name = prod_buf.value

            # Read Capabilities
            usage_page, usage = 0, 0
            in_len, out_len, feat_len = 0, 0, 0
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
        finally:
            self._kernel32.CloseHandle(handle)

    def open_device(self, path: str) -> Optional[int]:
        """Opens a handle to a device with read/write access."""
        if not self.is_windows:
            return None

        handle = self._kernel32.CreateFileW(
            path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None
        )
        if handle == INVALID_HANDLE_VALUE or handle is None:
            # Fallback attempt: read-only access
            handle = self._kernel32.CreateFileW(
                path,
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                None
            )
            if handle == INVALID_HANDLE_VALUE or handle is None:
                return None
        return handle

    def close_device(self, handle: int):
        if handle and handle != INVALID_HANDLE_VALUE and self.is_windows:
            self._kernel32.CloseHandle(handle)

    def write_output_report(self, handle: int, data: bytes) -> bool:
        """Sends an Output Report via WriteFile."""
        if not self.is_windows or not handle:
            return False
        written = wintypes.DWORD()
        buf = ctypes.create_string_buffer(data)
        success = self._kernel32.WriteFile(
            handle,
            buf,
            len(data),
            ctypes.byref(written),
            None
        )
        return bool(success and written.value == len(data))

    def read_input_report(self, handle: int, length: int) -> Optional[bytes]:
        """Reads an Input Report via ReadFile."""
        if not self.is_windows or not handle:
            return None
        buf = ctypes.create_string_buffer(length)
        bytes_read = wintypes.DWORD()
        success = self._kernel32.ReadFile(
            handle,
            buf,
            length,
            ctypes.byref(bytes_read),
            None
        )
        if success and bytes_read.value > 0:
            return bytes(buf[:bytes_read.value])
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

"""
Windows Raw HID API wrapper using pure ctypes (Zero 3rd-party dependencies).
Enhanced for USB Hubs, Monitor Hubs, KVM Switches, and Docking Stations:
- Full sharing rights (FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE)
- Path-based VID/PID regex extraction fallback if the query handle is blocked
- 3-stage open fallback (Read/Write -> ReadOnly -> Zero Access)
- Overlapped reads/writes with real timeouts, so a silent device can never hang the UI
- Dual output transport: WriteFile with HidD_SetOutputReport fallback
"""

import sys
import re
import ctypes
from ctypes import wintypes
from typing import List, Optional

# Windows Constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
FILE_SHARE_ALL = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE

OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010

WAIT_OBJECT_0 = 0
ERROR_IO_PENDING = 997


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


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


class HidDeviceInfo:
    def __init__(
        self,
        path: str,
        vid: int,
        pid: int,
        usage_page: int = 0,
        usage: int = 0,
        input_len: int = 0,
        output_len: int = 0,
        feature_len: int = 0,
        product_name: str = "",
    ):
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
        return (
            f"<HidDeviceInfo VID=0x{self.vid:04X} PID=0x{self.pid:04X} "
            f"Page=0x{self.usage_page:04X} Usage=0x{self.usage:04X} "
            f"Name='{self.product_name}'>"
        )


class WinRawHid:
    """Pure-ctypes Windows HID access robust across ports, hubs and KVMs."""

    def __init__(self):
        self.is_windows = sys.platform.startswith("win")
        self._hid = None
        self._setupapi = None
        self._kernel32 = None
        if self.is_windows:
            self._hid = ctypes.WinDLL("hid")
            self._setupapi = ctypes.WinDLL("setupapi")
            self._kernel32 = ctypes.WinDLL("kernel32")
            self._configure_functions()

    # ------------------------------------------------------------------ Win32
    def _configure_functions(self):
        k = self._kernel32
        k.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        k.CreateFileW.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.ReadFile.argtypes = [
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(OVERLAPPED),
        ]
        k.ReadFile.restype = wintypes.BOOL
        k.WriteFile.argtypes = [
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(OVERLAPPED),
        ]
        k.WriteFile.restype = wintypes.BOOL
        k.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        k.CreateEventW.restype = wintypes.HANDLE
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.GetOverlappedResult.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(OVERLAPPED),
            ctypes.POINTER(wintypes.DWORD),
            wintypes.BOOL,
        ]
        k.GetOverlappedResult.restype = wintypes.BOOL
        k.GetLastError.restype = wintypes.DWORD
        if hasattr(k, "CancelIoEx"):
            k.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)]
            k.CancelIoEx.restype = wintypes.BOOL

        s = self._setupapi
        s.SetupDiGetClassDevsW.argtypes = [
            ctypes.POINTER(GUID),
            wintypes.LPCWSTR,
            wintypes.HWND,
            wintypes.DWORD,
        ]
        s.SetupDiGetClassDevsW.restype = wintypes.HANDLE
        s.SetupDiEnumDeviceInterfaces.argtypes = [
            wintypes.HANDLE,
            wintypes.LPVOID,
            ctypes.POINTER(GUID),
            wintypes.DWORD,
            ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
        ]
        s.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
        s.SetupDiGetDeviceInterfaceDetailW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        s.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
        s.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
        s.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

        h = self._hid
        h.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
        h.HidD_GetHidGuid.restype = None
        h.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
        h.HidD_GetAttributes.restype = wintypes.BOOL
        h.HidD_GetProductString.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
        h.HidD_GetProductString.restype = wintypes.BOOL
        h.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
        h.HidD_GetPreparsedData.restype = wintypes.BOOL
        h.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
        h.HidP_GetCaps.restype = wintypes.BOOL
        h.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
        h.HidD_FreePreparsedData.restype = wintypes.BOOL
        h.HidD_SetOutputReport.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
        h.HidD_SetOutputReport.restype = wintypes.BOOL
        h.HidD_SetFeature.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
        h.HidD_SetFeature.restype = wintypes.BOOL
        h.HidD_GetFeature.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.ULONG]
        h.HidD_GetFeature.restype = wintypes.BOOL

    def _handle_ok(self, handle) -> bool:
        return bool(handle) and handle != INVALID_HANDLE_VALUE

    # -------------------------------------------------------------- Enumeration
    def enumerate_devices(
        self, target_vid: Optional[int] = None, target_pid: Optional[int] = None
    ) -> List[HidDeviceInfo]:
        """Enumerates HID devices, optionally filtered by VID/PID."""
        if not self.is_windows:
            return []

        hid_guid = GUID()
        self._hid.HidD_GetHidGuid(ctypes.byref(hid_guid))

        dev_info_set = self._setupapi.SetupDiGetClassDevsW(
            ctypes.byref(hid_guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        )
        if not self._handle_ok(dev_info_set):
            return []

        found: List[HidDeviceInfo] = []
        try:
            interface_data = SP_DEVICE_INTERFACE_DATA()
            interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            index = 0

            while self._setupapi.SetupDiEnumDeviceInterfaces(
                dev_info_set, None, ctypes.byref(hid_guid), index, ctypes.byref(interface_data)
            ):
                index += 1
                required = wintypes.DWORD()
                self._setupapi.SetupDiGetDeviceInterfaceDetailW(
                    dev_info_set, ctypes.byref(interface_data), None, 0, ctypes.byref(required), None
                )
                if required.value == 0:
                    continue

                detail = ctypes.create_string_buffer(required.value)
                # cbSize is sizeof(DWORD) + sizeof(WCHAR) padded to pointer size.
                cb_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
                ctypes.memmove(
                    detail, ctypes.byref(wintypes.DWORD(cb_size)), ctypes.sizeof(wintypes.DWORD)
                )

                if self._setupapi.SetupDiGetDeviceInterfaceDetailW(
                    dev_info_set,
                    ctypes.byref(interface_data),
                    detail,
                    required.value,
                    None,
                    None,
                ):
                    # DevicePath always starts right after the DWORD cbSize.
                    path = ctypes.wstring_at(ctypes.addressof(detail) + 4)
                    info = self._probe_device_path(path)
                    if not info:
                        continue
                    if target_vid is not None and info.vid != target_vid:
                        continue
                    if target_pid is not None and info.pid != target_pid:
                        continue
                    found.append(info)
        finally:
            self._setupapi.SetupDiDestroyDeviceInfoList(dev_info_set)

        return found

    def _probe_device_path(self, path: str) -> Optional[HidDeviceInfo]:
        """Reads VID/PID/Caps; falls back to parsing the device path if opening fails."""
        handle = self._kernel32.CreateFileW(
            path, 0, FILE_SHARE_ALL, None, OPEN_EXISTING, 0, None
        )

        vid = pid = 0
        product_name = ""
        usage_page = usage = 0
        in_len = out_len = feat_len = 0

        if self._handle_ok(handle):
            try:
                attrs = HIDD_ATTRIBUTES()
                attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
                if self._hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
                    vid, pid = attrs.VendorID, attrs.ProductID

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

        # Path fallback is also used when a zero-access handle opens but cannot be queried.
        if not vid or not pid:
            vid_match = re.search(r"vid_([0-9a-fA-F]{4})", path, re.IGNORECASE)
            pid_match = re.search(r"pid_([0-9a-fA-F]{4})", path, re.IGNORECASE)
            if vid_match and pid_match:
                vid = int(vid_match.group(1), 16)
                pid = int(pid_match.group(1), 16)
                if not product_name:
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
            product_name=product_name,
        )

    # -------------------------------------------------------------------- Open
    def open_device(self, path: str) -> Optional[int]:
        """
        Opens a HID handle with a 3-tier fallback designed for Monitor Hubs:
        Tier 1: GENERIC_READ | GENERIC_WRITE
        Tier 2: GENERIC_READ
        Tier 3: 0 desired access (still allows HidD_SetFeature / HidD_GetFeature)

        FILE_FLAG_OVERLAPPED is required for the timeout-aware ReadFile/WriteFile.
        """
        if not self.is_windows:
            return None

        flags = FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OVERLAPPED
        for access in (GENERIC_READ | GENERIC_WRITE, GENERIC_READ, 0):
            handle = self._kernel32.CreateFileW(
                path, access, FILE_SHARE_ALL, None, OPEN_EXISTING, flags, None
            )
            if self._handle_ok(handle):
                return handle
        return None

    def close_device(self, handle):
        if self.is_windows and self._handle_ok(handle):
            self._kernel32.CloseHandle(handle)

    # --------------------------------------------------------- Timed transfers
    def _overlapped_io(self, handle, buffer, length: int, write: bool, timeout_ms: int) -> int:
        """
        Performs one overlapped read/write.
        Returns bytes transferred on success, -1 on timeout, -2 on immediate error.
        """
        event = self._kernel32.CreateEventW(None, True, False, None)
        if not self._handle_ok(event):
            return -2

        ov = OVERLAPPED()
        ov.hEvent = event
        transferred = wintypes.DWORD(0)

        func = self._kernel32.WriteFile if write else self._kernel32.ReadFile
        ok = func(handle, buffer, length, ctypes.byref(transferred), ctypes.byref(ov))
        if not ok:
            err = self._kernel32.GetLastError()
            if err != ERROR_IO_PENDING:
                self._kernel32.CloseHandle(event)
                return -2

            wait = self._kernel32.WaitForSingleObject(event, timeout_ms)
            if wait != WAIT_OBJECT_0:
                if hasattr(self._kernel32, "CancelIoEx"):
                    self._kernel32.CancelIoEx(handle, ctypes.byref(ov))
                    self._kernel32.WaitForSingleObject(event, 200)
                self._kernel32.CloseHandle(event)
                return -1

            if not self._kernel32.GetOverlappedResult(
                handle, ctypes.byref(ov), ctypes.byref(transferred), False
            ):
                self._kernel32.CloseHandle(event)
                return -2

        self._kernel32.CloseHandle(event)
        return int(transferred.value)

    def write_output_report(self, handle, data: bytes, timeout_ms: int = 80) -> bool:
        """
        Dual transport:
        1. Overlapped WriteFile (interrupt OUT)
        2. HidD_SetOutputReport (control pipe fallback for hubs without interrupt OUT)
        """
        if not self.is_windows or not self._handle_ok(handle) or not data:
            return False

        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        result = self._overlapped_io(handle, buf, len(data), True, timeout_ms)
        if result == len(data):
            return True
        if result == -2:
            try:
                return bool(self._hid.HidD_SetOutputReport(handle, buf, len(data)))
            except Exception:
                return False
        return False

    def read_input_report(self, handle, length: int, timeout_ms: int = 60) -> Optional[bytes]:
        """Reads one input report, bounded by timeout_ms. Never blocks indefinitely."""
        if not self.is_windows or not self._handle_ok(handle) or length <= 0:
            return None

        buf = ctypes.create_string_buffer(length)
        result = self._overlapped_io(handle, buf, length, False, timeout_ms)
        if result > 0:
            return bytes(buf.raw[:result])
        return None

    # ----------------------------------------------------------- Feature reports
    def set_feature_report(self, handle, data: bytes) -> bool:
        """Sends a Feature Report via HidD_SetFeature."""
        if not self.is_windows or not self._handle_ok(handle) or not data:
            return False
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        return bool(self._hid.HidD_SetFeature(handle, buf, len(data)))

    def get_feature_report(self, handle, report_id: int, length: int) -> Optional[bytes]:
        """Reads a Feature Report via HidD_GetFeature. Report ID must be the first byte."""
        if not self.is_windows or not self._handle_ok(handle) or length <= 0:
            return None
        buf = ctypes.create_string_buffer(length)
        buf[0] = report_id & 0xFF
        if self._hid.HidD_GetFeature(handle, buf, length):
            return bytes(buf.raw[:length])
        return None

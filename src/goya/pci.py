"""Windows PCIe BAR access for Habana Goya.

Two strategies for BAR access on Windows:
1. SetupAPI + generic resource driver (no kernel driver needed)
2. Custom UMDF2/KMDF driver that exposes BARs to userspace

This module implements strategy 1 using Windows SetupAPI to locate the device
and attempts to memory-map BARs via the generic PCI resource mechanism.

For production, we'll need a minimal kernel driver (KMDF) that:
- Claims the PCI device
- Maps BARs to userspace via MmMapIoSpace
- Exposes IOCTL for read32/write32

For now, this provides device enumeration and a BAR access abstraction.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import regs

if sys.platform != "win32":
    raise ImportError("goya.pci requires Windows")


# ---------------------------------------------------------------------------
# Windows API bindings (minimal subset)
# ---------------------------------------------------------------------------

_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
_cfgmgr32 = ctypes.WinDLL("cfgmgr32", use_last_error=True)

DIGCF_PRESENT = 0x02
DIGCF_ALLCLASSES = 0x04
INVALID_HANDLE = -1

CR_SUCCESS = 0


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("ClassGuid", wt.BYTE * 16),
        ("DevInst", wt.DWORD),
        ("Reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]


def _setup_di_get_class_devs(flags: int):
    """Get device info set for all present devices."""
    func = _setupapi.SetupDiGetClassDevsW
    func.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, wt.HWND, wt.DWORD]
    func.restype = wt.HANDLE
    handle = func(None, None, None, flags)
    if handle == INVALID_HANDLE:
        raise OSError(f"SetupDiGetClassDevsW failed: {ctypes.get_last_error()}")
    return handle


def _setup_di_enum_device_info(dev_info_set, index: int, dev_info: SP_DEVINFO_DATA) -> bool:
    func = _setupapi.SetupDiEnumDeviceInfo
    func.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
    func.restype = wt.BOOL
    return bool(func(dev_info_set, index, ctypes.byref(dev_info)))


def _setup_di_get_device_instance_id(dev_info_set, dev_info: SP_DEVINFO_DATA) -> str:
    func = _setupapi.SetupDiGetDeviceInstanceIdW
    func.argtypes = [
        wt.HANDLE, ctypes.POINTER(SP_DEVINFO_DATA),
        ctypes.c_wchar_p, wt.DWORD, ctypes.POINTER(wt.DWORD),
    ]
    func.restype = wt.BOOL
    buf = ctypes.create_unicode_buffer(512)
    required = wt.DWORD(0)
    ok = func(dev_info_set, ctypes.byref(dev_info), buf, 512, ctypes.byref(required))
    if not ok:
        return ""
    return buf.value


def _setup_di_destroy(dev_info_set) -> None:
    func = _setupapi.SetupDiDestroyDeviceInfoList
    func.argtypes = [wt.HANDLE]
    func.restype = wt.BOOL
    func(dev_info_set)


# ---------------------------------------------------------------------------
# CM_Get_DevNode_Registry_Property for reading hardware resources
# ---------------------------------------------------------------------------

CM_DRP_BUSNUMBER = 0x00000015


def _cm_get_devnode_property_string(dev_inst: int, prop_key: int) -> Optional[str]:
    """Read a string property from a device node."""
    buf = ctypes.create_unicode_buffer(1024)
    buf_size = wt.ULONG(ctypes.sizeof(buf))
    prop_type = wt.ULONG(0)
    func = _cfgmgr32.CM_Get_DevNode_PropertyW
    # This is a simplification — real impl needs property key GUID
    return None  # Placeholder for future KMDF driver


# ---------------------------------------------------------------------------
# Device discovery
# ---------------------------------------------------------------------------

@dataclass
class GoyaPCIDevice:
    """Represents a discovered Goya device on the PCI bus."""
    instance_id: str
    dev_inst: int
    location: str  # e.g., "PCI bus 3, device 0, function 0"

    def __str__(self) -> str:
        return f"Goya HL-1000 [{self.instance_id}] at {self.location}"


def find_goya_devices() -> list[GoyaPCIDevice]:
    """Enumerate PCI bus and find all Habana Goya devices."""
    devices: list[GoyaPCIDevice] = []
    ven_dev = f"VEN_{regs.PCIE_VENDOR_ID:04X}&DEV_{regs.PCIE_DEVICE_ID:04X}"

    dev_info_set = _setup_di_get_class_devs(DIGCF_PRESENT | DIGCF_ALLCLASSES)
    try:
        dev_info = SP_DEVINFO_DATA()
        dev_info.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
        index = 0
        while _setup_di_enum_device_info(dev_info_set, index, dev_info):
            instance_id = _setup_di_get_device_instance_id(dev_info_set, dev_info)
            if ven_dev.upper() in instance_id.upper():
                # Parse location from instance ID
                # Typical: PCI\VEN_1DA3&DEV_0001&SUBSYS_...&REV_01\3&...
                location = _parse_pci_location(instance_id)
                devices.append(GoyaPCIDevice(
                    instance_id=instance_id,
                    dev_inst=dev_info.DevInst,
                    location=location,
                ))
            index += 1
    finally:
        _setup_di_destroy(dev_info_set)

    return devices


def _parse_pci_location(instance_id: str) -> str:
    """Extract PCI bus/device/function from instance ID if possible."""
    # Instance IDs have varied formats; return the raw suffix for now
    parts = instance_id.split("\\")
    if len(parts) >= 3:
        return parts[-1]
    return "unknown"


# ---------------------------------------------------------------------------
# BAR access abstraction
# ---------------------------------------------------------------------------

class BARAccessor:
    """Abstract interface for reading/writing 32-bit registers via PCIe BAR.

    Concrete implementations:
    - KMDFBARAccessor: Uses a custom KMDF driver (production)
    - SimBARAccessor: In-memory simulation (testing)
    """

    def read32(self, offset: int) -> int:
        raise NotImplementedError

    def write32(self, offset: int, value: int) -> None:
        raise NotImplementedError

    def read64(self, offset: int) -> int:
        lo = self.read32(offset)
        hi = self.read32(offset + 4)
        return (hi << 32) | lo

    def write64(self, offset: int, value: int) -> None:
        self.write32(offset, value & 0xFFFFFFFF)
        self.write32(offset + 4, (value >> 32) & 0xFFFFFFFF)

    def close(self) -> None:
        pass

    def __enter__(self) -> "BARAccessor":
        return self

    def __exit__(self, *args) -> None:
        self.close()


class SimBARAccessor(BARAccessor):
    """Simulated BAR accessor for testing without hardware.

    Provides a 16 MB register space backed by a bytearray.
    Pre-loads device ID register with correct Goya vendor/device ID.
    """

    def __init__(self, size: int = 16 * 1024 * 1024) -> None:
        self._mem = bytearray(size)
        # Pre-load device ID
        vid_did = regs.PCIE_VENDOR_ID | (regs.PCIE_DEVICE_ID << 16)
        if regs.PCIE_DBI_DEVICE_ID_VENDOR_ID_REG < size:
            struct.pack_into("<I", self._mem, regs.PCIE_DBI_DEVICE_ID_VENDOR_ID_REG, vid_did)
        # Pre-load MME status as idle (all empty, SM idle)
        idle_status = (
            (1 << 7) |   # SB_A_EMPTY
            (1 << 8) |   # SB_B_EMPTY
            (1 << 9) |   # SB_CIN_EMPTY
            (1 << 10) |  # SB_COUT_EMPTY
            (1 << 11)    # SM_IDLE
        )
        if regs.MME_ARCH_STATUS < size:
            struct.pack_into("<I", self._mem, regs.MME_ARCH_STATUS, idle_status)

    def read32(self, offset: int) -> int:
        if offset + 4 > len(self._mem):
            return 0xFFFFFFFF
        return struct.unpack_from("<I", self._mem, offset)[0]

    def write32(self, offset: int, value: int) -> None:
        if offset + 4 <= len(self._mem):
            struct.pack_into("<I", self._mem, offset, value & 0xFFFFFFFF)


# ---------------------------------------------------------------------------
# Future: KMDF driver accessor
# ---------------------------------------------------------------------------

class KMDFBARAccessor(BARAccessor):
    """BAR access via a custom KMDF driver that exposes BARs to userspace.

    The driver will be a minimal KMDF driver that:
    1. Claims PCI device VEN_1DA3 DEV_0001
    2. Maps BAR0 via MmMapIoSpace
    3. Exposes IOCTL_READ32 / IOCTL_WRITE32

    This accessor opens the driver's device interface and issues IOCTLs.
    """

    DEVICE_INTERFACE = r"\\.\GoyaBAR"

    # IOCTL codes (will be defined in driver)
    IOCTL_READ32  = 0x80002000
    IOCTL_WRITE32 = 0x80002004

    def __init__(self) -> None:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        self._handle = kernel32.CreateFileW(
            self.DEVICE_INTERFACE,
            0xC0000000,  # GENERIC_READ | GENERIC_WRITE
            0, None,
            3,  # OPEN_EXISTING
            0, None,
        )
        if self._handle == INVALID_HANDLE:
            raise OSError(
                f"Cannot open Goya BAR driver at {self.DEVICE_INTERFACE}. "
                "Is the KMDF driver installed?"
            )

    def read32(self, offset: int) -> int:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        in_buf = struct.pack("<I", offset)
        out_buf = (ctypes.c_byte * 4)()
        bytes_returned = wt.DWORD(0)
        ok = kernel32.DeviceIoControl(
            self._handle, self.IOCTL_READ32,
            in_buf, len(in_buf),
            out_buf, 4,
            ctypes.byref(bytes_returned), None,
        )
        if not ok:
            raise OSError(f"Read32 at 0x{offset:X} failed")
        return struct.unpack("<I", bytes(out_buf))[0]

    def write32(self, offset: int, value: int) -> None:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        in_buf = struct.pack("<II", offset, value)
        bytes_returned = wt.DWORD(0)
        ok = kernel32.DeviceIoControl(
            self._handle, self.IOCTL_WRITE32,
            in_buf, len(in_buf),
            None, 0,
            ctypes.byref(bytes_returned), None,
        )
        if not ok:
            raise OSError(f"Write32 at 0x{offset:X} failed")

    def close(self) -> None:
        if self._handle and self._handle != INVALID_HANDLE:
            ctypes.windll.kernel32.CloseHandle(self._handle)  # type: ignore[attr-defined]
            self._handle = None

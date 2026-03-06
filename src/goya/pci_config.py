"""Read PCI configuration and resource information for Goya devices.

Uses Windows CfgMgr32 API to read device properties and allocated resources
without requiring a custom kernel driver. This gets us BAR physical addresses
and sizes even before we have goya_bar.sys.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import sys
from dataclasses import dataclass

if sys.platform != "win32":
    raise ImportError("goya.pci_config requires Windows")

_cfgmgr32 = ctypes.WinDLL("cfgmgr32", use_last_error=True)

CR_SUCCESS = 0
CR_NO_SUCH_VALUE = 0x00000025
CR_BUFFER_SMALL = 0x0000001A

# CM_Get_DevNode_Registry_Property property codes
CM_DRP_PHYSICAL_DEVICE_OBJECT_NAME = 0x0000000E
CM_DRP_BUSNUMBER = 0x00000015
CM_DRP_ADDRESS = 0x0000001D

# Resource types in CM_RESOURCE_LIST
CmResourceTypeMemory = 3
CmResourceTypeInterrupt = 2
CmResourceTypePort = 1

# Registry property for allocated resources
CM_DRP_CONFIGFLAGS = 0x0000000A


@dataclass
class PCIBar:
    """A PCI Base Address Register."""
    index: int
    physical_address: int
    length: int
    is_memory: bool  # True = memory, False = I/O

    def __str__(self) -> str:
        kind = "MEM" if self.is_memory else "IO"
        mb = self.length / (1024 * 1024)
        if mb >= 1:
            return f"BAR{self.index}: {kind} 0x{self.physical_address:012X} ({mb:.0f} MB)"
        kb = self.length / 1024
        return f"BAR{self.index}: {kind} 0x{self.physical_address:012X} ({kb:.0f} KB)"


@dataclass
class PCIDeviceInfo:
    """PCI device configuration information."""
    instance_id: str
    bus_number: int
    device_address: int  # (device << 16) | function
    location_path: str
    bars: list[PCIBar]
    interrupt_count: int

    @property
    def device_number(self) -> int:
        return (self.device_address >> 16) & 0xFF

    @property
    def function_number(self) -> int:
        return self.device_address & 0xFFFF

    def __str__(self) -> str:
        lines = [
            f"PCI {self.bus_number:02X}:{self.device_number:02X}.{self.function_number}",
            f"  Instance: {self.instance_id}",
            f"  Path: {self.location_path}",
        ]
        for bar in self.bars:
            lines.append(f"  {bar}")
        if self.interrupt_count:
            lines.append(f"  Interrupts: {self.interrupt_count}")
        return "\n".join(lines)


def _cm_locate_devnode(instance_id: str) -> int:
    """Locate a device node by instance ID."""
    dev_inst = wt.DWORD(0)
    func = _cfgmgr32.CM_Locate_DevNodeW
    func.argtypes = [ctypes.POINTER(wt.DWORD), ctypes.c_wchar_p, wt.ULONG]
    func.restype = wt.DWORD
    ret = func(ctypes.byref(dev_inst), instance_id, 0)
    if ret != CR_SUCCESS:
        raise OSError(f"CM_Locate_DevNode failed for {instance_id}: CR={ret}")
    return dev_inst.value


def _cm_get_devnode_registry_property(dev_inst: int, prop: int) -> bytes | None:
    """Read a registry property from a device node."""
    func = _cfgmgr32.CM_Get_DevNode_Registry_PropertyW
    func.argtypes = [
        wt.DWORD, wt.ULONG,
        ctypes.POINTER(wt.ULONG),
        ctypes.c_void_p, ctypes.POINTER(wt.ULONG),
        wt.ULONG,
    ]
    func.restype = wt.DWORD

    # First call to get required size
    prop_type = wt.ULONG(0)
    buf_size = wt.ULONG(0)
    ret = func(dev_inst, prop, ctypes.byref(prop_type), None, ctypes.byref(buf_size), 0)
    if ret == CR_NO_SUCH_VALUE:
        return None
    if ret != CR_BUFFER_SMALL and ret != CR_SUCCESS:
        return None

    if buf_size.value == 0:
        return None

    buf = (ctypes.c_byte * buf_size.value)()
    ret = func(dev_inst, prop, ctypes.byref(prop_type), buf, ctypes.byref(buf_size), 0)
    if ret != CR_SUCCESS:
        return None

    return bytes(buf[:buf_size.value])


def _read_bus_number(dev_inst: int) -> int:
    """Read PCI bus number."""
    data = _cm_get_devnode_registry_property(dev_inst, CM_DRP_BUSNUMBER)
    if data and len(data) >= 4:
        return struct.unpack("<I", data[:4])[0]
    return -1


def _read_address(dev_inst: int) -> int:
    """Read PCI device address (device << 16 | function)."""
    data = _cm_get_devnode_registry_property(dev_inst, CM_DRP_ADDRESS)
    if data and len(data) >= 4:
        return struct.unpack("<I", data[:4])[0]
    return 0


def _read_resources_from_registry(instance_id: str) -> tuple[list[PCIBar], int]:
    """Read allocated resources from the registry.

    Windows stores PCI resource assignments at:
    HKLM\\SYSTEM\\CurrentControlSet\\Enum\\<instance_id>\\LogConf
    """
    import winreg

    bars: list[PCIBar] = []
    interrupt_count = 0
    bar_index = 0

    # Try to read from the device's resource assignment in the registry
    try:
        # The resource lists are stored as binary data
        key_path = f"SYSTEM\\CurrentControlSet\\Enum\\{instance_id}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            # Try to read LogConf subkey for resource info
            try:
                with winreg.OpenKey(key, "LogConf") as logconf:
                    # BasicConfigVector contains the resource requirements
                    try:
                        data, reg_type = winreg.QueryValueEx(logconf, "BootConfig")
                        bars, interrupt_count = _parse_resource_list(data)
                    except FileNotFoundError:
                        pass
                    # Also try AllocConfig
                    if not bars:
                        try:
                            data, reg_type = winreg.QueryValueEx(logconf, "AllocConfig")
                            bars, interrupt_count = _parse_resource_list(data)
                        except FileNotFoundError:
                            pass
            except FileNotFoundError:
                pass
    except OSError:
        pass

    return bars, interrupt_count


def _parse_resource_list(data: bytes) -> tuple[list[PCIBar], int]:
    """Parse a CM_RESOURCE_LIST binary blob from the registry.

    CM_RESOURCE_LIST structure:
        ULONG Count;                    // Number of full resource descriptors
        CM_FULL_RESOURCE_DESCRIPTOR List[1]; // Array
    CM_FULL_RESOURCE_DESCRIPTOR:
        INTERFACE_TYPE InterfaceType;   // ULONG
        ULONG BusNumber;
        CM_PARTIAL_RESOURCE_LIST PartialResourceList;
    CM_PARTIAL_RESOURCE_LIST:
        USHORT Version;
        USHORT Revision;
        ULONG Count;
        CM_PARTIAL_RESOURCE_DESCRIPTOR PartialDescriptors[1];
    CM_PARTIAL_RESOURCE_DESCRIPTOR:
        UCHAR Type;
        UCHAR ShareDisposition;
        USHORT Flags;
        union { ... } u;  // 12 bytes (3 ULONGs or equivalent)
    """
    bars: list[PCIBar] = []
    interrupt_count = 0
    bar_index = 0

    if len(data) < 4:
        return bars, interrupt_count

    offset = 0
    list_count = struct.unpack_from("<I", data, offset)[0]
    offset += 4

    for _ in range(list_count):
        if offset + 12 > len(data):
            break

        # CM_FULL_RESOURCE_DESCRIPTOR header
        interface_type = struct.unpack_from("<I", data, offset)[0]
        bus_number = struct.unpack_from("<I", data, offset + 4)[0]
        offset += 8

        # CM_PARTIAL_RESOURCE_LIST header
        version = struct.unpack_from("<H", data, offset)[0]
        revision = struct.unpack_from("<H", data, offset + 2)[0]
        partial_count = struct.unpack_from("<I", data, offset + 4)[0]
        offset += 8

        for _ in range(partial_count):
            if offset + 16 > len(data):
                break

            res_type = data[offset]
            share_disp = data[offset + 1]
            flags = struct.unpack_from("<H", data, offset + 2)[0]
            # Union: 12 bytes starting at offset + 4
            union_data = data[offset + 4:offset + 16]
            offset += 16

            if res_type == CmResourceTypeMemory and len(union_data) >= 12:
                # Memory resource: Start (PHYSICAL_ADDRESS = u64), Length (ULONG)
                phys_addr = struct.unpack_from("<Q", union_data, 0)[0]
                length = struct.unpack_from("<I", union_data, 8)[0]
                if phys_addr > 0 and length > 0:
                    bars.append(PCIBar(
                        index=bar_index,
                        physical_address=phys_addr,
                        length=length,
                        is_memory=True,
                    ))
                    bar_index += 1

            elif res_type == CmResourceTypeInterrupt:
                interrupt_count += 1

    return bars, interrupt_count


def get_goya_pci_info(instance_id: str) -> PCIDeviceInfo:
    """Get full PCI configuration info for a Goya device."""
    dev_inst = _cm_locate_devnode(instance_id)
    bus = _read_bus_number(dev_inst)
    addr = _read_address(dev_inst)

    # Read location path from registry
    import winreg
    location_path = ""
    try:
        key_path = f"SYSTEM\\CurrentControlSet\\Enum\\{instance_id}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            try:
                val, _ = winreg.QueryValueEx(key, "LocationInformation")
                location_path = str(val)
            except FileNotFoundError:
                pass
    except OSError:
        pass

    bars, int_count = _read_resources_from_registry(instance_id)

    return PCIDeviceInfo(
        instance_id=instance_id,
        bus_number=bus,
        device_address=addr,
        location_path=location_path,
        bars=bars,
        interrupt_count=int_count,
    )

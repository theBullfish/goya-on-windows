"""Goya firmware loader — load and boot the on-chip ARM CPU.

The Goya SoC has an ARM Cortex-A53 CPU that runs its own embedded Linux.
The firmware handles DDR4 memory controller initialization, PLL config,
power management, and thermal monitoring.

Firmware loading sequence (from Linux goya_init_cpu):
1. Check if CPU is already running (status register)
2. Load boot FIT image to DRAM offset 0 via BAR4
3. Signal CPU that FIT image is ready (mailbox)
4. Poll CPU status until DRAM_RDY (up to 15s)

All operations go through BARAccessor — works with SimBARAccessor
for offline testing and KMDFBARAccessor on real hardware.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import regs
from .pci import BARAccessor


class FirmwareError(Exception):
    """Firmware loading or CPU boot failed."""


# ---------------------------------------------------------------------------
# CPU status helpers
# ---------------------------------------------------------------------------

@dataclass
class CPUStatus:
    """Snapshot of ARM CPU status registers."""
    boot_status: int
    boot_error: int
    cmd_status: int

    @property
    def status_name(self) -> str:
        names = {
            regs.CPU_BOOT_STATUS_NA: "NOT_AVAILABLE",
            regs.CPU_BOOT_STATUS_IN_WFE: "WAIT_FOR_EVENT",
            regs.CPU_BOOT_STATUS_DRAM_RDY: "DRAM_READY",
            regs.CPU_BOOT_STATUS_SRAM_AVAIL: "SRAM_AVAILABLE",
            regs.CPU_BOOT_STATUS_IN_BTL: "IN_BOOTLOADER",
            regs.CPU_BOOT_STATUS_IN_PREBOOT: "IN_PREBOOT",
            regs.CPU_BOOT_STATUS_IN_SPL: "IN_SPL",
            regs.CPU_BOOT_STATUS_IN_UBOOT: "IN_UBOOT",
            regs.CPU_BOOT_STATUS_IN_FW_INIT: "IN_FW_INIT",
            regs.CPU_BOOT_STATUS_READY_TO_BOOT: "READY_TO_BOOT",
            regs.CPU_BOOT_STATUS_WAITING_FOR_BOOT_FIT: "WAITING_FOR_FIT",
        }
        return names.get(self.boot_status, f"UNKNOWN({self.boot_status})")

    @property
    def is_ready(self) -> bool:
        return self.boot_status >= regs.CPU_BOOT_STATUS_DRAM_RDY

    @property
    def is_waiting_for_fit(self) -> bool:
        return self.boot_status == regs.CPU_BOOT_STATUS_WAITING_FOR_BOOT_FIT

    @property
    def is_in_preboot(self) -> bool:
        return self.boot_status in (
            regs.CPU_BOOT_STATUS_IN_WFE,
            regs.CPU_BOOT_STATUS_IN_PREBOOT,
        )

    @property
    def has_error(self) -> bool:
        return self.boot_error != 0


def read_cpu_status(bar: BARAccessor) -> CPUStatus:
    """Read current CPU status from mailbox registers."""
    return CPUStatus(
        boot_status=bar.read32(regs.CPU_BOOT_STATUS_REG),
        boot_error=bar.read32(regs.CPU_BOOT_ERR0_REG),
        cmd_status=bar.read32(regs.CPU_CMD_STATUS_REG),
    )


# ---------------------------------------------------------------------------
# Firmware image handling
# ---------------------------------------------------------------------------

@dataclass
class FirmwareImage:
    """A firmware image loaded from disk."""
    path: str
    data: bytes

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)


def load_firmware_file(path: str | Path) -> FirmwareImage:
    """Load a firmware image from disk.

    Args:
        path: Path to firmware file (.itb format)

    Returns:
        FirmwareImage with raw bytes

    Raises:
        FirmwareError: If file not found or too large
    """
    path = Path(path)
    if not path.exists():
        raise FirmwareError(f"Firmware file not found: {path}")

    data = path.read_bytes()
    if len(data) == 0:
        raise FirmwareError(f"Firmware file is empty: {path}")

    if len(data) > regs.CPU_FW_IMAGE_SIZE:
        raise FirmwareError(
            f"Firmware too large: {len(data)} bytes "
            f"(max {regs.CPU_FW_IMAGE_SIZE} = {regs.CPU_FW_IMAGE_SIZE // (1024*1024)} MB)"
        )

    return FirmwareImage(path=str(path), data=data)


# ---------------------------------------------------------------------------
# Firmware load to DRAM
# ---------------------------------------------------------------------------

def write_firmware_to_bar(
    bar: BARAccessor,
    fw: FirmwareImage,
    dram_offset: int = regs.FW_LOAD_DRAM_OFFSET,
    progress_callback: Optional[callable] = None,
) -> None:
    """Write firmware image to device DRAM via BAR.

    On real hardware this writes through BAR4 (DRAM-mapped).
    On SimBARAccessor this writes to the simulated register space.

    For real hardware, the BAR4 iATU must be configured to map to
    DRAM_PHYS_BASE before calling this function.

    Args:
        bar: BAR accessor (BAR4 for real hardware, BAR0 sim for testing)
        fw: Firmware image to write
        dram_offset: Offset in DRAM to write to (default: 0)
        progress_callback: Optional callback(bytes_written, total_bytes)
    """
    import struct as _struct

    total = fw.size
    written = 0

    # Write 4 bytes at a time
    for i in range(0, total, 4):
        chunk = fw.data[i:i + 4]
        if len(chunk) < 4:
            chunk = chunk + b"\x00" * (4 - len(chunk))
        val = _struct.unpack_from("<I", chunk, 0)[0]
        bar.write32(dram_offset + i, val)
        written += 4

        if progress_callback and written % (1024 * 1024) == 0:
            progress_callback(written, total)


# ---------------------------------------------------------------------------
# CPU boot sequence
# ---------------------------------------------------------------------------

def signal_fit_ready(bar: BARAccessor) -> None:
    """Signal the ARM CPU that the FIT image is loaded in DRAM.

    Writes KMD_MSG_FIT_RDY to the CPU command status register.
    """
    bar.write32(regs.CPU_CMD_STATUS_REG, regs.KMD_MSG_FIT_RDY)


def halt_cpu(bar: BARAccessor) -> None:
    """Send halt command to ARM CPU.

    Writes KMD_MSG_GOTO_WFE to command status register.
    """
    bar.write32(regs.CPU_CMD_STATUS_REG, regs.KMD_MSG_GOTO_WFE)


def poll_cpu_boot(
    bar: BARAccessor,
    target_status: int = regs.CPU_BOOT_STATUS_DRAM_RDY,
    timeout_sec: float = regs.CPU_BOOT_TIMEOUT_SEC,
    poll_interval_sec: float = 0.1,
) -> CPUStatus:
    """Poll CPU boot status until target status or timeout.

    Args:
        bar: BAR accessor
        target_status: Minimum boot status to wait for
        timeout_sec: Maximum wait time in seconds
        poll_interval_sec: Polling interval

    Returns:
        Final CPUStatus

    Raises:
        FirmwareError: On timeout or CPU error
    """
    deadline = time.monotonic() + timeout_sec

    while time.monotonic() < deadline:
        status = read_cpu_status(bar)

        if status.has_error:
            raise FirmwareError(
                f"CPU boot error: 0x{status.boot_error:08X} "
                f"(status={status.status_name})"
            )

        if status.boot_status >= target_status:
            return status

        time.sleep(poll_interval_sec)

    # Timeout — read final status
    final = read_cpu_status(bar)
    raise FirmwareError(
        f"CPU boot timeout after {timeout_sec}s "
        f"(status={final.status_name}, target={target_status})"
    )


# ---------------------------------------------------------------------------
# High-level firmware load orchestrator
# ---------------------------------------------------------------------------

def load_and_boot_firmware(
    bar: BARAccessor,
    fw_path: str | Path,
    timeout_sec: float = regs.CPU_BOOT_TIMEOUT_SEC,
    progress_callback: Optional[callable] = None,
) -> CPUStatus:
    """Complete firmware load and boot sequence.

    1. Check if CPU is already booted
    2. Load firmware file from disk
    3. Write firmware to DRAM via BAR
    4. Signal CPU that FIT image is ready
    5. Poll until DRAM_RDY

    Args:
        bar: BAR accessor (BAR4 for DRAM on real hardware)
        fw_path: Path to .itb firmware file
        timeout_sec: Boot timeout in seconds
        progress_callback: Optional progress callback

    Returns:
        CPUStatus after successful boot

    Raises:
        FirmwareError: On any failure
    """
    # Step 1: Check current status
    status = read_cpu_status(bar)
    if status.is_ready:
        return status

    # Step 2: Load firmware image from disk
    fw = load_firmware_file(fw_path)

    # Step 3: Write firmware to DRAM
    write_firmware_to_bar(bar, fw, progress_callback=progress_callback)

    # Step 4: Signal CPU
    signal_fit_ready(bar)

    # Step 5: Poll for boot completion
    return poll_cpu_boot(bar, timeout_sec=timeout_sec)


# ---------------------------------------------------------------------------
# Simulated firmware boot (for testing)
# ---------------------------------------------------------------------------

def sim_set_cpu_ready(bar: BARAccessor) -> None:
    """Set CPU status to DRAM_RDY in a SimBARAccessor.

    This simulates a successful firmware boot for testing purposes.
    Call this after init to make the sim behave as if firmware booted.
    """
    bar.write32(regs.CPU_BOOT_STATUS_REG, regs.CPU_BOOT_STATUS_DRAM_RDY)
    bar.write32(regs.CPU_BOOT_ERR0_REG, 0)

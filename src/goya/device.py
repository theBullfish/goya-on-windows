"""GoyaDevice — high-level orchestrator for Habana Goya operations.

Ties together BAR access, initialization, DMA transfers, and MME execution
into a single coherent interface. Works against SimBARAccessor for offline
testing and KMDFBARAccessor for real hardware.

Usage:
    from goya.device import GoyaDevice
    from goya.pci import SimBARAccessor

    bar = SimBARAccessor()
    dev = GoyaDevice(bar)
    dev.init()
    dev.dma_host_to_dram(channel=0, src=host_addr, dst=dram_addr, size=nbytes)
    dev.gemm(desc)
    dev.shutdown()
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import regs
from .init import (
    init_minimum,
    soft_reset_engines,
    verify_device_id,
)
from .packets import (
    GEMMDescriptor,
    dma_transfer_direct,
    mme_execute_and_wait,
    write_gemm_descriptor,
)
from .pci import BARAccessor


class GoyaError(Exception):
    """Base exception for Goya hardware operations."""


class GoyaInitError(GoyaError):
    """Initialization failed."""


class GoyaDMAError(GoyaError):
    """DMA transfer failed."""


class GoyaMMEError(GoyaError):
    """MME operation failed."""


@dataclass
class GoyaStatus:
    """Snapshot of device status registers."""
    hw_caps: int
    mme_idle: bool
    mme_status_raw: int
    dma_ch_busy: list[bool]  # per-channel busy flag

    @property
    def is_ready(self) -> bool:
        return (
            (self.hw_caps & regs.HW_CAP_DMA) != 0
            and (self.hw_caps & regs.HW_CAP_MME) != 0
            and self.mme_idle
        )


class GoyaDevice:
    """High-level interface to a Habana Goya accelerator.

    Lifecycle:
        dev = GoyaDevice(bar)
        dev.init()          # queue manager init, verify device
        dev.gemm(desc)      # run a matrix multiply
        dev.shutdown()      # clean reset
    """

    def __init__(self, bar: BARAccessor) -> None:
        self._bar = bar
        self._hw_caps: int = 0
        self._initialized = False

    @property
    def hw_caps(self) -> int:
        return self._hw_caps

    @property
    def initialized(self) -> bool:
        return self._initialized

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> int:
        """Initialize the device. Returns hardware capability bitmask.

        Raises GoyaInitError if device ID verification fails.
        """
        if not verify_device_id(self._bar):
            raise GoyaInitError(
                "Device ID verification failed — not a Goya HL-1000"
            )

        self._hw_caps = init_minimum(self._bar)
        if self._hw_caps == 0:
            raise GoyaInitError("Minimum init returned no capabilities")

        self._initialized = True
        return self._hw_caps

    def shutdown(self) -> None:
        """Soft-reset engines and mark device as uninitialized."""
        if self._initialized:
            soft_reset_engines(self._bar)
            self._hw_caps = 0
            self._initialized = False

    def status(self) -> GoyaStatus:
        """Read current device status registers."""
        mme_status = self._bar.read32(regs.MME_ARCH_STATUS)
        ch_busy = []
        for ch in range(5):
            sts = self._bar.read32(regs.dma_ch_base(ch) + regs.DMA_CH_STS0)
            ch_busy.append(bool(sts & 1))

        return GoyaStatus(
            hw_caps=self._hw_caps,
            mme_idle=regs.mme_is_idle(mme_status),
            mme_status_raw=mme_status,
            dma_ch_busy=ch_busy,
        )

    # ------------------------------------------------------------------
    # DMA
    # ------------------------------------------------------------------

    def dma_transfer(
        self,
        channel: int,
        src_addr: int,
        dst_addr: int,
        size: int,
        timeout_polls: int = 1000000,
    ) -> None:
        """Execute a direct-register DMA transfer.

        Raises GoyaDMAError on timeout.
        """
        self._require_init()
        ok = dma_transfer_direct(
            self._bar, channel, src_addr, dst_addr, size, timeout_polls
        )
        if not ok:
            raise GoyaDMAError(
                f"DMA transfer timed out on channel {channel} "
                f"(src=0x{src_addr:X} dst=0x{dst_addr:X} size={size})"
            )

    def write_to_dram(
        self,
        dram_offset: int,
        data: bytes,
        channel: int = 0,
    ) -> None:
        """Write data to simulated DRAM via BAR.

        For SimBARAccessor, this writes directly into the backing memory.
        For real hardware, this would DMA from a pinned host buffer.
        """
        self._require_init()
        for i in range(0, len(data), 4):
            chunk = data[i:i + 4]
            if len(chunk) < 4:
                chunk = chunk + b"\x00" * (4 - len(chunk))
            val = struct.unpack_from("<I", chunk, 0)[0]
            self._bar.write32(dram_offset + i, val)

    def read_from_dram(
        self,
        dram_offset: int,
        size: int,
    ) -> bytes:
        """Read data from simulated DRAM via BAR.

        For SimBARAccessor, reads directly from backing memory.
        """
        self._require_init()
        result = bytearray()
        for i in range(0, size, 4):
            val = self._bar.read32(dram_offset + i)
            result.extend(struct.pack("<I", val))
        return bytes(result[:size])

    # ------------------------------------------------------------------
    # MME / GEMM
    # ------------------------------------------------------------------

    def gemm(
        self,
        desc: GEMMDescriptor,
        timeout_polls: int = 1000000,
    ) -> None:
        """Execute a GEMM operation via direct register writes.

        Writes the descriptor to MME architecture registers, triggers
        execution, and polls for completion.

        Raises GoyaMMEError on timeout.
        """
        self._require_init()

        # Write descriptor
        write_gemm_descriptor(self._bar, desc)

        # Execute and wait
        ok = mme_execute_and_wait(self._bar, timeout_polls)
        if not ok:
            raise GoyaMMEError(
                f"MME GEMM timed out (M={desc.m} K={desc.k} N={desc.n})"
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_init(self) -> None:
        if not self._initialized:
            raise GoyaError("Device not initialized — call init() first")

    def __enter__(self) -> GoyaDevice:
        self.init()
        return self

    def __exit__(self, *args) -> None:
        self.shutdown()
        self._bar.close()

    def __repr__(self) -> str:
        state = "READY" if self._initialized else "UNINIT"
        caps = f"0x{self._hw_caps:03X}" if self._hw_caps else "none"
        return f"<GoyaDevice {state} caps={caps}>"

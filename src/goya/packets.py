"""Goya command buffer packet builder.

Builds hardware command packets for submission via queue managers.
Packets are 64-bit aligned, big-endian header + little-endian payload.

Also works for direct-register mode: the DMA and MME helpers below
can drive registers directly via BARAccessor without queues.

Packet format (from Linux driver goya_packets.h):
  Header [63:56] = opcode
  Header [55:52] = engine group (for WREG_32/BULK)
  Header [31:0]  = payload (varies by opcode)
  Body varies by opcode type.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Sequence

from . import regs


# ---------------------------------------------------------------------------
# Packet assembly
# ---------------------------------------------------------------------------

def _packet_header(opcode: int, **kwargs) -> int:
    """Build a 64-bit packet header word."""
    hdr = (opcode & 0xFF) << 56
    if "eng_group" in kwargs:
        hdr |= (kwargs["eng_group"] & 0xF) << 52
    if "reg_offset" in kwargs:
        # WREG_32: offset in lower 16 bits (>>2 from base)
        hdr |= kwargs["reg_offset"] & 0xFFFF
    if "msg" in kwargs:
        hdr |= kwargs["msg"] & 0xFFFFFFFF
    return hdr


def packet_wreg32(reg_offset: int, value: int) -> bytes:
    """WREG_32: Write a single 32-bit register.

    reg_offset: BAR0 offset (will be encoded as >>2 relative to base).
    value: 32-bit value to write.
    """
    hdr = _packet_header(regs.PACKET_WREG_32, reg_offset=(reg_offset >> 2))
    return struct.pack(">Q", hdr) + struct.pack("<I", value) + b"\x00" * 4


def packet_nop() -> bytes:
    """NOP: No operation, used for alignment or queue padding."""
    hdr = _packet_header(regs.PACKET_NOP)
    return struct.pack(">Q", hdr)


def packet_fence(dec_val: int = 1, gate_val: int = 1, fence_id: int = 0) -> bytes:
    """FENCE: Wait until sync object value >= gate_val.

    dec_val: Value to decrement from sync object after passing.
    gate_val: Minimum value to pass fence.
    fence_id: Fence index (0-3).
    """
    hdr = _packet_header(regs.PACKET_FENCE)
    payload = (
        (dec_val & 0xFF) |
        ((gate_val & 0xFF) << 8) |
        ((fence_id & 0x3) << 16)
    )
    return struct.pack(">Q", hdr) + struct.pack("<I", payload) + b"\x00" * 4


def packet_lin_dma(
    src_addr: int,
    dst_addr: int,
    tsize: int,
    direction: int = regs.DMA_HOST_TO_DRAM,
    dma_en: bool = True,
) -> bytes:
    """LIN_DMA: Linear DMA transfer packet.

    src_addr: 64-bit source address
    dst_addr: 64-bit destination address
    tsize: Transfer size in bytes
    direction: DMA direction (HOST_TO_DRAM, DRAM_TO_HOST, etc.)
    """
    ctl = (
        (int(dma_en) << 0) |
        ((direction & 0x7) << 1)
    )
    hdr = _packet_header(regs.PACKET_LIN_DMA, msg=ctl)
    body = struct.pack("<QQII",
        src_addr,    # 64-bit source
        dst_addr,    # 64-bit destination
        tsize,       # transfer size
        0,           # reserved
    )
    return struct.pack(">Q", hdr) + body


def packet_stop() -> bytes:
    """STOP: Halt the command processor."""
    hdr = _packet_header(regs.PACKET_STOP)
    return struct.pack(">Q", hdr)


# ---------------------------------------------------------------------------
# Command buffer
# ---------------------------------------------------------------------------

class CommandBuffer:
    """Accumulates packets into a contiguous command buffer."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def wreg32(self, reg_offset: int, value: int) -> "CommandBuffer":
        self._buf.extend(packet_wreg32(reg_offset, value))
        return self

    def nop(self) -> "CommandBuffer":
        self._buf.extend(packet_nop())
        return self

    def fence(self, dec_val: int = 1, gate_val: int = 1, fence_id: int = 0) -> "CommandBuffer":
        self._buf.extend(packet_fence(dec_val, gate_val, fence_id))
        return self

    def lin_dma(self, src: int, dst: int, size: int,
                direction: int = regs.DMA_HOST_TO_DRAM) -> "CommandBuffer":
        self._buf.extend(packet_lin_dma(src, dst, size, direction))
        return self

    def stop(self) -> "CommandBuffer":
        self._buf.extend(packet_stop())
        return self

    def build(self) -> bytes:
        return bytes(self._buf)

    def __len__(self) -> int:
        return len(self._buf)


# ---------------------------------------------------------------------------
# MME GEMM descriptor — direct register mode
# ---------------------------------------------------------------------------

@dataclass
class GEMMDescriptor:
    """Describes a matrix multiply operation for the MME.

    A [M x K] @ B [K x N] -> Cout [M x N]

    All addresses are DRAM physical addresses (offset from BAR0 or device-space).
    """
    a_addr: int          # 64-bit address of matrix A in DRAM
    b_addr: int          # 64-bit address of matrix B in DRAM
    cout_addr: int       # 64-bit address of output matrix in DRAM
    cin_addr: int = 0    # Optional accumulator input (for fused add)
    bias_addr: int = 0   # Optional bias vector address

    m: int = 0           # Rows of A / rows of Cout
    k: int = 0           # Cols of A / rows of B
    n: int = 0           # Cols of B / cols of Cout

    dtype: int = regs.MMEHeader.DT_FP32  # Data type for A and B
    out_dtype: int = regs.MMEHeader.DT_FP32  # Data type for Cout

    transpose_a: bool = False
    load_cin: bool = False
    load_bias: bool = False
    signal_en: bool = True
    relu: bool = False   # Hardware ReLU via GEMMLOWP_ZP bit 30

    def header_value(self) -> int:
        """Build the MME_ARCH_HEADER register value."""
        hdr = (
            regs.MMEHeader()
            .signal_mask(0x01)
            .signal_en(self.signal_en)
            .trans_a(self.transpose_a)
            .store_out()
            .load_cin(self.load_cin)
            .load_bias(self.load_bias)
            .ab_data_type(self.dtype)
            .cout_data_type(self.out_dtype)
        )
        return hdr.build()

    def gemmlowp_zp_value(self) -> int:
        """Build the GEMMLOWP_ZP register value. Bit 30 = ReLU enable."""
        val = 0
        if self.relu:
            val |= (1 << 30)
        return val

    def associated_dims_0(self) -> int:
        """Encode outer dimensions (M, N) into ASSOCIATED_DIMS_0.

        This is a simplified encoding — real hardware uses stride descriptors.
        Bits [15:0] = outer_size_0, bits [31:16] = outer_size_1
        """
        return (self.m & 0xFFFF) | ((self.n & 0xFFFF) << 16)

    def associated_dims_1(self) -> int:
        """Encode inner dimension (K) into ASSOCIATED_DIMS_1.

        Bits [15:0] = inner_size
        """
        return self.k & 0xFFFF

    def kernel_size(self) -> int:
        """KERNEL_SIZE_MINUS_1: 0 for standard GEMM (1x1 convolution)."""
        return 0


def write_gemm_descriptor(bar, desc: GEMMDescriptor) -> None:
    """Write a GEMM descriptor to MME architecture registers via BAR.

    This is the direct-register path (no queue submission).
    After writing, caller should issue MME_CMD=1 and poll for idle.
    """
    # Address registers (split 64-bit into high/low)
    bar.write32(regs.MME_ARCH_A_BASE_ADDR_HIGH, (desc.a_addr >> 32) & 0xFFFFFFFF)
    bar.write32(regs.MME_ARCH_A_BASE_ADDR_LOW, desc.a_addr & 0xFFFFFFFF)
    bar.write32(regs.MME_ARCH_B_BASE_ADDR_HIGH, (desc.b_addr >> 32) & 0xFFFFFFFF)
    bar.write32(regs.MME_ARCH_B_BASE_ADDR_LOW, desc.b_addr & 0xFFFFFFFF)
    bar.write32(regs.MME_ARCH_COUT_BASE_ADDR_HIGH, (desc.cout_addr >> 32) & 0xFFFFFFFF)
    bar.write32(regs.MME_ARCH_COUT_BASE_ADDR_LOW, desc.cout_addr & 0xFFFFFFFF)

    if desc.load_cin:
        bar.write32(regs.MME_ARCH_CIN_BASE_ADDR_HIGH, (desc.cin_addr >> 32) & 0xFFFFFFFF)
        bar.write32(regs.MME_ARCH_CIN_BASE_ADDR_LOW, desc.cin_addr & 0xFFFFFFFF)

    if desc.load_bias:
        bar.write32(regs.MME_ARCH_BIAS_BASE_ADDR_HIGH, (desc.bias_addr >> 32) & 0xFFFFFFFF)
        bar.write32(regs.MME_ARCH_BIAS_BASE_ADDR_LOW, desc.bias_addr & 0xFFFFFFFF)

    # Dimensions
    bar.write32(regs.MME_ARCH_KERNEL_SIZE_MINUS_1, desc.kernel_size())
    bar.write32(regs.MME_ARCH_ASSOCIATED_DIMS_0, desc.associated_dims_0())
    bar.write32(regs.MME_ARCH_ASSOCIATED_DIMS_1, desc.associated_dims_1())

    # Quantization / ReLU
    bar.write32(regs.MME_ARCH_GEMMLOWP_ZP, desc.gemmlowp_zp_value())

    # Header (must be written last — it triggers descriptor load)
    bar.write32(regs.MME_ARCH_HEADER, desc.header_value())


# ---------------------------------------------------------------------------
# Direct-register DMA transfer
# ---------------------------------------------------------------------------

def dma_transfer_direct(
    bar,
    channel: int,
    src_addr: int,
    dst_addr: int,
    size: int,
    timeout_polls: int = 1000000,
) -> bool:
    """Execute a DMA transfer using direct register writes (no queue).

    This uses the channel's local DMA registers, bypassing the queue manager.
    Returns True on success, False on timeout.
    """
    base = regs.dma_ch_base(channel)

    # Set source address
    bar.write32(base + regs.DMA_CH_LDMA_SRC_ADDR_LO, src_addr & 0xFFFFFFFF)
    bar.write32(base + regs.DMA_CH_LDMA_SRC_ADDR_HI, (src_addr >> 32) & 0xFFFFFFFF)

    # Set destination address
    bar.write32(base + regs.DMA_CH_LDMA_DST_ADDR_LO, dst_addr & 0xFFFFFFFF)
    bar.write32(base + regs.DMA_CH_LDMA_DST_ADDR_HI, (dst_addr >> 32) & 0xFFFFFFFF)

    # Set transfer size
    bar.write32(base + regs.DMA_CH_LDMA_TSIZE, size)

    # Commit transfer
    bar.write32(base + regs.DMA_CH_COMIT_TRANSFER, 1)

    # Poll for completion (STS0 bit 0 = busy)
    for _ in range(timeout_polls):
        sts = bar.read32(base + regs.DMA_CH_STS0)
        if (sts & 1) == 0:  # Not busy
            return True

    return False


# ---------------------------------------------------------------------------
# MME execute + poll (direct register mode)
# ---------------------------------------------------------------------------

def mme_execute_and_wait(bar, timeout_polls: int = 1000000) -> bool:
    """Trigger MME execution and wait for idle.

    Assumes descriptor is already written via write_gemm_descriptor().
    Returns True on success (idle), False on timeout.
    """
    # Write 1 to MME_CMD to start execution
    bar.write32(regs.MME_CMD, 1)

    # Poll status for idle
    for _ in range(timeout_polls):
        status = bar.read32(regs.MME_ARCH_STATUS)
        if regs.mme_is_idle(status):
            return True

    return False

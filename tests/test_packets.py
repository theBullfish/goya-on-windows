"""Tests for packet builder, GEMM descriptor, and DMA transfer logic.

All tests run against SimBARAccessor — no hardware required.
"""

import struct
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from goya import regs
from goya.pci import SimBARAccessor
from goya.packets import (
    packet_wreg32, packet_nop, packet_fence, packet_lin_dma, packet_stop,
    CommandBuffer, GEMMDescriptor, write_gemm_descriptor,
    dma_transfer_direct, mme_execute_and_wait,
)


# ---------------------------------------------------------------------------
# Packet encoding tests
# ---------------------------------------------------------------------------

class TestPacketEncoding:
    def test_wreg32_packet_size(self):
        pkt = packet_wreg32(0xD0200, 1)
        assert len(pkt) == 16  # 8-byte header + 4 value + 4 pad

    def test_wreg32_header_opcode(self):
        pkt = packet_wreg32(0xD0200, 0xDEAD)
        hdr = struct.unpack(">Q", pkt[:8])[0]
        opcode = (hdr >> 56) & 0xFF
        assert opcode == regs.PACKET_WREG_32

    def test_wreg32_encodes_offset(self):
        pkt = packet_wreg32(0xD0200, 42)
        hdr = struct.unpack(">Q", pkt[:8])[0]
        # Lower 16 bits = (offset >> 2) & 0xFFFF (16-bit relative offset)
        encoded_offset = hdr & 0xFFFF
        assert encoded_offset == (0xD0200 >> 2) & 0xFFFF

    def test_wreg32_encodes_value(self):
        pkt = packet_wreg32(0xD0200, 0x12345678)
        value = struct.unpack("<I", pkt[8:12])[0]
        assert value == 0x12345678

    def test_nop_packet(self):
        pkt = packet_nop()
        assert len(pkt) == 8
        hdr = struct.unpack(">Q", pkt)[0]
        opcode = (hdr >> 56) & 0xFF
        assert opcode == regs.PACKET_NOP

    def test_fence_packet(self):
        pkt = packet_fence(dec_val=2, gate_val=3, fence_id=1)
        assert len(pkt) == 16
        hdr = struct.unpack(">Q", pkt[:8])[0]
        opcode = (hdr >> 56) & 0xFF
        assert opcode == regs.PACKET_FENCE
        payload = struct.unpack("<I", pkt[8:12])[0]
        assert payload & 0xFF == 2          # dec_val
        assert (payload >> 8) & 0xFF == 3   # gate_val
        assert (payload >> 16) & 0x3 == 1   # fence_id

    def test_lin_dma_packet(self):
        pkt = packet_lin_dma(
            src_addr=0x1000,
            dst_addr=0x20000000,
            tsize=4096,
            direction=regs.DMA_HOST_TO_DRAM,
        )
        hdr = struct.unpack(">Q", pkt[:8])[0]
        opcode = (hdr >> 56) & 0xFF
        assert opcode == regs.PACKET_LIN_DMA
        # Check control bits
        ctl = hdr & 0xFFFFFFFF
        assert ctl & 1 == 1  # dma_en
        assert (ctl >> 1) & 0x7 == regs.DMA_HOST_TO_DRAM

    def test_lin_dma_addresses(self):
        pkt = packet_lin_dma(0xAAAABBBBCCCC, 0xDDDDEEEEFFFF, 8192)
        # Body starts at offset 8
        src, dst, tsize, _ = struct.unpack("<QQII", pkt[8:])
        assert src == 0xAAAABBBBCCCC
        assert dst == 0xDDDDEEEEFFFF
        assert tsize == 8192

    def test_stop_packet(self):
        pkt = packet_stop()
        assert len(pkt) == 8
        hdr = struct.unpack(">Q", pkt)[0]
        opcode = (hdr >> 56) & 0xFF
        assert opcode == regs.PACKET_STOP


# ---------------------------------------------------------------------------
# Command buffer tests
# ---------------------------------------------------------------------------

class TestCommandBuffer:
    def test_empty_buffer(self):
        cb = CommandBuffer()
        assert len(cb) == 0
        assert cb.build() == b""

    def test_chain_multiple_packets(self):
        cb = CommandBuffer()
        cb.wreg32(regs.MME_CMD, 1).nop().stop()
        buf = cb.build()
        assert len(buf) == 16 + 8 + 8  # wreg32=16, nop=8, stop=8

    def test_dma_command_sequence(self):
        cb = CommandBuffer()
        cb.lin_dma(0x1000, 0x20000000, 4096, regs.DMA_HOST_TO_DRAM)
        cb.fence()
        cb.stop()
        buf = cb.build()
        assert len(buf) > 0

    def test_chaining_returns_self(self):
        cb = CommandBuffer()
        result = cb.nop()
        assert result is cb


# ---------------------------------------------------------------------------
# GEMM descriptor tests
# ---------------------------------------------------------------------------

class TestGEMMDescriptor:
    def test_basic_fp32_descriptor(self):
        desc = GEMMDescriptor(
            a_addr=0x20000000,
            b_addr=0x20100000,
            cout_addr=0x20200000,
            m=64, k=128, n=64,
        )
        header = desc.header_value()
        # FP32 data type
        assert (header >> 24) & 0x3 == regs.MMEHeader.DT_FP32
        assert (header >> 29) & 0x7 == regs.MMEHeader.DT_FP32
        # Store out enabled
        assert header & 0x8000 == 0x8000
        # Signal enabled
        assert header & 0x20 == 0x20

    def test_int8_descriptor(self):
        desc = GEMMDescriptor(
            a_addr=0x20000000,
            b_addr=0x20100000,
            cout_addr=0x20200000,
            m=256, k=256, n=256,
            dtype=regs.MMEHeader.DT_INT8,
            out_dtype=regs.MMEHeader.DT_INT8,
        )
        header = desc.header_value()
        assert (header >> 24) & 0x3 == regs.MMEHeader.DT_INT8
        assert (header >> 29) & 0x7 == regs.MMEHeader.DT_INT8

    def test_transpose_a(self):
        desc = GEMMDescriptor(
            a_addr=0, b_addr=0, cout_addr=0,
            m=32, k=32, n=32,
            transpose_a=True,
        )
        header = desc.header_value()
        assert header & 0x40 == 0x40  # trans_a bit

    def test_relu_via_gemmlowp(self):
        desc = GEMMDescriptor(
            a_addr=0, b_addr=0, cout_addr=0,
            relu=True,
        )
        zp = desc.gemmlowp_zp_value()
        assert zp & (1 << 30) != 0  # ReLU bit

    def test_no_relu(self):
        desc = GEMMDescriptor(a_addr=0, b_addr=0, cout_addr=0, relu=False)
        assert desc.gemmlowp_zp_value() == 0

    def test_associated_dims(self):
        desc = GEMMDescriptor(
            a_addr=0, b_addr=0, cout_addr=0,
            m=128, k=256, n=64,
        )
        d0 = desc.associated_dims_0()
        assert d0 & 0xFFFF == 128       # M
        assert (d0 >> 16) & 0xFFFF == 64  # N

        d1 = desc.associated_dims_1()
        assert d1 & 0xFFFF == 256       # K

    def test_kernel_size_gemm(self):
        desc = GEMMDescriptor(a_addr=0, b_addr=0, cout_addr=0)
        assert desc.kernel_size() == 0  # Standard GEMM = 1x1

    def test_load_cin_and_bias(self):
        desc = GEMMDescriptor(
            a_addr=0, b_addr=0, cout_addr=0,
            cin_addr=0x30000000,
            bias_addr=0x31000000,
            load_cin=True,
            load_bias=True,
        )
        header = desc.header_value()
        assert header & 0x2000 == 0x2000  # load_cin
        assert header & 0x1000 == 0x1000  # load_bias


# ---------------------------------------------------------------------------
# SimBAR integration: write GEMM descriptor
# ---------------------------------------------------------------------------

class TestGEMMOnSimBAR:
    def test_write_gemm_descriptor_to_sim(self):
        bar = SimBARAccessor()
        desc = GEMMDescriptor(
            a_addr=0x20000000,
            b_addr=0x20100000,
            cout_addr=0x20200000,
            m=64, k=128, n=64,
            dtype=regs.MMEHeader.DT_FP32,
            out_dtype=regs.MMEHeader.DT_FP32,
        )
        write_gemm_descriptor(bar, desc)

        # Verify addresses were written
        a_hi = bar.read32(regs.MME_ARCH_A_BASE_ADDR_HIGH)
        a_lo = bar.read32(regs.MME_ARCH_A_BASE_ADDR_LOW)
        assert (a_hi << 32 | a_lo) == 0x20000000

        b_hi = bar.read32(regs.MME_ARCH_B_BASE_ADDR_HIGH)
        b_lo = bar.read32(regs.MME_ARCH_B_BASE_ADDR_LOW)
        assert (b_hi << 32 | b_lo) == 0x20100000

        cout_hi = bar.read32(regs.MME_ARCH_COUT_BASE_ADDR_HIGH)
        cout_lo = bar.read32(regs.MME_ARCH_COUT_BASE_ADDR_LOW)
        assert (cout_hi << 32 | cout_lo) == 0x20200000

        # Verify dimensions
        dims0 = bar.read32(regs.MME_ARCH_ASSOCIATED_DIMS_0)
        assert dims0 & 0xFFFF == 64         # M
        assert (dims0 >> 16) & 0xFFFF == 64  # N

        dims1 = bar.read32(regs.MME_ARCH_ASSOCIATED_DIMS_1)
        assert dims1 & 0xFFFF == 128        # K

        # Verify header
        header = bar.read32(regs.MME_ARCH_HEADER)
        assert header & 0x8000 == 0x8000    # store_out
        assert (header >> 24) & 0x3 == 0    # FP32

    def test_write_with_cin_and_bias(self):
        bar = SimBARAccessor()
        desc = GEMMDescriptor(
            a_addr=0x20000000,
            b_addr=0x20100000,
            cout_addr=0x20200000,
            cin_addr=0x20300000,
            bias_addr=0x20400000,
            m=32, k=32, n=32,
            load_cin=True,
            load_bias=True,
        )
        write_gemm_descriptor(bar, desc)

        cin_lo = bar.read32(regs.MME_ARCH_CIN_BASE_ADDR_LOW)
        assert cin_lo == 0x20300000

        bias_lo = bar.read32(regs.MME_ARCH_BIAS_BASE_ADDR_LOW)
        assert bias_lo == 0x20400000

    def test_mme_execute_returns_true_on_idle_sim(self):
        """SimBAR pre-loads idle status, so execute should return True immediately."""
        bar = SimBARAccessor()
        desc = GEMMDescriptor(
            a_addr=0x20000000, b_addr=0x20100000, cout_addr=0x20200000,
            m=16, k=16, n=16,
        )
        write_gemm_descriptor(bar, desc)
        # SimBAR has idle status pre-loaded
        result = mme_execute_and_wait(bar, timeout_polls=10)
        assert result is True

    def test_mme_execute_timeout_on_busy(self):
        """If status never goes idle, should timeout."""
        bar = SimBARAccessor()
        # Write a busy status (all zeros = not idle)
        bar.write32(regs.MME_ARCH_STATUS, 0x00000000)
        result = mme_execute_and_wait(bar, timeout_polls=10)
        assert result is False


# ---------------------------------------------------------------------------
# SimBAR integration: DMA transfer
# ---------------------------------------------------------------------------

class TestDMAOnSimBAR:
    def test_dma_direct_writes_registers(self):
        bar = SimBARAccessor()
        # DMA will "complete" immediately on SimBAR because STS0 reads as 0 (not busy)
        ok = dma_transfer_direct(bar, 0, src_addr=0x1000, dst_addr=0x20000000, size=4096)
        assert ok is True

        # Verify registers were written
        base = regs.dma_ch_base(0)
        src_lo = bar.read32(base + regs.DMA_CH_LDMA_SRC_ADDR_LO)
        assert src_lo == 0x1000
        dst_lo = bar.read32(base + regs.DMA_CH_LDMA_DST_ADDR_LO)
        assert dst_lo == 0x20000000
        tsize = bar.read32(base + regs.DMA_CH_LDMA_TSIZE)
        assert tsize == 4096
        commit = bar.read32(base + regs.DMA_CH_COMIT_TRANSFER)
        assert commit == 1

    def test_dma_channel_1(self):
        bar = SimBARAccessor()
        ok = dma_transfer_direct(bar, 1, src_addr=0x2000, dst_addr=0x21000000, size=8192)
        assert ok is True
        base = regs.dma_ch_base(1)
        src_lo = bar.read32(base + regs.DMA_CH_LDMA_SRC_ADDR_LO)
        assert src_lo == 0x2000

    def test_dma_timeout(self):
        bar = SimBARAccessor()
        # Make STS0 show busy
        base = regs.dma_ch_base(0)
        bar.write32(base + regs.DMA_CH_STS0, 1)  # bit 0 = busy
        ok = dma_transfer_direct(bar, 0, 0x1000, 0x20000000, 4096, timeout_polls=10)
        assert ok is False

    def test_dma_64bit_addresses(self):
        bar = SimBARAccessor()
        src = 0x100_AABB_CCDD
        dst = 0x200_EEFF_0011
        dma_transfer_direct(bar, 0, src, dst, 1024)
        base = regs.dma_ch_base(0)
        src_lo = bar.read32(base + regs.DMA_CH_LDMA_SRC_ADDR_LO)
        src_hi = bar.read32(base + regs.DMA_CH_LDMA_SRC_ADDR_HI)
        assert (src_hi << 32 | src_lo) == src
        dst_lo = bar.read32(base + regs.DMA_CH_LDMA_DST_ADDR_LO)
        dst_hi = bar.read32(base + regs.DMA_CH_LDMA_DST_ADDR_HI)
        assert (dst_hi << 32 | dst_lo) == dst


# ---------------------------------------------------------------------------
# Full GEMM workflow simulation
# ---------------------------------------------------------------------------

class TestFullGEMMWorkflow:
    def test_end_to_end_gemm_sim(self):
        """Simulate the full GEMM flow: DMA in -> MME execute -> DMA out."""
        bar = SimBARAccessor()

        # Step 1: DMA matrix A from host to DRAM
        a_dram = regs.DRAM_BASE_ADDR_USER
        ok = dma_transfer_direct(bar, 0, src_addr=0x1000, dst_addr=a_dram, size=64*128*4)
        assert ok

        # Step 2: DMA matrix B from host to DRAM
        b_dram = a_dram + 64 * 128 * 4
        ok = dma_transfer_direct(bar, 1, src_addr=0x2000, dst_addr=b_dram, size=128*64*4)
        assert ok

        # Step 3: Write GEMM descriptor
        cout_dram = b_dram + 128 * 64 * 4
        desc = GEMMDescriptor(
            a_addr=a_dram, b_addr=b_dram, cout_addr=cout_dram,
            m=64, k=128, n=64,
            dtype=regs.MMEHeader.DT_FP32,
            out_dtype=regs.MMEHeader.DT_FP32,
        )
        write_gemm_descriptor(bar, desc)

        # Step 4: Execute MME
        ok = mme_execute_and_wait(bar, timeout_polls=100)
        assert ok

        # Step 5: DMA result back to host
        ok = dma_transfer_direct(
            bar, 0, src_addr=cout_dram, dst_addr=0x3000,
            size=64*64*4,
        )
        assert ok

        # Verify all critical registers were touched
        assert bar.read32(regs.MME_CMD) == 1
        assert bar.read32(regs.MME_ARCH_HEADER) != 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

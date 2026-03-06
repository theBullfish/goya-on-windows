"""Tests for register definitions and helpers."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from goya.regs import (
    MMEHeader, mme_is_idle, dma_qm_base, dma_ch_base,
    MME_ARCH_STATUS, MME_CMD, PCIE_VENDOR_ID, PCIE_DEVICE_ID,
)


def test_dma_channel_bases():
    assert dma_qm_base(0) == 0x400000
    assert dma_qm_base(1) == 0x408000
    assert dma_qm_base(2) == 0x410000
    assert dma_qm_base(3) == 0x418000
    assert dma_qm_base(4) == 0x420000

    assert dma_ch_base(0) == 0x401000
    assert dma_ch_base(1) == 0x409000
    assert dma_ch_base(4) == 0x421000


def test_mme_idle_detection():
    # All empty + SM idle = idle
    idle = (1 << 7) | (1 << 8) | (1 << 9) | (1 << 10) | (1 << 11)
    assert mme_is_idle(idle) is True

    # A port busy = not idle
    assert mme_is_idle(idle | 0x01) is False

    # SM not idle = not idle
    not_sm = (1 << 7) | (1 << 8) | (1 << 9) | (1 << 10)  # no bit 11
    assert mme_is_idle(not_sm) is False

    # Zero = not idle (SM not idle)
    assert mme_is_idle(0) is False


def test_mme_header_basic_fp32():
    header = MMEHeader.basic_fp32_gemm()
    # SIGNAL_MASK = 0x01, SIGNAL_EN = 1, STORE_OUT = 1, AB/COUT = FP32(0)
    assert header & 0x1F == 0x01       # signal_mask
    assert header & 0x20 == 0x20       # signal_en
    assert header & 0x8000 == 0x8000   # store_out
    assert (header >> 24) & 0x3 == 0   # AB = FP32
    assert (header >> 29) & 0x7 == 0   # COUT = FP32


def test_mme_header_int8_with_relu():
    header = (
        MMEHeader()
        .signal_mask(0x01)
        .signal_en()
        .store_out()
        .ab_data_type(MMEHeader.DT_INT8)
        .cout_data_type(MMEHeader.DT_INT8)
        .build()
    )
    assert (header >> 24) & 0x3 == 3   # AB = INT8
    assert (header >> 29) & 0x7 == 3   # COUT = INT8
    assert header & 0x8000 == 0x8000   # store_out


def test_mme_header_transpose_a():
    header = MMEHeader().trans_a().build()
    assert header & 0x40 == 0x40


def test_mme_header_load_bias_and_cin():
    header = MMEHeader().load_bias().load_cin().build()
    assert header & 0x1000 == 0x1000   # load_bias
    assert header & 0x2000 == 0x2000   # load_cin


def test_device_ids():
    assert PCIE_VENDOR_ID == 0x1DA3
    assert PCIE_DEVICE_ID == 0x0001


def test_register_offsets():
    assert MME_ARCH_STATUS == 0xD0000
    assert MME_CMD == 0xD0200


if __name__ == "__main__":
    test_dma_channel_bases()
    test_mme_idle_detection()
    test_mme_header_basic_fp32()
    test_mme_header_int8_with_relu()
    test_mme_header_transpose_a()
    test_mme_header_load_bias_and_cin()
    test_device_ids()
    test_register_offsets()
    print("All tests passed!")

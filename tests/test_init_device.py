"""Tests for goya.init and goya.device modules.

All tests run against SimBARAccessor — no hardware required.
"""

import os
import struct
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

if sys.platform != "win32":
    pytest.skip("Goya modules require Windows", allow_module_level=True)

from goya import regs
from goya.pci import SimBARAccessor
from goya.init import (
    CQ_CFG0_VALUE,
    GLBL_ERR_CFG_ENABLE,
    GLBL_ERR_WDATA_VALUE,
    SYNC_MNGR_MON_BASE,
    SYNC_MNGR_SOB_BASE,
    init_all_dma,
    init_dma_channel,
    init_dma_qman,
    init_minimum,
    init_mme_qman,
    soft_reset_engines,
    verify_device_id,
)
from goya.device import (
    GoyaDevice,
    GoyaDMAError,
    GoyaError,
    GoyaInitError,
    GoyaMMEError,
    GoyaStatus,
)
from goya.packets import GEMMDescriptor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bar():
    """Fresh SimBARAccessor for each test."""
    return SimBARAccessor()


@pytest.fixture
def device(bar):
    """Initialized GoyaDevice."""
    dev = GoyaDevice(bar)
    dev.init()
    return dev


# ---------------------------------------------------------------------------
# init.py: verify_device_id
# ---------------------------------------------------------------------------

class TestVerifyDeviceId:
    def test_sim_bar_has_correct_id(self, bar):
        assert verify_device_id(bar)

    def test_wrong_vendor_id_fails(self):
        bar = SimBARAccessor()
        # Overwrite with wrong vendor ID
        struct.pack_into("<I", bar._mem, regs.PCIE_DBI_DEVICE_ID_VENDOR_ID_REG, 0xDEADBEEF)
        assert not verify_device_id(bar)

    def test_zero_id_fails(self):
        bar = SimBARAccessor()
        struct.pack_into("<I", bar._mem, regs.PCIE_DBI_DEVICE_ID_VENDOR_ID_REG, 0)
        assert not verify_device_id(bar)


# ---------------------------------------------------------------------------
# init.py: DMA queue manager init
# ---------------------------------------------------------------------------

class TestDMAQManInit:
    def test_init_channel_0_sets_pq_size(self, bar):
        init_dma_qman(bar, 0)
        qm_base = regs.dma_qm_base(0)
        assert bar.read32(qm_base + regs.DMA_QM_PQ_SIZE) == 6

    def test_init_resets_indices(self, bar):
        init_dma_qman(bar, 0)
        qm_base = regs.dma_qm_base(0)
        assert bar.read32(qm_base + regs.DMA_QM_PQ_PI) == 0
        assert bar.read32(qm_base + regs.DMA_QM_PQ_CI) == 0

    def test_init_sets_cq_cfg0(self, bar):
        init_dma_qman(bar, 2)
        qm_base = regs.dma_qm_base(2)
        assert bar.read32(qm_base + regs.DMA_QM_CQ_CFG0) == CQ_CFG0_VALUE

    def test_init_sets_msg_bases(self, bar):
        init_dma_qman(bar, 0)
        qm_base = regs.dma_qm_base(0)
        assert bar.read32(qm_base + regs.DMA_QM_CP_MSG_BASE0_ADDR_LO) == SYNC_MNGR_SOB_BASE
        assert bar.read32(qm_base + regs.DMA_QM_CP_MSG_BASE1_ADDR_LO) == SYNC_MNGR_MON_BASE

    def test_init_enables_qman(self, bar):
        init_dma_qman(bar, 0)
        qm_base = regs.dma_qm_base(0)
        assert bar.read32(qm_base + regs.DMA_QM_GLBL_CFG0) == 1

    def test_init_sets_error_config(self, bar):
        init_dma_qman(bar, 1)
        qm_base = regs.dma_qm_base(1)
        assert bar.read32(qm_base + regs.DMA_QM_GLBL_ERR_CFG) == GLBL_ERR_CFG_ENABLE
        assert bar.read32(qm_base + regs.DMA_QM_GLBL_ERR_WDATA) == GLBL_ERR_WDATA_VALUE

    def test_init_all_channels(self, bar):
        init_all_dma(bar, channels=5)
        for ch in range(5):
            qm_base = regs.dma_qm_base(ch)
            assert bar.read32(qm_base + regs.DMA_QM_GLBL_CFG0) == 1

    def test_init_channel_with_pq_addr(self, bar):
        addr = 0x00000001_DEADBEEF
        init_dma_qman(bar, 0, pq_base_addr=addr)
        qm_base = regs.dma_qm_base(0)
        lo = bar.read32(qm_base + regs.DMA_QM_PQ_BASE_LO)
        hi = bar.read32(qm_base + regs.DMA_QM_PQ_BASE_HI)
        assert lo == addr & 0xFFFFFFFF
        assert hi == (addr >> 32) & 0xFFFFFFFF

    def test_invalid_channel_asserts(self, bar):
        with pytest.raises(AssertionError):
            init_dma_qman(bar, 5)
        with pytest.raises(AssertionError):
            init_dma_qman(bar, -1)


class TestDMAChannelInit:
    def test_clears_error_regs(self, bar):
        init_dma_channel(bar, 0)
        ch_base = regs.dma_ch_base(0)
        assert bar.read32(ch_base + regs.DMA_CH_ERRMSG_ADDR_LO) == 0
        assert bar.read32(ch_base + regs.DMA_CH_ERRMSG_ADDR_HI) == 0

    def test_sets_cfg_regs(self, bar):
        init_dma_channel(bar, 3)
        ch_base = regs.dma_ch_base(3)
        assert bar.read32(ch_base + regs.DMA_CH_CFG0) == 0


# ---------------------------------------------------------------------------
# init.py: MME queue manager init
# ---------------------------------------------------------------------------

class TestMMEQManInit:
    def test_sets_pq_size(self, bar):
        init_mme_qman(bar)
        assert bar.read32(regs.MME_QM_PQ_SIZE) == 6

    def test_resets_indices(self, bar):
        init_mme_qman(bar)
        assert bar.read32(regs.MME_QM_PQ_PI) == 0
        assert bar.read32(regs.MME_QM_PQ_CI) == 0

    def test_sets_cq_cfg0(self, bar):
        init_mme_qman(bar)
        assert bar.read32(regs.MME_QM_CQ_CFG0) == CQ_CFG0_VALUE

    def test_sets_msg_bases(self, bar):
        init_mme_qman(bar)
        assert bar.read32(regs.MME_QM_CP_MSG_BASE0_ADDR_LO) == SYNC_MNGR_SOB_BASE
        assert bar.read32(regs.MME_QM_CP_MSG_BASE1_ADDR_LO) == SYNC_MNGR_MON_BASE

    def test_enables_qman(self, bar):
        init_mme_qman(bar)
        assert bar.read32(regs.MME_QM_GLBL_CFG0) == 1

    def test_sets_sm_base_address(self, bar):
        init_mme_qman(bar)
        assert bar.read32(regs.MME_SM_BASE_ADDRESS_LOW) == SYNC_MNGR_SOB_BASE
        assert bar.read32(regs.MME_SM_BASE_ADDRESS_HIGH) == 0

    def test_sets_error_config(self, bar):
        init_mme_qman(bar)
        assert bar.read32(regs.MME_QM_GLBL_ERR_CFG) == GLBL_ERR_CFG_ENABLE


# ---------------------------------------------------------------------------
# init.py: init_minimum
# ---------------------------------------------------------------------------

class TestInitMinimum:
    def test_returns_dma_and_mme_caps(self, bar):
        caps = init_minimum(bar)
        assert caps & regs.HW_CAP_DMA
        assert caps & regs.HW_CAP_MME

    def test_returns_zero_on_wrong_device(self):
        bar = SimBARAccessor()
        struct.pack_into("<I", bar._mem, regs.PCIE_DBI_DEVICE_ID_VENDOR_ID_REG, 0)
        caps = init_minimum(bar)
        assert caps == 0

    def test_all_qmans_enabled_after_init(self, bar):
        init_minimum(bar)
        for ch in range(5):
            qm_base = regs.dma_qm_base(ch)
            assert bar.read32(qm_base + regs.DMA_QM_GLBL_CFG0) == 1
        assert bar.read32(regs.MME_QM_GLBL_CFG0) == 1


# ---------------------------------------------------------------------------
# init.py: soft_reset_engines
# ---------------------------------------------------------------------------

class TestSoftReset:
    def test_disables_all_qmans(self, bar):
        init_minimum(bar)
        soft_reset_engines(bar)
        for ch in range(5):
            qm_base = regs.dma_qm_base(ch)
            assert bar.read32(qm_base + regs.DMA_QM_GLBL_CFG0) == 0
        assert bar.read32(regs.MME_QM_GLBL_CFG0) == 0

    def test_writes_mme_reset(self, bar):
        soft_reset_engines(bar)
        assert bar.read32(regs.MME_RESET) == 1


# ---------------------------------------------------------------------------
# device.py: GoyaDevice lifecycle
# ---------------------------------------------------------------------------

class TestGoyaDeviceLifecycle:
    def test_init_succeeds_on_sim(self, bar):
        dev = GoyaDevice(bar)
        caps = dev.init()
        assert caps & regs.HW_CAP_DMA
        assert caps & regs.HW_CAP_MME
        assert dev.initialized

    def test_init_fails_on_wrong_device(self):
        bar = SimBARAccessor()
        struct.pack_into("<I", bar._mem, regs.PCIE_DBI_DEVICE_ID_VENDOR_ID_REG, 0)
        dev = GoyaDevice(bar)
        with pytest.raises(GoyaInitError, match="Device ID"):
            dev.init()

    def test_shutdown_resets_state(self, bar):
        dev = GoyaDevice(bar)
        dev.init()
        dev.shutdown()
        assert not dev.initialized
        assert dev.hw_caps == 0

    def test_shutdown_idempotent(self, bar):
        dev = GoyaDevice(bar)
        dev.init()
        dev.shutdown()
        dev.shutdown()  # should not raise
        assert not dev.initialized

    def test_context_manager(self, bar):
        with GoyaDevice(bar) as dev:
            assert dev.initialized
        assert not dev.initialized

    def test_repr_uninit(self, bar):
        dev = GoyaDevice(bar)
        assert "UNINIT" in repr(dev)

    def test_repr_ready(self, device):
        assert "READY" in repr(device)


# ---------------------------------------------------------------------------
# device.py: require_init guard
# ---------------------------------------------------------------------------

class TestRequireInit:
    def test_gemm_before_init_raises(self, bar):
        dev = GoyaDevice(bar)
        desc = GEMMDescriptor(a_addr=0, b_addr=0, cout_addr=0)
        with pytest.raises(GoyaError, match="not initialized"):
            dev.gemm(desc)

    def test_dma_before_init_raises(self, bar):
        dev = GoyaDevice(bar)
        with pytest.raises(GoyaError, match="not initialized"):
            dev.dma_transfer(0, 0, 0, 64)

    def test_write_dram_before_init_raises(self, bar):
        dev = GoyaDevice(bar)
        with pytest.raises(GoyaError, match="not initialized"):
            dev.write_to_dram(0, b"\x00")

    def test_read_dram_before_init_raises(self, bar):
        dev = GoyaDevice(bar)
        with pytest.raises(GoyaError, match="not initialized"):
            dev.read_from_dram(0, 4)


# ---------------------------------------------------------------------------
# device.py: status
# ---------------------------------------------------------------------------

class TestGoyaStatus:
    def test_status_ready_after_init(self, device):
        st = device.status()
        assert st.is_ready
        assert st.mme_idle
        assert st.hw_caps & regs.HW_CAP_DMA
        assert st.hw_caps & regs.HW_CAP_MME

    def test_dma_channels_idle(self, device):
        st = device.status()
        assert len(st.dma_ch_busy) == 5
        assert all(not busy for busy in st.dma_ch_busy)


# ---------------------------------------------------------------------------
# device.py: DRAM read/write (sim)
# ---------------------------------------------------------------------------

class TestDRAMAccess:
    def test_write_and_read_back(self, device):
        data = struct.pack("<4f", 1.0, 2.0, 3.0, 4.0)
        offset = 0x1000
        device.write_to_dram(offset, data)
        result = device.read_from_dram(offset, len(data))
        assert result == data

    def test_write_non_aligned_size(self, device):
        data = b"\x01\x02\x03"  # 3 bytes, not 4-aligned
        offset = 0x2000
        device.write_to_dram(offset, data)
        result = device.read_from_dram(offset, 4)
        # Should be padded with zero
        assert result[:3] == data
        assert result[3:4] == b"\x00"

    def test_read_zero_region(self, device):
        result = device.read_from_dram(0x3000, 8)
        assert result == b"\x00" * 8


# ---------------------------------------------------------------------------
# device.py: GEMM execution
# ---------------------------------------------------------------------------

class TestGEMMExecution:
    def test_gemm_completes_on_sim(self, device):
        """SimBARAccessor pre-loads MME status as idle, so GEMM succeeds."""
        desc = GEMMDescriptor(
            a_addr=regs.DRAM_BASE_ADDR_USER,
            b_addr=regs.DRAM_BASE_ADDR_USER + 0x10000,
            cout_addr=regs.DRAM_BASE_ADDR_USER + 0x20000,
            m=64, k=64, n=64,
        )
        device.gemm(desc)  # Should not raise

    def test_gemm_writes_header(self, device, bar):
        desc = GEMMDescriptor(
            a_addr=0x1000,
            b_addr=0x2000,
            cout_addr=0x3000,
            m=32, k=16, n=32,
            dtype=regs.MMEHeader.DT_FP16,
        )
        device.gemm(desc)
        header = bar.read32(regs.MME_ARCH_HEADER)
        assert header != 0

    def test_gemm_writes_addresses(self, device, bar):
        desc = GEMMDescriptor(
            a_addr=0x0000_0001_0000_1000,
            b_addr=0x0000_0001_0000_2000,
            cout_addr=0x0000_0001_0000_3000,
        )
        device.gemm(desc)
        a_lo = bar.read32(regs.MME_ARCH_A_BASE_ADDR_LOW)
        a_hi = bar.read32(regs.MME_ARCH_A_BASE_ADDR_HIGH)
        assert a_lo == 0x00001000
        assert a_hi == 0x00000001

    def test_gemm_with_relu(self, device, bar):
        desc = GEMMDescriptor(
            a_addr=0x1000, b_addr=0x2000, cout_addr=0x3000,
            relu=True,
        )
        device.gemm(desc)
        zp = bar.read32(regs.MME_ARCH_GEMMLOWP_ZP)
        assert zp & (1 << 30)  # ReLU bit set

    def test_gemm_triggers_mme_cmd(self, device, bar):
        desc = GEMMDescriptor(a_addr=0x1000, b_addr=0x2000, cout_addr=0x3000)
        device.gemm(desc)
        cmd = bar.read32(regs.MME_CMD)
        assert cmd == 1


# ---------------------------------------------------------------------------
# device.py: DMA transfer
# ---------------------------------------------------------------------------

class TestDMATransfer:
    def test_dma_direct_succeeds_on_sim(self, device):
        """SimBARAccessor returns 0 for STS0 (not busy), so transfer succeeds."""
        device.dma_transfer(
            channel=0,
            src_addr=0x1000,
            dst_addr=regs.DRAM_BASE_ADDR_USER,
            size=256,
        )

    def test_dma_writes_src_dst_regs(self, device, bar):
        src = 0x0000_0002_0000_0000
        dst = 0x0000_0003_0000_0000
        device.dma_transfer(0, src, dst, 1024)
        ch_base = regs.dma_ch_base(0)
        assert bar.read32(ch_base + regs.DMA_CH_LDMA_SRC_ADDR_LO) == 0
        assert bar.read32(ch_base + regs.DMA_CH_LDMA_SRC_ADDR_HI) == 2
        assert bar.read32(ch_base + regs.DMA_CH_LDMA_DST_ADDR_LO) == 0
        assert bar.read32(ch_base + regs.DMA_CH_LDMA_DST_ADDR_HI) == 3

    def test_dma_commits_transfer(self, device, bar):
        device.dma_transfer(0, 0, 0, 64)
        ch_base = regs.dma_ch_base(0)
        assert bar.read32(ch_base + regs.DMA_CH_COMIT_TRANSFER) == 1


# ---------------------------------------------------------------------------
# Full pipeline: init → write → GEMM → read
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_end_to_end(self, bar):
        """Full lifecycle: init, write data, GEMM, read back, shutdown."""
        with GoyaDevice(bar) as dev:
            # Check status
            st = dev.status()
            assert st.is_ready

            # Write "matrix" data to DRAM offsets
            a_data = struct.pack("<4f", 1.0, 2.0, 3.0, 4.0)
            b_data = struct.pack("<4f", 5.0, 6.0, 7.0, 8.0)
            a_offset = 0x4000
            b_offset = 0x5000
            c_offset = 0x6000

            dev.write_to_dram(a_offset, a_data)
            dev.write_to_dram(b_offset, b_data)

            # GEMM (descriptors only — sim doesn't compute)
            desc = GEMMDescriptor(
                a_addr=a_offset,
                b_addr=b_offset,
                cout_addr=c_offset,
                m=2, k=2, n=2,
            )
            dev.gemm(desc)

            # Read back (will be zeros since sim doesn't compute)
            result = dev.read_from_dram(c_offset, 16)
            assert len(result) == 16

        # After context manager, device is shut down
        assert not dev.initialized

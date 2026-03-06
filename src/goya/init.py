"""Goya hardware initialization sequences.

Queue manager init for DMA channels and MME, following the sequence
documented in docs/init-sequence.md (derived from Linux goya_hw_init).

All functions operate on a BARAccessor — works with SimBARAccessor
for offline testing and KMDFBARAccessor for real hardware.
"""

from __future__ import annotations

from . import regs
from .pci import BARAccessor


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CQ_CFG0 cache line config (from Linux driver)
CQ_CFG0_VALUE = 0x00080008

# Sync manager base addresses
SYNC_MNGR_SOB_BASE = regs.SYNC_MNGR_SOB_OBJ_0      # 0x112000
SYNC_MNGR_MON_BASE = regs.SYNC_MNGR_MON_PAY_ADDRL_0  # 0x113000

# CP LDMA default config values
CP_LDMA_TSIZE = 0x1000          # 4KB local DMA transfer size
CP_LDMA_SRC_OFFSET = 0x2000     # Source offset within CP
CP_LDMA_DST_OFFSET = 0x0        # Destination offset

# Error handling defaults
GLBL_ERR_CFG_ENABLE = 0x1F      # Enable all error types
GLBL_ERR_WDATA_VALUE = 0xBAD0   # Error notification data


# ---------------------------------------------------------------------------
# DMA Queue Manager init
# ---------------------------------------------------------------------------

def init_dma_qman(
    bar: BARAccessor,
    channel: int,
    pq_base_addr: int = 0,
) -> None:
    """Initialize a single DMA queue manager (channel 0-4).

    Follows the goya_init_dma_qman() sequence from the Linux driver:
    1. PQ_BASE address + size
    2. Reset producer/consumer indices
    3. CP LDMA offsets for command processor
    4. CP message bases (sync manager SOB + monitor)
    5. CQ cache line config
    6. Error handling
    7. Protection settings
    8. Enable the queue manager

    Args:
        bar: BAR accessor for register writes
        channel: DMA channel index (0-4)
        pq_base_addr: Physical address of packet queue buffer (0 for sim)
    """
    assert 0 <= channel <= 4
    qm_base = regs.dma_qm_base(channel)

    # Packet queue base address (host physical)
    bar.write32(qm_base + regs.DMA_QM_PQ_BASE_LO, pq_base_addr & 0xFFFFFFFF)
    bar.write32(qm_base + regs.DMA_QM_PQ_BASE_HI, (pq_base_addr >> 32) & 0xFFFFFFFF)

    # Queue size: ilog2(64) = 6 (64-entry queue)
    bar.write32(qm_base + regs.DMA_QM_PQ_SIZE, 6)

    # Reset producer and consumer indices
    bar.write32(qm_base + regs.DMA_QM_PQ_PI, 0)
    bar.write32(qm_base + regs.DMA_QM_PQ_CI, 0)

    # CP local DMA configuration
    bar.write32(qm_base + regs.DMA_QM_CP_LDMA_TSIZE_OFFSET, CP_LDMA_TSIZE)
    bar.write32(qm_base + regs.DMA_QM_CP_LDMA_SRC_BASE_LO_OFFSET, CP_LDMA_SRC_OFFSET)
    bar.write32(qm_base + regs.DMA_QM_CP_LDMA_SRC_BASE_HI_OFFSET, 0)
    bar.write32(qm_base + regs.DMA_QM_CP_LDMA_DST_BASE_LO_OFFSET, CP_LDMA_DST_OFFSET)
    bar.write32(qm_base + regs.DMA_QM_CP_LDMA_DST_BASE_HI_OFFSET, 0)

    # CP message base addresses (sync manager)
    bar.write32(qm_base + regs.DMA_QM_CP_MSG_BASE0_ADDR_LO, SYNC_MNGR_SOB_BASE & 0xFFFFFFFF)
    bar.write32(qm_base + regs.DMA_QM_CP_MSG_BASE0_ADDR_HI, 0)
    bar.write32(qm_base + regs.DMA_QM_CP_MSG_BASE1_ADDR_LO, SYNC_MNGR_MON_BASE & 0xFFFFFFFF)
    bar.write32(qm_base + regs.DMA_QM_CP_MSG_BASE1_ADDR_HI, 0)

    # Completion queue config
    bar.write32(qm_base + regs.DMA_QM_CQ_CFG0, CQ_CFG0_VALUE)

    # Error handling
    bar.write32(qm_base + regs.DMA_QM_GLBL_ERR_CFG, GLBL_ERR_CFG_ENABLE)
    bar.write32(qm_base + regs.DMA_QM_GLBL_ERR_ADDR_LO, 0)
    bar.write32(qm_base + regs.DMA_QM_GLBL_ERR_ADDR_HI, 0)
    bar.write32(qm_base + regs.DMA_QM_GLBL_ERR_WDATA, GLBL_ERR_WDATA_VALUE)

    # Protection: 0 = no protection for now (all queues accessible)
    bar.write32(qm_base + regs.DMA_QM_GLBL_PROT, 0)

    # Enable the queue manager (bit 0 = enable)
    bar.write32(qm_base + regs.DMA_QM_GLBL_CFG0, 1)


def init_dma_channel(bar: BARAccessor, channel: int) -> None:
    """Initialize DMA channel hardware registers.

    Separate from queue manager — this configures the DMA engine itself.
    """
    assert 0 <= channel <= 4
    ch_base = regs.dma_ch_base(channel)

    # Channel config: enable, set default mode
    bar.write32(ch_base + regs.DMA_CH_CFG0, 0)
    bar.write32(ch_base + regs.DMA_CH_CFG1, 0)

    # Clear error message registers
    bar.write32(ch_base + regs.DMA_CH_ERRMSG_ADDR_LO, 0)
    bar.write32(ch_base + regs.DMA_CH_ERRMSG_ADDR_HI, 0)
    bar.write32(ch_base + regs.DMA_CH_ERRMSG_WDATA, 0)


def init_all_dma(bar: BARAccessor, channels: int = 5) -> None:
    """Initialize all DMA queue managers and channels."""
    for ch in range(channels):
        init_dma_qman(bar, ch)
        init_dma_channel(bar, ch)


# ---------------------------------------------------------------------------
# MME Queue Manager init
# ---------------------------------------------------------------------------

def init_mme_qman(bar: BARAccessor, pq_base_addr: int = 0) -> None:
    """Initialize the MME queue manager.

    Follows goya_init_mme_qmans() from the Linux driver.
    Same pattern as DMA QM but at MME_QM register offsets.

    Args:
        bar: BAR accessor for register writes
        pq_base_addr: Physical address of MME packet queue buffer
    """
    # Packet queue base address
    bar.write32(regs.MME_QM_PQ_BASE_LO, pq_base_addr & 0xFFFFFFFF)
    bar.write32(regs.MME_QM_PQ_BASE_HI, (pq_base_addr >> 32) & 0xFFFFFFFF)

    # Queue size: ilog2(MME_QMAN_LENGTH=64) = 6
    bar.write32(regs.MME_QM_PQ_SIZE, 6)

    # Reset indices
    bar.write32(regs.MME_QM_PQ_PI, 0)
    bar.write32(regs.MME_QM_PQ_CI, 0)

    # CP message base addresses (sync manager)
    bar.write32(regs.MME_QM_CP_MSG_BASE0_ADDR_LO, SYNC_MNGR_SOB_BASE & 0xFFFFFFFF)
    bar.write32(regs.MME_QM_CP_MSG_BASE0_ADDR_HI, 0)
    bar.write32(regs.MME_QM_CP_MSG_BASE1_ADDR_LO, SYNC_MNGR_MON_BASE & 0xFFFFFFFF)
    bar.write32(regs.MME_QM_CP_MSG_BASE1_ADDR_HI, 0)

    # Completion queue config
    bar.write32(regs.MME_QM_CQ_CFG0, CQ_CFG0_VALUE)

    # Error handling
    bar.write32(regs.MME_QM_GLBL_ERR_CFG, GLBL_ERR_CFG_ENABLE)
    bar.write32(regs.MME_QM_GLBL_ERR_ADDR_LO, 0)
    bar.write32(regs.MME_QM_GLBL_ERR_ADDR_HI, 0)
    bar.write32(regs.MME_QM_GLBL_ERR_WDATA, GLBL_ERR_WDATA_VALUE)

    # Protection
    bar.write32(regs.MME_QM_GLBL_PROT, 0)

    # Enable the MME queue manager
    bar.write32(regs.MME_QM_GLBL_CFG0, 1)

    # Set sync manager base address for MME
    bar.write32(regs.MME_SM_BASE_ADDRESS_LOW, SYNC_MNGR_SOB_BASE)
    bar.write32(regs.MME_SM_BASE_ADDRESS_HIGH, 0)


# ---------------------------------------------------------------------------
# Device verification
# ---------------------------------------------------------------------------

def verify_device_id(bar: BARAccessor) -> bool:
    """Read PCIe device ID register and verify it's a Goya."""
    vid_did = bar.read32(regs.PCIE_DBI_DEVICE_ID_VENDOR_ID_REG)
    vendor = vid_did & 0xFFFF
    device = (vid_did >> 16) & 0xFFFF
    return vendor == regs.PCIE_VENDOR_ID and device == regs.PCIE_DEVICE_ID


# ---------------------------------------------------------------------------
# Soft reset
# ---------------------------------------------------------------------------

def soft_reset_engines(bar: BARAccessor) -> None:
    """Reset MME and DMA engines. Used during shutdown or error recovery."""
    bar.write32(regs.MME_RESET, 1)

    # Disable all DMA queue managers
    for ch in range(5):
        qm_base = regs.dma_qm_base(ch)
        bar.write32(qm_base + regs.DMA_QM_GLBL_CFG0, 0)

    # Disable MME queue manager
    bar.write32(regs.MME_QM_GLBL_CFG0, 0)


# ---------------------------------------------------------------------------
# Full init sequence (minimum path)
# ---------------------------------------------------------------------------

def init_minimum(bar: BARAccessor) -> int:
    """Run the minimum init sequence for MME + DMA operation.

    Returns a bitmask of hardware capabilities that were initialized.
    Firmware load and DDR training are NOT handled here — those must
    be done before calling this function on real hardware.

    On SimBARAccessor this runs the full sequence for testing.
    """
    caps = 0

    # Phase A: Verify device
    if not verify_device_id(bar):
        return caps

    # Phase C: DMA init (all 5 channels)
    init_all_dma(bar)
    caps |= regs.HW_CAP_DMA

    # Phase D: MME init
    init_mme_qman(bar)
    caps |= regs.HW_CAP_MME

    return caps

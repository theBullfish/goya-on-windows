"""Goya register definitions — offsets relative to BAR0 base.

Derived from Linux kernel drivers/accel/habanalabs/include/goya/asic_reg/
(GPL source, clean-room documented as offset constants only).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Device identification
# ---------------------------------------------------------------------------
PCIE_VENDOR_ID = 0x1DA3
PCIE_DEVICE_ID = 0x0001
PCIE_DBI_DEVICE_ID_VENDOR_ID_REG = 0xC02000

# ---------------------------------------------------------------------------
# MME Architecture Registers (matrix multiply descriptor)
# ---------------------------------------------------------------------------
MME_ARCH_STATUS             = 0xD0000
MME_ARCH_A_BASE_ADDR_HIGH   = 0xD0008
MME_ARCH_B_BASE_ADDR_HIGH   = 0xD000C
MME_ARCH_CIN_BASE_ADDR_HIGH = 0xD0010
MME_ARCH_COUT_BASE_ADDR_HIGH = 0xD0014
MME_ARCH_BIAS_BASE_ADDR_HIGH = 0xD0018
MME_ARCH_A_BASE_ADDR_LOW    = 0xD001C
MME_ARCH_B_BASE_ADDR_LOW    = 0xD0020
MME_ARCH_CIN_BASE_ADDR_LOW  = 0xD0024
MME_ARCH_COUT_BASE_ADDR_LOW = 0xD0028
MME_ARCH_BIAS_BASE_ADDR_LOW = 0xD002C
MME_ARCH_HEADER             = 0xD0030
MME_ARCH_KERNEL_SIZE_MINUS_1 = 0xD0034
MME_ARCH_ASSOCIATED_DIMS_0  = 0xD0038
MME_ARCH_ASSOCIATED_DIMS_1  = 0xD003C
MME_ARCH_COUT_SCALE         = 0xD0040
MME_ARCH_CIN_SCALE          = 0xD0044
MME_ARCH_GEMMLOWP_ZP        = 0xD0048
MME_ARCH_GEMMLOWP_EXPONENT  = 0xD004C

# ---------------------------------------------------------------------------
# MME Control
# ---------------------------------------------------------------------------
MME_CMD                     = 0xD0200
MME_DUMMY                   = 0xD0204
MME_RESET                   = 0xD0208
MME_STALL                   = 0xD020C
MME_SM_BASE_ADDRESS_LOW     = 0xD0210
MME_SM_BASE_ADDRESS_HIGH    = 0xD0214

# ---------------------------------------------------------------------------
# MME Execution Unit Config
# ---------------------------------------------------------------------------
MME_STORE_MAX_CREDIT        = 0xD0300
MME_AGU                     = 0xD0304
MME_SBA                     = 0xD0308
MME_SBB                     = 0xD030C
MME_SBC                     = 0xD0310
MME_WBC                     = 0xD0314
MME_TE                      = 0xD0328
MME_TE2DEC                  = 0xD032C

# ---------------------------------------------------------------------------
# MME Error Registers
# ---------------------------------------------------------------------------
MME_REI_STATUS              = 0xD0330
MME_REI_MASK                = 0xD0334
MME_SEI_STATUS              = 0xD0338
MME_SEI_MASK                = 0xD033C
MME_SPI_STATUS              = 0xD0340
MME_SPI_MASK                = 0xD0344

# ---------------------------------------------------------------------------
# MME Shadow Register Banks (same layout as ARCH at each base)
# ---------------------------------------------------------------------------
MME_SHADOW_0_BASE           = 0xD0400
MME_SHADOW_1_BASE           = 0xD0600
MME_SHADOW_2_BASE           = 0xD0800
MME_SHADOW_3_BASE           = 0xD0A00

# ---------------------------------------------------------------------------
# MME Queue Manager
# ---------------------------------------------------------------------------
MME_QM_GLBL_CFG0            = 0xD8000
MME_QM_GLBL_CFG1            = 0xD8004
MME_QM_GLBL_PROT            = 0xD8008
MME_QM_GLBL_ERR_CFG         = 0xD800C
MME_QM_GLBL_ERR_ADDR_LO     = 0xD8010
MME_QM_GLBL_ERR_ADDR_HI     = 0xD8014
MME_QM_GLBL_ERR_WDATA       = 0xD8018
MME_QM_GLBL_STS0            = 0xD8024
MME_QM_GLBL_STS1            = 0xD8028
MME_QM_PQ_BASE_LO           = 0xD8060
MME_QM_PQ_BASE_HI           = 0xD8064
MME_QM_PQ_SIZE              = 0xD8068
MME_QM_PQ_PI                = 0xD806C
MME_QM_PQ_CI                = 0xD8070
MME_QM_CQ_CFG0              = 0xD80B0
MME_QM_CQ_PTR_LO            = 0xD80C0
MME_QM_CQ_PTR_HI            = 0xD80C4
MME_QM_CQ_TSIZE             = 0xD80C8
MME_QM_CQ_CTL               = 0xD80CC
MME_QM_CP_MSG_BASE0_ADDR_LO = 0xD8120
MME_QM_CP_MSG_BASE0_ADDR_HI = 0xD8124
MME_QM_CP_MSG_BASE1_ADDR_LO = 0xD8128
MME_QM_CP_MSG_BASE1_ADDR_HI = 0xD812C

# ---------------------------------------------------------------------------
# MME Command Queue
# ---------------------------------------------------------------------------
MME_CMDQ_GLBL_CFG0          = 0xD9000
MME_CMDQ_CQ_PTR_LO          = 0xD90C0
MME_CMDQ_CQ_PTR_HI          = 0xD90C4
MME_CMDQ_CQ_TSIZE           = 0xD90C8
MME_CMDQ_CQ_CTL             = 0xD90CC
MME_CMDQ_CP_STS              = 0xD9178

# ---------------------------------------------------------------------------
# DMA Channel Registers — offsets from DMA_CH_n base
# DMA_CH_n_BASE = 0x401000 + n * 0x8000
# ---------------------------------------------------------------------------
DMA_CH_CFG0                 = 0x000
DMA_CH_CFG1                 = 0x004
DMA_CH_ERRMSG_ADDR_LO       = 0x008
DMA_CH_ERRMSG_ADDR_HI       = 0x00C
DMA_CH_ERRMSG_WDATA         = 0x010
DMA_CH_RD_COMP_ADDR_LO      = 0x014
DMA_CH_RD_COMP_ADDR_HI      = 0x018
DMA_CH_RD_COMP_WDATA        = 0x01C
DMA_CH_WR_COMP_ADDR_LO      = 0x020
DMA_CH_WR_COMP_ADDR_HI      = 0x024
DMA_CH_WR_COMP_WDATA        = 0x028
DMA_CH_LDMA_SRC_ADDR_LO     = 0x02C
DMA_CH_LDMA_SRC_ADDR_HI     = 0x030
DMA_CH_LDMA_DST_ADDR_LO     = 0x034
DMA_CH_LDMA_DST_ADDR_HI     = 0x038
DMA_CH_LDMA_TSIZE           = 0x03C
DMA_CH_COMIT_TRANSFER       = 0x040
DMA_CH_STS0                 = 0x044
DMA_CH_STS1                 = 0x048

# ---------------------------------------------------------------------------
# DMA Queue Manager — offsets from DMA_QM_n base
# DMA_QM_n_BASE = 0x400000 + n * 0x8000
# ---------------------------------------------------------------------------
DMA_QM_GLBL_CFG0            = 0x000
DMA_QM_GLBL_CFG1            = 0x004
DMA_QM_GLBL_PROT            = 0x008
DMA_QM_GLBL_ERR_CFG         = 0x00C
DMA_QM_GLBL_ERR_ADDR_LO     = 0x010
DMA_QM_GLBL_ERR_ADDR_HI     = 0x014
DMA_QM_GLBL_ERR_WDATA       = 0x018
DMA_QM_GLBL_STS0            = 0x024
DMA_QM_GLBL_STS1            = 0x028
DMA_QM_PQ_BASE_LO           = 0x060
DMA_QM_PQ_BASE_HI           = 0x064
DMA_QM_PQ_SIZE              = 0x068
DMA_QM_PQ_PI                = 0x06C
DMA_QM_PQ_CI                = 0x070
DMA_QM_CQ_CFG0              = 0x0B0
DMA_QM_CQ_PTR_LO            = 0x0C0
DMA_QM_CQ_PTR_HI            = 0x0C4
DMA_QM_CQ_TSIZE             = 0x0C8
DMA_QM_CQ_CTL               = 0x0CC
DMA_QM_CP_MSG_BASE0_ADDR_LO = 0x120
DMA_QM_CP_MSG_BASE0_ADDR_HI = 0x124
DMA_QM_CP_MSG_BASE1_ADDR_LO = 0x128
DMA_QM_CP_MSG_BASE1_ADDR_HI = 0x12C
DMA_QM_CP_LDMA_TSIZE_OFFSET = 0x140
DMA_QM_CP_LDMA_SRC_BASE_LO_OFFSET = 0x144
DMA_QM_CP_LDMA_SRC_BASE_HI_OFFSET = 0x148
DMA_QM_CP_LDMA_DST_BASE_LO_OFFSET = 0x14C
DMA_QM_CP_LDMA_DST_BASE_HI_OFFSET = 0x150
DMA_QM_CP_LDMA_COMMIT_OFFSET = 0x154
DMA_QM_CP_FENCE0_RDATA      = 0x158
DMA_QM_CP_STS                = 0x178

# ---------------------------------------------------------------------------
# Sync Manager
# ---------------------------------------------------------------------------
SYNC_MNGR_SOB_OBJ_0         = 0x112000
SYNC_MNGR_SOB_OBJ_1023      = 0x112FFC
SYNC_MNGR_MON_PAY_ADDRL_0   = 0x113000
SYNC_MNGR_MON_STATUS_0      = 0x114000
SYNC_MNGR_MON_STATUS_255    = 0x1143FC

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def dma_qm_base(channel: int) -> int:
    """Absolute BAR0 offset for DMA queue manager of given channel (0-4)."""
    assert 0 <= channel <= 4
    return 0x400000 + channel * 0x8000

def dma_ch_base(channel: int) -> int:
    """Absolute BAR0 offset for DMA channel registers (0-4)."""
    assert 0 <= channel <= 4
    return 0x401000 + channel * 0x8000


# ---------------------------------------------------------------------------
# MME_ARCH_HEADER bit field helpers
# ---------------------------------------------------------------------------

class MMEHeader:
    """Builder for the MME_ARCH_HEADER register value."""

    # Data types (2-bit encoding for AB, inferred)
    DT_FP32 = 0
    DT_FP16 = 1
    DT_BF16 = 2
    DT_INT8 = 3

    def __init__(self) -> None:
        self._val = 0

    def signal_mask(self, mask: int) -> "MMEHeader":
        self._val = (self._val & ~0x1F) | (mask & 0x1F)
        return self

    def signal_en(self, en: bool = True) -> "MMEHeader":
        self._val = (self._val & ~0x20) | (int(en) << 5)
        return self

    def trans_a(self, en: bool = True) -> "MMEHeader":
        self._val = (self._val & ~0x40) | (int(en) << 6)
        return self

    def lower_a(self, en: bool = True) -> "MMEHeader":
        self._val = (self._val & ~0x80) | (int(en) << 7)
        return self

    def accum_mask(self, mask: int) -> "MMEHeader":
        self._val = (self._val & ~0xF00) | ((mask & 0xF) << 8)
        return self

    def load_bias(self, en: bool = True) -> "MMEHeader":
        self._val = (self._val & ~0x1000) | (int(en) << 12)
        return self

    def load_cin(self, en: bool = True) -> "MMEHeader":
        self._val = (self._val & ~0x2000) | (int(en) << 13)
        return self

    def store_out(self, en: bool = True) -> "MMEHeader":
        self._val = (self._val & ~0x8000) | (int(en) << 15)
        return self

    def advance_a(self, en: bool = True) -> "MMEHeader":
        self._val = (self._val & ~0x20000) | (int(en) << 17)
        return self

    def advance_b(self, en: bool = True) -> "MMEHeader":
        self._val = (self._val & ~0x40000) | (int(en) << 18)
        return self

    def ab_data_type(self, dt: int) -> "MMEHeader":
        self._val = (self._val & ~0x3000000) | ((dt & 0x3) << 24)
        return self

    def cin_data_type(self, dt: int) -> "MMEHeader":
        self._val = (self._val & ~0x1C000000) | ((dt & 0x7) << 26)
        return self

    def cout_data_type(self, dt: int) -> "MMEHeader":
        self._val = (self._val & ~0xE0000000) | ((dt & 0x7) << 29)
        return self

    def build(self) -> int:
        return self._val

    @staticmethod
    def basic_fp32_gemm() -> int:
        """Header for a simple A × B → Cout in FP32."""
        return (
            MMEHeader()
            .signal_mask(0x01)
            .signal_en()
            .store_out()
            .ab_data_type(MMEHeader.DT_FP32)
            .cout_data_type(MMEHeader.DT_FP32)
            .build()
        )


# ---------------------------------------------------------------------------
# MME_ARCH_STATUS helpers
# ---------------------------------------------------------------------------

def mme_is_idle(status: int) -> bool:
    """Check if MME is idle based on status register value."""
    busy_bits = status & 0x7F        # bits [6:0] = port/engine busy
    sm_idle = (status >> 11) & 1     # bit 11 = sync manager idle
    return busy_bits == 0 and sm_idle == 1


# ---------------------------------------------------------------------------
# Packet opcodes
# ---------------------------------------------------------------------------
PACKET_WREG_32   = 0x1
PACKET_WREG_BULK = 0x2
PACKET_MSG_LONG  = 0x3
PACKET_MSG_SHORT = 0x4
PACKET_CP_DMA    = 0x5
PACKET_MSG_PROT  = 0x7
PACKET_FENCE     = 0x8
PACKET_LIN_DMA   = 0x9
PACKET_NOP       = 0xA
PACKET_STOP      = 0xB

# LIN_DMA directions
DMA_HOST_TO_DRAM = 0
DMA_HOST_TO_SRAM = 1
DMA_DRAM_TO_SRAM = 2
DMA_DRAM_TO_DRAM = 3
DMA_SRAM_TO_HOST = 4
DMA_SRAM_TO_DRAM = 5
DMA_SRAM_TO_SRAM = 6
DMA_DRAM_TO_HOST = 7

# ---------------------------------------------------------------------------
# Device constants
# ---------------------------------------------------------------------------
DRAM_PHYS_DEFAULT_SIZE = 0x100000000   # 4 GB
CPU_FW_IMAGE_SIZE      = 0x10000000    # 256 MB
MMU_PAGE_TABLES_SIZE   = 0x0FC00000    # 252 MB
DRAM_BASE_ADDR_USER    = 0x20000000    # First usable DRAM address
PLL_HIGH_DEFAULT       = 1575000000    # 1.575 GHz
MME_QMAN_LENGTH        = 64
NUMBER_OF_EXT_HW_QUEUES = 5
NUMBER_OF_INT_HW_QUEUES = 9

# Hardware capability flags
HW_CAP_PLL       = 0x001
HW_CAP_DDR_0     = 0x002
HW_CAP_DDR_1     = 0x004
HW_CAP_MME       = 0x008
HW_CAP_CPU       = 0x010
HW_CAP_DMA       = 0x020
HW_CAP_MSIX      = 0x040
HW_CAP_CPU_Q     = 0x080
HW_CAP_MMU       = 0x100
HW_CAP_TPC_MBIST = 0x200
HW_CAP_GOLDEN    = 0x400
HW_CAP_TPC       = 0x800

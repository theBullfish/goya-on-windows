# Goya Register Map

Extracted from Linux kernel `drivers/accel/habanalabs/` (GPL source, clean-room documented).

## Device Address Space

BAR0 maps to device physical address `0x7FFC000000`. All register offsets below are relative to BAR0 base.

| BAR | Size | Maps To | Purpose |
|-----|------|---------|---------|
| BAR0 | 256 MB | SRAM + CFG | Configuration registers (MMIO) + on-chip SRAM |
| BAR2 | — | MSI-X | Interrupt vectors |
| BAR4 | 8 GB | DRAM | Device DDR4 memory (dynamically remapped via iATU) |

### iATU (Internal Address Translation Unit)
- Inbound Region 0: BAR0 → `SRAM_BASE_ADDR`
- Inbound Region 1: BAR4 → `DRAM_PHYS_BASE`
- Outbound Region: Device → Host at `HOST_PHYS_BASE`
- BAR4 can be dynamically remapped via `goya_set_ddr_bar_base()` for different DRAM ranges

### DRAM Layout

| Region | Offset | Size | Purpose |
|--------|--------|------|---------|
| Firmware | 0x00000000 | 256 MB | CPU firmware image (u-boot + Linux) |
| Page Tables | 0x10000000 | 252 MB | MMU page tables |
| Cache Mgmt | — | 4 KB | MMU cache management |
| User DRAM | 0x20000000 | ~3.5 GB | Available for user data (matrices, etc.) |

Constants:
- `DRAM_PHYS_DEFAULT_SIZE` = 0x100000000 (4 GB, HL-100-04)
- `DRAM_BASE_ADDR_USER` = 0x20000000
- `VA_DDR_SPACE_START` = 0x800000000
- `VA_DDR_SPACE_END` = 0x2000000000

---

## MME (Matrix Math Engine) — The Core Target

The MME is Goya's fixed-function matrix multiply unit. This is what we drive for inference.

### Architecture Registers (BAR0 + offset)

| Register | Offset | Purpose |
|----------|--------|---------|
| `MME_ARCH_STATUS` | 0xD0000 | Engine status (see bit fields below) |
| `MME_ARCH_A_BASE_ADDR_HIGH` | 0xD0008 | Matrix A address [63:32] |
| `MME_ARCH_B_BASE_ADDR_HIGH` | 0xD000C | Matrix B address [63:32] |
| `MME_ARCH_CIN_BASE_ADDR_HIGH` | 0xD0010 | Accumulator input [63:32] |
| `MME_ARCH_COUT_BASE_ADDR_HIGH` | 0xD0014 | Output address [63:32] |
| `MME_ARCH_BIAS_BASE_ADDR_HIGH` | 0xD0018 | Bias vector [63:32] |
| `MME_ARCH_A_BASE_ADDR_LOW` | 0xD001C | Matrix A address [31:0] |
| `MME_ARCH_B_BASE_ADDR_LOW` | 0xD0020 | Matrix B address [31:0] |
| `MME_ARCH_CIN_BASE_ADDR_LOW` | 0xD0024 | Accumulator input [31:0] |
| `MME_ARCH_COUT_BASE_ADDR_LOW` | 0xD0028 | Output address [31:0] |
| `MME_ARCH_BIAS_BASE_ADDR_LOW` | 0xD002C | Bias vector [31:0] |
| `MME_ARCH_HEADER` | 0xD0030 | Operation config (see bit fields below) |
| `MME_ARCH_KERNEL_SIZE_MINUS_1` | 0xD0034 | Convolution kernel size (4 dims × 8 bits) |
| `MME_ARCH_ASSOCIATED_DIMS_0` | 0xD0038 | Tensor dimension mapping |
| `MME_ARCH_ASSOCIATED_DIMS_1` | 0xD003C | Tensor dimension mapping (continued) |
| `MME_ARCH_COUT_SCALE` | 0xD0040 | Output scaling factor |
| `MME_ARCH_CIN_SCALE` | 0xD0044 | Input scaling factor |
| `MME_ARCH_GEMMLOWP_ZP` | 0xD0048 | Quantization zero points + ReLU + accumulator ctrl |
| `MME_ARCH_GEMMLOWP_EXPONENT` | 0xD004C | Quantization exponents + scale enables |

### MME_ARCH_HEADER Bit Fields (0xD0030)

This is the **operation descriptor** — controls what the MME does.

| Bits | Field | Description |
|------|-------|-------------|
| [4:0] | `SIGNAL_MASK` | Which sync objects to signal on completion |
| [5] | `SIGNAL_EN` | Enable completion signaling |
| [6] | `TRANS_A` | **Transpose matrix A** |
| [7] | `LOWER_A` | Lower triangular A |
| [11:8] | `ACCUM_MASK` | Accumulator selection mask (4 accumulators) |
| [12] | `LOAD_BIAS` | Load bias vector from memory |
| [13] | `LOAD_CIN` | Load Cin (accumulator input) from memory |
| [15] | `STORE_OUT` | **Store output to Cout address** |
| [16] | `ACC_LD_INC_DISABLE` | Disable accumulator load increment |
| [17] | `ADVANCE_A` | Advance A pointer after operation |
| [18] | `ADVANCE_B` | Advance B pointer after operation |
| [19] | `ADVANCE_CIN` | Advance Cin pointer after operation |
| [20] | `ADVANCE_COUT` | Advance Cout pointer after operation |
| [21] | `COMPRESSED_B` | B matrix is compressed (sparsity support?) |
| [22] | `MASK_CONV_END` | Mask convolution end signal |
| [23] | `ACC_ST_INC_DISABLE` | Disable accumulator store increment |
| [25:24] | `AB_DATA_TYPE` | **Data type for A and B matrices** (2 bits) |
| [28:26] | `CIN_DATA_TYPE` | Data type for accumulator input (3 bits) |
| [31:29] | `COUT_DATA_TYPE` | Data type for output (3 bits) |

#### Data Types (inferred from bit widths)

AB_DATA_TYPE (2 bits — 4 values):
| Value | Type (likely) |
|-------|---------------|
| 0 | FP32 |
| 1 | FP16 |
| 2 | BF16 |
| 3 | INT8 |

CIN/COUT_DATA_TYPE (3 bits — 8 values):
| Value | Type (likely) |
|-------|---------------|
| 0 | FP32 |
| 1 | FP16 |
| 2 | BF16 |
| 3 | INT8 |
| 4 | INT16 |
| 5 | INT32 |

*Note: Exact data type encoding needs validation on hardware.*

#### Minimal GEMM Header Value

For a basic FP32 A × B → Cout (no transpose, no accumulation):
```
STORE_OUT = 1 (bit 15)     = 0x8000
AB_DATA_TYPE = 0 (FP32)    = 0x0
COUT_DATA_TYPE = 0 (FP32)  = 0x0
SIGNAL_EN = 1 (bit 5)      = 0x20
SIGNAL_MASK = 0x01          = 0x01
─────────────────────────────────
Header = 0x00008021
```

### MME_ARCH_GEMMLOWP_ZP Bit Fields (0xD0048)

Hardware-level quantization AND activation support:

| Bits | Field | Description |
|------|-------|-------------|
| [8:0] | `ZP_CIN` | Zero point for Cin (9 bits, signed) |
| [17:9] | `ZP_COUT` | Zero point for Cout (9 bits, signed) |
| [26:18] | `ZP_B` | Zero point for matrix B (9 bits, signed) |
| [27] | `GEMMLOWP_EU_EN` | **Enable GEMM low-precision execution unit** |
| [28] | `ACCUM` | Use accumulator |
| [29] | `ACCUM_BIAS` | Add bias to accumulator |
| [30] | `RELU_EN` | **Enable ReLU activation in hardware!** |

### MME_ARCH_GEMMLOWP_EXPONENT Bit Fields (0xD004C)

| Bits | Field | Description |
|------|-------|-------------|
| [5:0] | `EXPONENT_CIN` | Scale exponent for Cin (6 bits) |
| [13:8] | `EXPONENT_COUT` | Scale exponent for Cout (6 bits) |
| [16] | `MUL_CIN_EN` | Enable Cin scale multiplication |
| [17] | `MUL_COUT_EN` | Enable Cout scale multiplication |

### MME_ARCH_STATUS Bit Fields (0xD0000)

| Bits | Field | Description |
|------|-------|-------------|
| [0] | `A` | Matrix A port busy |
| [1] | `B` | Matrix B port busy |
| [2] | `CIN` | Cin port busy |
| [3] | `COUT` | Cout port busy |
| [4] | `TE` | Tensor Engine busy |
| [5] | `LD` | Load unit busy |
| [6] | `ST` | Store unit busy |
| [7] | `SB_A_EMPTY` | Score buffer A empty |
| [8] | `SB_B_EMPTY` | Score buffer B empty |
| [9] | `SB_CIN_EMPTY` | Score buffer Cin empty |
| [10] | `SB_COUT_EMPTY` | Score buffer Cout empty |
| [11] | `SM_IDLE` | Sync manager idle |
| [15:12] | `WBC_AXI_IDLE` | Write-back controller AXI idle |
| [17:16] | `SBC_AXI_IDLE` | Score buffer C AXI idle |
| [19:18] | `SBB_AXI_IDLE` | Score buffer B AXI idle |
| [21:20] | `SBA_AXI_IDLE` | Score buffer A AXI idle |
| [24:22] | `FREE_ACCUMS` | Number of free accumulators |

**MME is idle when:** All busy bits [6:0] are 0, all EMPTY bits [10:7] are 1, SM_IDLE is 1.

### Control Registers

| Register | Offset | Purpose |
|----------|--------|---------|
| `MME_CMD` | 0xD0200 | **Execute command** — write 1 to bit 0 to trigger |
| `MME_DUMMY` | 0xD0204 | Dummy register (for flush) |
| `MME_RESET` | 0xD0208 | Reset engine (write 1 to bit 0) |
| `MME_STALL` | 0xD020C | Stall engine (write mask) |
| `MME_SM_BASE_ADDRESS_LOW` | 0xD0210 | Sync manager base [31:0] |
| `MME_SM_BASE_ADDRESS_HIGH` | 0xD0214 | Sync manager base [63:32] |

### Execution Unit Registers

| Register | Offset | Purpose |
|----------|--------|---------|
| `MME_STORE_MAX_CREDIT` | 0xD0300 | Store unit max credit (6 bits) |
| `MME_AGU` | 0xD0304 | Address Generation Unit credits (SBA/SBB/SBC/WBC) |
| `MME_SBA` | 0xD0308 | Score buffer A: max_size[9:0], eu_max_credit[20:16] |
| `MME_SBB` | 0xD030C | Score buffer B: max_size[9:0], eu_max_credit[20:16] |
| `MME_SBC` | 0xD0310 | Score buffer C: max_size[9:0], eu_max_credit[20:16] |
| `MME_WBC` | 0xD0314 | Write-back controller config |
| `MME_TE` | 0xD0328 | Tensor engine config |
| `MME_TE2DEC` | 0xD032C | Tensor engine to decoder config |

### Error Registers

| Register | Offset | Purpose |
|----------|--------|---------|
| `MME_REI_STATUS` | 0xD0330 | Recoverable error status |
| `MME_REI_MASK` | 0xD0334 | Recoverable error mask |
| `MME_SEI_STATUS` | 0xD0338 | Severe error status |
| `MME_SEI_MASK` | 0xD033C | Severe error mask |
| `MME_SPI_STATUS` | 0xD0340 | SPI status |
| `MME_SPI_MASK` | 0xD0344 | SPI mask |

### Shadow Registers

4 shadow register banks mirror the architecture registers:
- Shadow 0: 0xD0400 (same layout as 0xD0000)
- Shadow 1: 0xD0600
- Shadow 2: 0xD0800
- Shadow 3: 0xD0A00

Shadows allow queueing up to 4 operations while one executes.

---

## MME Queue Manager (0xD8000)

Handles packet submission to the MME.

| Register | Offset | Purpose |
|----------|--------|---------|
| `MME_QM_GLBL_CFG0` | 0xD8000 | Global config (enable) |
| `MME_QM_GLBL_CFG1` | 0xD8004 | Global config 1 |
| `MME_QM_GLBL_PROT` | 0xD8008 | Protection settings |
| `MME_QM_GLBL_ERR_CFG` | 0xD800C | Error configuration |
| `MME_QM_GLBL_ERR_ADDR_LO` | 0xD8010 | Error message address [31:0] |
| `MME_QM_GLBL_ERR_ADDR_HI` | 0xD8014 | Error message address [63:32] |
| `MME_QM_GLBL_ERR_WDATA` | 0xD8018 | Error write data |
| `MME_QM_GLBL_STS0` | 0xD8024 | Global status 0 |
| `MME_QM_GLBL_STS1` | 0xD8028 | Global status 1 |
| `MME_QM_PQ_BASE_LO` | 0xD8060 | Packet queue base [31:0] |
| `MME_QM_PQ_BASE_HI` | 0xD8064 | Packet queue base [63:32] |
| `MME_QM_PQ_SIZE` | 0xD8068 | Packet queue size (log2) |
| `MME_QM_PQ_PI` | 0xD806C | Producer index (host writes) |
| `MME_QM_PQ_CI` | 0xD8070 | Consumer index (HW reads) |
| `MME_QM_CQ_PTR_LO` | 0xD80C0 | Completion queue pointer [31:0] |
| `MME_QM_CQ_PTR_HI` | 0xD80C4 | Completion queue pointer [63:32] |
| `MME_QM_CQ_TSIZE` | 0xD80C8 | Completion transfer size |
| `MME_QM_CQ_CTL` | 0xD80CC | Completion control |
| `MME_QM_CP_MSG_BASE0_ADDR_LO` | 0xD8120 | CP message base 0 [31:0] |
| `MME_QM_CP_MSG_BASE0_ADDR_HI` | 0xD8124 | CP message base 0 [63:32] |
| `MME_QM_CP_MSG_BASE1_ADDR_LO` | 0xD8128 | CP message base 1 [31:0] |
| `MME_QM_CP_MSG_BASE1_ADDR_HI` | 0xD812C | CP message base 1 [63:32] |
| `MME_QM_CP_FENCE0_RDATA` | 0xD8158 | Fence 0 read data |
| `MME_QM_CP_STS` | 0xD8178 | Command processor status |

## MME Command Queue (0xD9000)

| Register | Offset | Purpose |
|----------|--------|---------|
| `MME_CMDQ_GLBL_CFG0` | 0xD9000 | Command queue enable |
| `MME_CMDQ_CQ_PTR_LO` | 0xD90C0 | CQ pointer low |
| `MME_CMDQ_CQ_PTR_HI` | 0xD90C4 | CQ pointer high |
| `MME_CMDQ_CQ_TSIZE` | 0xD90C8 | Transfer size |
| `MME_CMDQ_CQ_CTL` | 0xD90CC | Control |
| `MME_CMDQ_CP_FENCE0_RDATA` | 0xD9158 | Fence 0 read data |
| `MME_CMDQ_CP_STS` | 0xD9178 | Command processor status |

---

## DMA Engines (5 channels)

### Channel Base Addresses

| Channel | QM Base | CH Base | Queue ID |
|---------|---------|---------|----------|
| DMA 0 | 0x400000 | 0x401000 | `GOYA_QUEUE_ID_DMA_0` |
| DMA 1 | 0x408000 | 0x409000 | `GOYA_QUEUE_ID_DMA_1` |
| DMA 2 | 0x410000 | 0x411000 | `GOYA_QUEUE_ID_DMA_2` |
| DMA 3 | 0x418000 | 0x419000 | `GOYA_QUEUE_ID_DMA_3` |
| DMA 4 | 0x420000 | 0x421000 | `GOYA_QUEUE_ID_DMA_4` |

**Spacing:** 0x8000 between channels. `DMA_QM_n = 0x400000 + n * 0x8000`, `DMA_CH_n = 0x401000 + n * 0x8000`

### Queue Manager Registers (per channel, offsets from QM base)

| Register | Offset | Purpose |
|----------|--------|---------|
| `GLBL_CFG0` | +0x000 | Global config (enable) |
| `GLBL_CFG1` | +0x004 | Global config 1 |
| `GLBL_PROT` | +0x008 | Protection |
| `GLBL_ERR_CFG` | +0x00C | Error config |
| `GLBL_ERR_ADDR_LO` | +0x010 | Error address [31:0] |
| `GLBL_ERR_ADDR_HI` | +0x014 | Error address [63:32] |
| `GLBL_STS0` | +0x024 | Global status 0 |
| `GLBL_STS1` | +0x028 | Global status 1 |
| `PQ_BASE_LO` | +0x060 | Packet queue base [31:0] |
| `PQ_BASE_HI` | +0x064 | Packet queue base [63:32] |
| `PQ_SIZE` | +0x068 | Packet queue size (log2) |
| `PQ_PI` | +0x06C | Producer index (host writes) |
| `PQ_CI` | +0x070 | Consumer index (HW reads) |
| `PQ_CFG0` | +0x074 | PQ config 0 |
| `PQ_CFG1` | +0x078 | PQ config 1 |
| `CQ_CFG0` | +0x0B0 | CQ config 0 |
| `CQ_CFG1` | +0x0B4 | CQ config 1 |
| `CQ_PTR_LO` | +0x0C0 | Completion queue ptr [31:0] |
| `CQ_PTR_HI` | +0x0C4 | Completion queue ptr [63:32] |
| `CQ_TSIZE` | +0x0C8 | CQ transfer size |
| `CQ_CTL` | +0x0CC | CQ control |
| `CP_MSG_BASE0_ADDR_LO` | +0x120 | CP msg base 0 [31:0] |
| `CP_MSG_BASE0_ADDR_HI` | +0x124 | CP msg base 0 [63:32] |
| `CP_MSG_BASE1_ADDR_LO` | +0x128 | CP msg base 1 [31:0] |
| `CP_MSG_BASE1_ADDR_HI` | +0x12C | CP msg base 1 [63:32] |
| `CP_LDMA_TSIZE_OFFSET` | +0x140 | Local DMA transfer size offset |
| `CP_LDMA_SRC_BASE_LO_OFFSET` | +0x144 | LDMA source base low offset |
| `CP_LDMA_SRC_BASE_HI_OFFSET` | +0x148 | LDMA source base high offset |
| `CP_LDMA_DST_BASE_LO_OFFSET` | +0x14C | LDMA dest base low offset |
| `CP_LDMA_DST_BASE_HI_OFFSET` | +0x150 | LDMA dest base high offset |
| `CP_LDMA_COMMIT_OFFSET` | +0x154 | LDMA commit offset |
| `CP_FENCE0_RDATA` | +0x158 | Fence 0 read data |
| `CP_FENCE1_RDATA` | +0x15C | Fence 1 read data |
| `CP_STS` | +0x178 | Command processor status |

### DMA Channel Registers (per channel, offsets from CH base)

| Register | Offset | Purpose |
|----------|--------|---------|
| `CFG0` | +0x000 | Channel config 0 |
| `CFG1` | +0x004 | Channel config 1 |
| `ERRMSG_ADDR_LO` | +0x008 | Error message address [31:0] |
| `ERRMSG_ADDR_HI` | +0x00C | Error message address [63:32] |
| `ERRMSG_WDATA` | +0x010 | Error write data |
| `RD_COMP_ADDR_LO` | +0x014 | Read completion address [31:0] |
| `RD_COMP_ADDR_HI` | +0x018 | Read completion address [63:32] |
| `RD_COMP_WDATA` | +0x01C | Read completion write data |
| `WR_COMP_ADDR_LO` | +0x020 | Write completion address [31:0] |
| `WR_COMP_ADDR_HI` | +0x024 | Write completion address [63:32] |
| `WR_COMP_WDATA` | +0x028 | Write completion write data |
| `LDMA_SRC_ADDR_LO` | +0x02C | Local DMA source [31:0] |
| `LDMA_SRC_ADDR_HI` | +0x030 | Local DMA source [63:32] |
| `LDMA_DST_ADDR_LO` | +0x034 | Local DMA destination [31:0] |
| `LDMA_DST_ADDR_HI` | +0x038 | Local DMA destination [63:32] |
| `LDMA_TSIZE` | +0x03C | Local DMA transfer size |
| `COMIT_TRANSFER` | +0x040 | Commit transfer (trigger) |
| `STS0` | +0x044 | Status 0 |
| `STS1` | +0x048 | Status 1 |
| `RD_RATE_LIM_EN` | +0x070 | Read rate limiter enable |
| `WR_RATE_LIM_EN` | +0x080 | Write rate limiter enable |
| `CFG2` | +0x090 | Channel config 2 |

Also includes TDMA (Tensor DMA) registers at +0x100 for strided/multi-dimensional transfers.

### DMA Packet Format

```c
// Packet opcodes
PACKET_WREG_32   = 0x1   // Write single register
PACKET_WREG_BULK = 0x2   // Write multiple registers
PACKET_MSG_LONG  = 0x3   // Long message (addr + data)
PACKET_MSG_SHORT = 0x4   // Short message
PACKET_CP_DMA    = 0x5   // Command processor DMA
PACKET_MSG_PROT  = 0x7   // Protected message
PACKET_FENCE     = 0x8   // Fence (synchronization)
PACKET_LIN_DMA   = 0x9   // Linear DMA transfer
PACKET_NOP       = 0xA   // No operation
PACKET_STOP      = 0xB   // Stop execution
```

#### packet_lin_dma (24 bytes)
```c
struct packet_lin_dma {
    uint32_t tsize;      // Transfer size in bytes
    uint32_t ctl;        // Control word
    uint64_t src_addr;   // Source address
    uint64_t dst_addr;   // Destination address
};
```

Control bits for LIN_DMA:
| Bit | Field | Description |
|-----|-------|-------------|
| 0 | `WO` | Write-only |
| 1 | `RDCOMP` | Read completion |
| 2 | `WRCOMP` | Write completion |
| 6 | `MEMSET` | Memory set mode |
| [22:20] | `DMA_DIR` | DMA direction |
| [28:24] | `OPCODE` | = 0x9 (LIN_DMA) |
| 29 | `EB` | Engine barrier |
| 30 | `RB` | Register barrier |
| 31 | `MB` | Message barrier |

#### packet_wreg32 (8 bytes)
```c
struct packet_wreg32 {
    uint32_t value;      // Value to write
    uint32_t ctl;        // Control: reg_offset[15:0], opcode[28:24]=0x1
};
```

#### packet_fence (8 bytes)
```c
struct packet_fence {
    uint32_t cfg;        // Fence configuration
    uint32_t ctl;        // Control: opcode[28:24]=0x8
};
```

#### packet_msg_long (16 bytes)
```c
struct packet_msg_long {
    uint32_t value;      // Value to write
    uint32_t ctl;        // Control: opcode[28:24]=0x3
    uint64_t addr;       // Target address
};
```

DMA directions:
- `DMA_HOST_TO_DRAM` (0)
- `DMA_HOST_TO_SRAM` (1)
- `DMA_DRAM_TO_SRAM` (2)
- `DMA_DRAM_TO_DRAM` (3)
- `DMA_SRAM_TO_HOST` (4)
- `DMA_SRAM_TO_DRAM` (5)
- `DMA_SRAM_TO_SRAM` (6)
- `DMA_DRAM_TO_HOST` (7)

---

## Sync Manager

The sync manager provides hardware synchronization primitives.

| Register | Offset | Purpose |
|----------|--------|---------|
| `SYNC_MNGR_SOB_OBJ_0` | 0x112000 | Sync object 0 (1024 total) |
| `SYNC_MNGR_SOB_OBJ_1023` | 0x112FFC | Sync object 1023 |
| `SYNC_MNGR_MON_PAY_ADDRL_0` | 0x113000 | Monitor payload address low |
| `SYNC_MNGR_MON_STATUS_0` | 0x114000 | Monitor status 0 |
| `SYNC_MNGR_MON_STATUS_255` | 0x1143FC | Monitor status 255 |

Sync objects are 16-bit counters. MME signals completion by incrementing a sync object.
Monitors watch sync objects and generate interrupts/messages when conditions are met.

---

## Device Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| PLL clock (high) | 1.575 GHz | Default high-performance clock |
| Max power | 200 W | Default power limit |
| DC power | 20 W | Idle power |
| TPC enabled mask | 0xFF | All 8 TPCs |
| Max pending CS | 64 | Max command submissions in flight |
| DRAM default size | 4 GB | (HL-100-04), HL-100-08 has 8 GB |
| CPU FW image size | 256 MB | Firmware region in DRAM |
| MMU page tables | 252 MB | Reserved for page tables |
| QMAN fence timeout | 10 ms | |
| QMAN stop timeout | 100 ms | |
| CPU timeout | 15 s | |
| Completion queues | 5 | One per DMA channel |
| External HW queues | 5 | DMA channels |
| Internal HW queues | 9 | MME + TPC queues |
| MME QMAN length | 64 | Entries in MME queue |

## Hardware Capability Flags

| Flag | Value | Component |
|------|-------|-----------|
| `HW_CAP_PLL` | 0x001 | Phase-locked loops |
| `HW_CAP_DDR_0` | 0x002 | DDR channel 0 |
| `HW_CAP_DDR_1` | 0x004 | DDR channel 1 |
| `HW_CAP_MME` | 0x008 | Matrix Math Engine |
| `HW_CAP_CPU` | 0x010 | On-chip CPU |
| `HW_CAP_DMA` | 0x020 | DMA engines |
| `HW_CAP_MSIX` | 0x040 | MSI-X interrupts |
| `HW_CAP_CPU_Q` | 0x080 | CPU queue |
| `HW_CAP_MMU` | 0x100 | Memory management unit |
| `HW_CAP_TPC_MBIST` | 0x200 | TPC memory BIST |
| `HW_CAP_GOLDEN` | 0x400 | Golden registers |
| `HW_CAP_TPC` | 0x800 | Tensor processing cores |

---

## The Path to a Matrix Multiply

Based on the complete register map, a minimal GEMM on the MME requires:

### Step 1: DMA — Host → DRAM
Submit `packet_lin_dma` to DMA channel 0:
- `tsize` = matrix size in bytes
- `ctl` = opcode 0x9, direction `DMA_HOST_TO_DRAM`
- `src_addr` = host physical address
- `dst_addr` = DRAM address (≥ 0x20000000 to skip firmware region)

### Step 2: MME Setup — Write Architecture Registers
Either via direct MMIO writes or via `packet_wreg32` through the MME queue:
- `MME_ARCH_A_BASE_ADDR` → DRAM address of matrix A
- `MME_ARCH_B_BASE_ADDR` → DRAM address of matrix B
- `MME_ARCH_COUT_BASE_ADDR` → DRAM address for result
- `MME_ARCH_HEADER` → 0x00008021 for basic FP32 GEMM
- `MME_ARCH_ASSOCIATED_DIMS` → matrix dimensions
- `MME_ARCH_KERNEL_SIZE_MINUS_1` → 0 for GEMM (no convolution)

### Step 3: Execute
Write 1 to `MME_CMD` (0xD0200) to trigger.

### Step 4: Wait for Completion
Poll `MME_ARCH_STATUS` (0xD0000):
- Idle when bits [6:0] = 0 and `SM_IDLE` = 1
- Or use sync manager: MME signals sync object, monitor generates interrupt

### Step 5: DMA — DRAM → Host
Submit `packet_lin_dma` to DMA channel:
- Direction = `DMA_DRAM_TO_HOST`
- `src_addr` = DRAM address of result
- `dst_addr` = host physical address

### For INT8 Quantized Inference (bonus)
Add to Step 2:
- `MME_ARCH_HEADER` → set `AB_DATA_TYPE` = 3 (INT8)
- `MME_ARCH_GEMMLOWP_ZP` → set zero points + `GEMMLOWP_EU_EN` + `RELU_EN`
- `MME_ARCH_GEMMLOWP_EXPONENT` → set scale exponents + `MUL_COUT_EN`

This gives hardware-accelerated: `ReLU(scale * (A_int8 × B_int8 + bias) + zero_point)`

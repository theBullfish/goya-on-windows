# Goya Initialization Sequence

Derived from `goya_hw_init()` in Linux `drivers/accel/habanalabs/goya/goya.c`.

## Full Init Sequence (Linux driver)

```
goya_hw_init()
├── 1. Read device status register (readiness check)
├── 2. Set HW_STATE = DIRTY
├── 3. goya_init_cpu()           → Load firmware, start ARM CPU
├── 4. TPC MBIST workaround      → Memory built-in self-test fix
├── 5. Golden register init       → Write optimal register values
├── 6. DDR BAR remap             → Point BAR4 at MMU page tables
├── 7. goya_mmu_init()           → Configure MMU for address translation
├── 8. Security init              → Protection and access control
├── 9. goya_init_dma_qmans()     → Enable all 5 DMA channels
├── 10. goya_init_mme_qmans()    → Enable MME queue manager
├── 11. goya_init_tpc_qmans()    → Enable TPC queue managers
├── 12. Timestamp enable          → Performance counters
├── 13. MSI-X setup               → Interrupt vectors
└── Set HW_STATE = RUNNING
```

## Firmware Question

**Is firmware required for MME-only operation?**

The Linux driver loads two firmware files:
- `GOYA_BOOT_FIT_FILE` — U-Boot bootloader
- `GOYA_LINUX_FW_FILE` — Embedded Linux for the on-chip ARM CPU

The firmware runs on the **ARM Cortex-A53 CPU** embedded in the Goya SoC. It handles:
- DDR4 memory controller initialization and training
- PLL configuration
- Power management
- Thermal monitoring
- Communication with host via CPU queue

**Critical finding:** The DDR4 controller is initialized by firmware. Without it, DRAM is unusable. The MME reads/writes to DRAM, so **firmware is required** even for MME-only operation.

However: The MME itself and the DMA engines are configured by the host driver through MMIO, not by firmware. The firmware's role is limited to low-level hardware init (clocks, DDR training).

### Implications for Windows

We need to either:
1. **Load the Linux firmware** — The ARM CPU runs its own embedded Linux, independent of the host OS. This should work from Windows.
2. **Use SRAM only** — Goya has on-chip SRAM (mapped via BAR0) that doesn't need DDR training. Limited size but could work for small matrices as a proof of concept.
3. **Pre-initialize from Linux** — Boot Linux, let firmware init DRAM, then warm-reboot into Windows. Hacky but possible for validation.

**Recommended approach:** Option 1 (load firmware from Windows). The firmware loading is just DMA to specific DRAM addresses + ARM CPU boot sequence. Host OS doesn't matter.

## DMA Queue Manager Init Sequence

From `goya_init_dma_qman()` — repeated for each of 5 channels:

```
For each DMA channel n (0-4):
  1. Set completion queue ID for this channel
  2. Set MSI-X vector number

  goya_init_dma_qman(n):
    3. Write PQ_BASE_LO/HI  → Physical address of packet queue buffer
    4. Write PQ_SIZE          → ilog2(queue_length)
    5. Write PQ_PI = 0        → Reset producer index
    6. Write PQ_CI = 0        → Reset consumer index
    7. Write CP_LDMA offsets  → Configure local DMA for command processor
    8. Write CP_MSG_BASE0     → Sync manager SOB base address
    9. Write CP_MSG_BASE1     → Sync manager monitor base address
    10. Write CQ_CFG0         → 0x00080008 (cache line config)
    11. Write GLBL_ERR_CFG    → Error handling setup
    12. Write GLBL_ERR_ADDR   → Error message destination
    13. Write GLBL_ERR_WDATA  → Error message data
    14. Write GLBL_PROT       → Protection settings
    15. Write GLBL_CFG0       → Enable the queue manager

  goya_init_dma_ch(n):
    16. Write CH_CFG0/CFG1    → Channel configuration
    17. Write rate limiters    → Optional bandwidth control
    18. Write completion addrs → Where to write DMA done notifications

  19. Set HW_CAP_DMA flag
```

## MME Queue Manager Init Sequence

From `goya_init_mme_qman()`:

```
goya_init_mme_qmans():
  1. Write PQ_BASE_LO/HI    → Physical address of MME packet queue
  2. Write PQ_SIZE           → ilog2(MME_QMAN_LENGTH) = ilog2(64) = 6
  3. Write PQ_PI = 0
  4. Write PQ_CI = 0
  5. Write CP_LDMA offsets   → Local DMA config for command processor
  6. Write CP_MSG_BASE0      → mmSYNC_MNGR_SOB_OBJ_0 (0x112000)
  7. Write CP_MSG_BASE1      → mmSYNC_MNGR_MON_PAY_ADDRL_0 (0x113000)
  8. Write CQ_CFG0           → 0x00080008
  9. Write GLBL_ERR_CFG      → Error handling
  10. Write GLBL_ERR_ADDR/WDATA
  11. Write GLBL_PROT        → Protection
  12. Write GLBL_CFG0        → Enable
  13. Set HW_CAP_MME flag
```

## Minimum Init Path (MME + DMA)

For our Windows driver, the minimum sequence to get a matrix multiply working:

```
Phase A: Hardware Ready
  1. Map BAR0, BAR2, BAR4 via PCIe
  2. Read PCIE_DBI_DEVICE_ID_VENDOR_ID_REG (0xC02000) → verify 0x00011DA3

Phase B: Firmware + DDR
  3. Load firmware to DRAM via BAR4
  4. Boot ARM CPU
  5. Wait for CPU ready (poll status, up to 15s timeout)
  6. DDR4 training completes (firmware handles this)

Phase C: DMA Init
  7. Allocate packet queue buffers in host memory (DMA-able)
  8. goya_init_dma_qman(0) — at minimum, init one DMA channel

Phase D: MME Init
  9. goya_init_mme_qmans() — enable MME queue
  10. Write MME_SM_BASE_ADDRESS → sync manager base

Phase E: Ready for GEMM
  11. DMA matrices host → DRAM
  12. Write MME architecture registers (or submit via queue)
  13. Trigger MME_CMD
  14. Poll for completion
  15. DMA result DRAM → host
```

## Shutdown Sequence

From `goya_hw_fini()`:

### Soft Reset
```
1. Write DMA_MME_TPC_RESET → Reset compute engines
2. Clear HW_CAP flags for DMA, MME, TPC
3. Clear event statistics
```

### Hard Reset
```
1. Send CPU halt command
2. Wait for CPU (100ms normal, 1000ms PLDM)
3. Reset DDR BAR to DRAM base
4. Disable clock relaxation
5. Set PLL to reference clock
6. Write RESET_ALL command
7. Wait for BTM FSM completion
```

## Key Insight: Direct Register Path

For initial bring-up and validation, we can **skip the queue managers entirely** and write MME registers directly via BAR0 MMIO:

1. Write `MME_ARCH_*` registers directly (they're just BAR0 + 0xD0xxx)
2. Write `MME_CMD` = 1 to execute
3. Poll `MME_ARCH_STATUS` for idle

This avoids the complexity of packet queues for the first proof of concept. Queue-based submission (via WREG32 packets) is needed for production performance (pipelining, shadow registers) but not for first light.

Similarly, for DMA, we can use the channel's **local DMA** registers directly:
1. Write `DMA_CH_n_LDMA_SRC_ADDR` = host address
2. Write `DMA_CH_n_LDMA_DST_ADDR` = DRAM address
3. Write `DMA_CH_n_LDMA_TSIZE` = byte count
4. Write `DMA_CH_n_COMIT_TRANSFER` = 1
5. Poll `DMA_CH_n_STS0` for completion

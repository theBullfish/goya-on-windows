# Linux habanalabs Driver — Reading Notes

## Source Location

Mainline Linux kernel: `drivers/accel/habanalabs/`

### Key Files for Goya

| File | Purpose |
|------|---------|
| `goya/goya.c` | Main Goya driver — init, reset, GEMM, DMA |
| `goya/goyaP.h` | Private definitions, register offsets, constants |
| `goya/goya_hwmgr.c` | Clock, power, thermal management |
| `goya/goya_coresight.c` | Debug/trace infrastructure |
| `common/habanalabs.h` | Shared types and structures |
| `common/habanalabs_drv.c` | PCI probe, BAR mapping |
| `common/command_buffer.c` | Command buffer management |
| `common/dma_pool.c` | DMA memory pools |
| `common/hw_queue.c` | Hardware queue submission |
| `common/irq.c` | Interrupt handling |
| `include/goya/asic_reg/goya_blocks.h` | Block base addresses (device physical) |
| `include/goya/asic_reg/goya_regs.h` | Master include for all register headers |
| `include/goya/asic_reg/mme_regs.h` | MME register offsets |
| `include/goya/asic_reg/mme_masks.h` | MME register bit field masks |
| `include/goya/asic_reg/dma_ch_0_regs.h` | DMA channel registers |
| `include/goya/asic_reg/dma_qm_0_regs.h` | DMA queue manager registers |
| `include/goya/goya_packets.h` | Packet structures and opcodes |

### Questions — ANSWERED

- [x] **Can the MME operate without loading TPC firmware?**
  YES — the MME and TPCs are independent. TPC firmware is only needed for TPC kernels. However, **DDR4 firmware IS required** because the ARM CPU firmware initializes the DDR memory controller. Without DDR, the MME has nowhere to read/write matrices.

- [x] **What is the minimum init sequence to get DMA + MME working?**
  See `docs/init-sequence.md`. Short version: firmware load → DDR ready → init one DMA QMAN → init MME QMAN → ready.

- [x] **How are GEMM descriptors structured?**
  They're **MME architecture registers**, not a descriptor struct. Write addresses (A, B, Cin, Cout, Bias), header (data type, transpose, store/load flags), dimensions, and quantization params to registers at 0xD0000-0xD004C. Then write 1 to MME_CMD at 0xD0200.

- [x] **Is there a command queue or is it direct register writes?**
  BOTH. Architecture registers can be written directly via BAR0 MMIO. For production, use the QMAN: submit WREG32 packets that write to registers, allowing pipelining via 4 shadow register banks.

- [x] **What interrupts are needed vs. can we poll?**
  Polling works fine. Poll `MME_ARCH_STATUS` for idle (bits [6:0] = 0, SM_IDLE = 1). For production, use sync objects — MME increments a sync object on completion, a monitor can generate an MSI-X interrupt.

- [x] **How is device memory addressed from MME descriptors?**
  MME uses device physical addresses. DRAM starts at the device's DRAM base. User-accessible DRAM starts at offset 0x20000000 (after firmware + page table regions). When MMU is enabled, virtual addresses are used instead.

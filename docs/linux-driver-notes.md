# Linux habanalabs Driver — Reading Notes

## Source Location

Mainline Linux kernel: `drivers/accel/habanalabs/`

### Key Files for Goya

| File | Purpose |
|------|---------|
| `goya/goya.c` | Main Goya driver — init, reset, GEMM, DMA |
| `goya/goyaP.h` | Private definitions, register offsets |
| `goya/goya_hwmgr.c` | Clock, power, thermal management |
| `goya/goya_coresight.c` | Debug/trace infrastructure |
| `common/habanalabs.h` | Shared types and structures |
| `common/habanalabs_drv.c` | PCI probe, BAR mapping |
| `common/command_buffer.c` | Command buffer management |
| `common/dma_pool.c` | DMA memory pools |
| `common/hw_queue.c` | Hardware queue submission |
| `common/irq.c` | Interrupt handling |
| `include/gaudi/asic_reg/` | Register definitions (shared with Gaudi) |

### What to Extract

1. **`goya_hw_init()`** — Full initialization sequence
2. **`goya_dma_*`** — DMA channel setup and descriptor format
3. **GEMM submission** — How matrices are submitted to the GEMM engine
4. **Memory management** — How DDR4 DRAM is mapped and managed
5. **Firmware loading** — Is firmware required? What format?
6. **Error handling** — How hardware errors are detected and recovered

### Questions to Answer

- [ ] Can the GEMM engine operate without loading TPC firmware?
- [ ] What is the minimum init sequence to get DMA + GEMM working?
- [ ] How are GEMM descriptors structured? (dimensions, addresses, precision)
- [ ] Is there a command queue or is it direct register writes?
- [ ] What interrupts are needed vs. can we poll for completion?
- [ ] How is device memory (DDR4) addressed from GEMM descriptors?

## Notes

*This document will be populated as we read through the driver source.*

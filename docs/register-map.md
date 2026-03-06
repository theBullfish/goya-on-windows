# Goya Register Map

Reference: Linux kernel `drivers/accel/habanalabs/goya/`

## PCIe BARs

| BAR | Size | Purpose |
|-----|------|---------|
| BAR0 | 16 MB | Configuration registers (MMIO) |
| BAR2 | 8 GB | DRAM (device memory) |
| BAR4 | 32 MB | SRAM (on-chip scratchpad) |

## Key Register Blocks (BAR0 offsets)

*TODO: Extract from `goya/goya.c` and `include/gaudi/asic_reg/`*

### Device Identity
- `0x0000` — Device ID / Revision
- *More TBD from driver source*

### GEMM Engine
- *TODO: Find GEMM engine base address and descriptor format*
- *Look for: matrix descriptor submission, completion status, precision select*

### DMA Engines (5 channels)
- *TODO: DMA descriptor ring base, head/tail pointers, status*
- *Look for: `goya_dma_*` functions in driver source*

### TPC (for reference, not initial target)
- 8 TPC units, each with VLIW-4 pipeline
- *Not needed for GEMM-only path*

## Device Initialization Sequence

*TODO: Extract from `goya_hw_init()` in `goya/goya.c`*

1. PCIe link training / BAR mapping
2. Clock configuration
3. Memory controller init (DDR4)
4. Firmware load (if required)
5. DMA engine init
6. GEMM engine init
7. Device ready

## Notes

- All register offsets and sequences will be extracted from the GPL Linux driver source
- This document will be updated as we read through the driver code

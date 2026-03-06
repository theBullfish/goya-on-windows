# Goya-on-Windows

Direct hardware driver for Habana Goya HL-1000 on Windows. Bypasses SynapseAI entirely.

## Goal
Drive the Goya's GEMM engine via PCIe BAR access on Windows for matrix multiply inference.

## Architecture
- `docs/` — Register maps, Linux driver reading notes, hardware documentation
- `src/` — Driver code (Python + C where needed)
- `tests/` — Hardware validation tests

## Key Constraint
All register maps and init sequences derived from GPL Linux kernel driver (`drivers/accel/habanalabs/goya/`). This project is MIT-licensed — we implement our own code based on publicly documented hardware behavior, not copy GPL code.

## Hardware
- PCI VEN_1DA3 DEV_0001 (Habana Goya HL-1000)
- 8 GB DDR4, 8 TPCs, GEMM engine, 5 DMA channels
- PCIe Gen3 (x4 over USB4 or x16 native)

## Related
- D:\mde — MDE runtime (will consume this as HabanaDirectSession)
- github.com/theBullfish/goya-bringup — SPI flash tools

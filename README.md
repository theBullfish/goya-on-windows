# Goya-on-Windows

Direct hardware access to Habana Goya HL-1000 inference accelerators on Windows — no SynapseAI, no Linux.

## Why This Exists

Habana's SynapseAI software stack is Linux-only. But the hardware doesn't care what OS it runs under. The Linux kernel driver (`drivers/accel/habanalabs/`) is open source GPL, documenting every register, every DMA descriptor, every initialization sequence.

This project bypasses SynapseAI entirely and drives the Goya's fixed-function **GEMM engine** directly via PCIe BAR access on Windows.

## Hardware Target

- **Habana Goya HL-1000** (Intel/Habana Labs inference ASIC)
- PCI Vendor: `1DA3`, Device: `0001`
- 8 Tensor Processor Cores (VLIW-4) + dedicated GEMM engine
- 5 DMA channels for host ↔ device data transfer
- 8 GB DDR4 on-card memory, 40 GB/s bandwidth
- PCIe Gen3 interface (x4 over USB4 tunneling, or x16 native)

## Strategy

We don't need the full SynapseAI stack. For matrix-multiply inference workloads, the Goya has a **fixed-function GEMM engine** that requires no TPC kernel compilation. The path:

1. **Map PCIe BARs** — BAR0 (config registers), BAR2 (DRAM), BAR4 (SRAM)
2. **Initialize device** — clock setup, memory controller, firmware load
3. **Configure DMA** — set up host ↔ device data channels
4. **Submit GEMM descriptors** — matrix addresses, dimensions, precision, output location
5. **Read results** — DMA output back to host

## Architecture

```
┌─────────────────────────────────────────┐
│  MDE (Model Decomposition Engine)       │
│  Assignment Engine routes matmuls       │
│  to Goya via HabanaDirectSession        │
├─────────────────────────────────────────┤
│  goya-on-windows                        │
│  ┌───────────┐  ┌────────────────────┐  │
│  │ Windows   │  │ GEMM Engine Driver │  │
│  │ PCIe/BAR  │──│ Init → DMA → GEMM │  │
│  │ Access    │  │ → Result Readback  │  │
│  └───────────┘  └────────────────────┘  │
├─────────────────────────────────────────┤
│  Habana Goya HL-1000 (PCIe)            │
│  8x TPC │ GEMM Engine │ 5x DMA │ 8GB  │
└─────────────────────────────────────────┘
```

## Project Phases

### Phase 1: Reverse Engineering
- [ ] Read Linux `habanalabs` driver source (`goya/goya.c`, `goyaP.h`)
- [ ] Document PCIe BAR register map
- [ ] Document GEMM engine descriptor format
- [ ] Document device initialization sequence
- [ ] Document DMA engine configuration

### Phase 2: Windows BAR Access
- [ ] Map Goya PCIe BARs from Windows (UMDF2 or userspace)
- [ ] Read device identification registers
- [ ] Verify BAR layout matches Linux driver docs

### Phase 3: Device Initialization
- [ ] Implement clock and power sequencing
- [ ] Initialize memory controller (DDR4)
- [ ] Load firmware (if required for GEMM-only path)
- [ ] Validate device health registers

### Phase 4: DMA Engine
- [ ] Configure DMA channels for host → device transfers
- [ ] Implement scatter-gather descriptor rings
- [ ] Test data round-trip: host → DRAM → host
- [ ] Measure achieved bandwidth vs theoretical 3.94 GB/s

### Phase 5: GEMM Engine
- [ ] Decode GEMM descriptor format from Linux driver
- [ ] Submit first matrix multiply (small, known result)
- [ ] Validate correctness against CPU reference
- [ ] Benchmark: throughput vs matrix size
- [ ] Support FP32, FP16, BF16, INT8 precisions

### Phase 6: MDE Integration
- [ ] Create `HabanaDirectSession` in MDE's device_session framework
- [ ] Wire into assignment engine for expert dispatch
- [ ] Real TCQ calibration (measured, not spec-estimated)
- [ ] Multi-card support (6x Goya)

## Reference Material

- Linux kernel driver: `drivers/accel/habanalabs/goya/`
- [Habana Goya whitepaper](https://habana.ai/training/goya/)
- PCI Vendor ID `1DA3` (Habana Labs Ltd.)
- PCI Device ID `0001` (HL-1000 Goya inference ASIC)

## Related Projects

- [MDE](https://github.com/theBullfish/mde) — Model Decomposition Engine (the runtime that will use this)
- [goya-bringup](https://github.com/theBullfish/goya-bringup) — SPI flash tools and bringup utilities

## License

MIT

---

*Codex Labs LLC*

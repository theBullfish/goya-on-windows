"""Goya hardware probe — detect and report device status.

Usage:
    python -m goya.probe
"""

from __future__ import annotations

import sys

from . import regs
from .pci import find_goya_devices, SimBARAccessor, BARAccessor


def probe_bar(bar: BARAccessor) -> dict:
    """Read key registers and return device info dict."""
    info = {}

    # Device ID
    vid_did = bar.read32(regs.PCIE_DBI_DEVICE_ID_VENDOR_ID_REG)
    info["vendor_id"] = vid_did & 0xFFFF
    info["device_id"] = (vid_did >> 16) & 0xFFFF
    info["vid_did_raw"] = f"0x{vid_did:08X}"

    is_goya = (
        info["vendor_id"] == regs.PCIE_VENDOR_ID
        and info["device_id"] == regs.PCIE_DEVICE_ID
    )
    info["is_goya"] = is_goya

    if not is_goya:
        return info

    # MME status
    mme_status = bar.read32(regs.MME_ARCH_STATUS)
    info["mme_status_raw"] = f"0x{mme_status:08X}"
    info["mme_idle"] = regs.mme_is_idle(mme_status)
    info["mme_a_busy"] = bool(mme_status & 0x01)
    info["mme_b_busy"] = bool(mme_status & 0x02)
    info["mme_cin_busy"] = bool(mme_status & 0x04)
    info["mme_cout_busy"] = bool(mme_status & 0x08)
    info["mme_te_busy"] = bool(mme_status & 0x10)
    info["mme_ld_busy"] = bool(mme_status & 0x20)
    info["mme_st_busy"] = bool(mme_status & 0x40)
    info["mme_free_accums"] = (mme_status >> 22) & 0x7

    # MME error status
    rei = bar.read32(regs.MME_REI_STATUS)
    sei = bar.read32(regs.MME_SEI_STATUS)
    info["mme_recoverable_errors"] = f"0x{rei:08X}"
    info["mme_severe_errors"] = f"0x{sei:08X}"

    # MME QM status
    qm_sts0 = bar.read32(regs.MME_QM_GLBL_STS0)
    qm_sts1 = bar.read32(regs.MME_QM_GLBL_STS1)
    info["mme_qm_status0"] = f"0x{qm_sts0:08X}"
    info["mme_qm_status1"] = f"0x{qm_sts1:08X}"

    # DMA channel 0 status
    dma_ch0_sts = bar.read32(regs.dma_ch_base(0) + regs.DMA_CH_STS0)
    info["dma_ch0_status"] = f"0x{dma_ch0_sts:08X}"

    return info


def print_probe(info: dict, prefix: str = "") -> None:
    """Pretty-print probe results."""
    print(f"{prefix}Device ID: {info['vid_did_raw']}")
    print(f"{prefix}  Vendor: 0x{info['vendor_id']:04X} ({'Habana Labs' if info['vendor_id'] == 0x1DA3 else 'Unknown'})")
    print(f"{prefix}  Device: 0x{info['device_id']:04X} ({'Goya HL-1000' if info['device_id'] == 0x0001 else 'Unknown'})")

    if not info.get("is_goya"):
        print(f"{prefix}  Not a Goya device, skipping detailed probe.")
        return

    print(f"{prefix}MME Status: {info['mme_status_raw']}")
    if info["mme_idle"]:
        print(f"{prefix}  MME is IDLE (ready for work)")
    else:
        busy = []
        if info["mme_a_busy"]:   busy.append("A-port")
        if info["mme_b_busy"]:   busy.append("B-port")
        if info["mme_cin_busy"]: busy.append("Cin")
        if info["mme_cout_busy"]: busy.append("Cout")
        if info["mme_te_busy"]:  busy.append("TensorEngine")
        if info["mme_ld_busy"]:  busy.append("Load")
        if info["mme_st_busy"]:  busy.append("Store")
        print(f"{prefix}  MME BUSY: {', '.join(busy)}")
    print(f"{prefix}  Free accumulators: {info['mme_free_accums']}")
    print(f"{prefix}  Recoverable errors: {info['mme_recoverable_errors']}")
    print(f"{prefix}  Severe errors: {info['mme_severe_errors']}")
    print(f"{prefix}MME Queue Manager: STS0={info['mme_qm_status0']} STS1={info['mme_qm_status1']}")
    print(f"{prefix}DMA Channel 0: STS={info['dma_ch0_status']}")


def main() -> None:
    print("=" * 60)
    print("  Goya HL-1000 Hardware Probe")
    print("  goya-on-windows")
    print("=" * 60)
    print()

    # Step 1: PCI enumeration
    print("[1] Scanning PCI bus for Habana devices (VEN_1DA3)...")
    try:
        devices = find_goya_devices()
    except Exception as e:
        print(f"  PCI enumeration failed: {e}")
        devices = []

    if devices:
        print(f"  Found {len(devices)} Goya device(s):")
        for i, dev in enumerate(devices):
            print(f"    [{i}] {dev}")
    else:
        print("  No Goya devices found on PCI bus.")

    print()

    # Step 2: Simulated BAR probe (always works, for validation)
    print("[2] Simulated BAR probe (testing register logic)...")
    with SimBARAccessor() as sim:
        info = probe_bar(sim)
        print_probe(info, prefix="  ")

    print()

    # Step 3: Real BAR access (requires KMDF driver)
    if devices:
        print("[3] Real BAR access...")
        print("  KMDF driver not yet installed.")
        print("  To proceed, we need the goya_bar.sys kernel driver.")
        print("  See docs/init-sequence.md for the BAR access strategy.")
    else:
        print("[3] Skipping real BAR access (no devices found).")

    print()
    print("Probe complete.")


if __name__ == "__main__":
    main()

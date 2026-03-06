/*
 * goya_bar.h — Goya BAR Access Driver (KMDF)
 *
 * Minimal kernel driver that claims Habana Goya PCI device and
 * exposes BAR0 register read/write to userspace via IOCTLs.
 *
 * MIT License — Codex Labs LLC
 */

#pragma once

#include <ntddk.h>
#include <wdf.h>

/* Habana Goya PCI IDs */
#define GOYA_VENDOR_ID  0x1DA3
#define GOYA_DEVICE_ID  0x0001

/* IOCTL definitions */
#define FILE_DEVICE_GOYA  0x8000

#define IOCTL_GOYA_READ32  CTL_CODE(FILE_DEVICE_GOYA, 0x800, METHOD_BUFFERED, FILE_READ_ACCESS)
#define IOCTL_GOYA_WRITE32 CTL_CODE(FILE_DEVICE_GOYA, 0x801, METHOD_BUFFERED, FILE_WRITE_ACCESS)
#define IOCTL_GOYA_GET_BAR_INFO CTL_CODE(FILE_DEVICE_GOYA, 0x802, METHOD_BUFFERED, FILE_READ_ACCESS)

/* IOCTL input/output structures */
#pragma pack(push, 1)

typedef struct _GOYA_READ32_IN {
    ULONG BarIndex;     /* Which BAR (0, 2, or 4) */
    ULONG Offset;       /* Register offset within BAR */
} GOYA_READ32_IN, *PGOYA_READ32_IN;

typedef struct _GOYA_READ32_OUT {
    ULONG Value;        /* Register value */
} GOYA_READ32_OUT, *PGOYA_READ32_OUT;

typedef struct _GOYA_WRITE32_IN {
    ULONG BarIndex;     /* Which BAR (0, 2, or 4) */
    ULONG Offset;       /* Register offset within BAR */
    ULONG Value;        /* Value to write */
} GOYA_WRITE32_IN, *PGOYA_WRITE32_IN;

typedef struct _GOYA_BAR_INFO {
    ULONG BarCount;
    struct {
        ULONGLONG PhysicalAddress;
        ULONGLONG Length;
        BOOLEAN IsMapped;
    } Bars[6];
} GOYA_BAR_INFO, *PGOYA_BAR_INFO;

#pragma pack(pop)

/* Maximum BAR0 size we'll map (256 MB) */
#define GOYA_BAR0_MAX_SIZE  (256 * 1024 * 1024)

/* Device context */
typedef struct _GOYA_DEVICE_CONTEXT {
    WDFDEVICE       Device;
    BUS_INTERFACE_STANDARD BusInterface;

    /* BAR mappings */
    struct {
        PHYSICAL_ADDRESS PhysAddr;
        PVOID            VirtAddr;
        ULONG            Length;
        BOOLEAN          Mapped;
    } Bar[6];

} GOYA_DEVICE_CONTEXT, *PGOYA_DEVICE_CONTEXT;

WDF_DECLARE_CONTEXT_TYPE_WITH_NAME(GOYA_DEVICE_CONTEXT, GoyaGetDeviceContext)

/* Function declarations */
DRIVER_INITIALIZE DriverEntry;
EVT_WDF_DRIVER_DEVICE_ADD GoyaEvtDeviceAdd;
EVT_WDF_DEVICE_PREPARE_HARDWARE GoyaEvtDevicePrepareHardware;
EVT_WDF_DEVICE_RELEASE_HARDWARE GoyaEvtDeviceReleaseHardware;
EVT_WDF_IO_QUEUE_IO_DEVICE_CONTROL GoyaEvtIoDeviceControl;

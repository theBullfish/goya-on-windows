/*
 * goya_bar.c — Goya BAR Access Driver (KMDF)
 *
 * Minimal kernel driver that:
 * 1. Claims Habana Goya PCI device (VEN_1DA3 DEV_0001)
 * 2. Maps BAR0 (config registers + SRAM) into kernel virtual address space
 * 3. Exposes IOCTL_READ32 / IOCTL_WRITE32 for userspace BAR access
 *
 * This is the thinnest possible driver — all intelligence lives in
 * the userspace Python code (goya.pci.KMDFBARAccessor).
 *
 * MIT License — Codex Labs LLC
 */

#include "goya_bar.h"

#ifdef ALLOC_PRAGMA
#pragma alloc_text(INIT, DriverEntry)
#pragma alloc_text(PAGE, GoyaEvtDeviceAdd)
#pragma alloc_text(PAGE, GoyaEvtDevicePrepareHardware)
#pragma alloc_text(PAGE, GoyaEvtDeviceReleaseHardware)
#endif

/* -----------------------------------------------------------------------
 * Driver Entry
 * ----------------------------------------------------------------------- */

NTSTATUS
DriverEntry(
    _In_ PDRIVER_OBJECT  DriverObject,
    _In_ PUNICODE_STRING RegistryPath
)
{
    WDF_DRIVER_CONFIG config;
    NTSTATUS status;

    KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
        "GoyaBAR: DriverEntry\n"));

    WDF_DRIVER_CONFIG_INIT(&config, GoyaEvtDeviceAdd);

    status = WdfDriverCreate(
        DriverObject,
        RegistryPath,
        WDF_NO_OBJECT_ATTRIBUTES,
        &config,
        WDF_NO_HANDLE
    );

    if (!NT_SUCCESS(status)) {
        KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_ERROR_LEVEL,
            "GoyaBAR: WdfDriverCreate failed 0x%x\n", status));
    }

    return status;
}

/* -----------------------------------------------------------------------
 * Device Add — called when PnP finds our device
 * ----------------------------------------------------------------------- */

NTSTATUS
GoyaEvtDeviceAdd(
    _In_ WDFDRIVER       Driver,
    _Inout_ PWDFDEVICE_INIT DeviceInit
)
{
    NTSTATUS status;
    WDFDEVICE device;
    WDF_OBJECT_ATTRIBUTES deviceAttributes;
    WDF_PNPPOWER_EVENT_CALLBACKS pnpPowerCallbacks;
    WDF_IO_QUEUE_CONFIG ioQueueConfig;
    WDFQUEUE queue;
    DECLARE_CONST_UNICODE_STRING(deviceName, L"\\Device\\GoyaBAR");
    DECLARE_CONST_UNICODE_STRING(symbolicLink, L"\\DosDevices\\GoyaBAR");

    UNREFERENCED_PARAMETER(Driver);
    PAGED_CODE();

    KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
        "GoyaBAR: DeviceAdd\n"));

    /* Set PnP power callbacks */
    WDF_PNPPOWER_EVENT_CALLBACKS_INIT(&pnpPowerCallbacks);
    pnpPowerCallbacks.EvtDevicePrepareHardware = GoyaEvtDevicePrepareHardware;
    pnpPowerCallbacks.EvtDeviceReleaseHardware = GoyaEvtDeviceReleaseHardware;
    WdfDeviceInitSetPnpPowerEventCallbacks(DeviceInit, &pnpPowerCallbacks);

    /* Create named device object */
    status = WdfDeviceInitAssignName(DeviceInit, &deviceName);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    /* Allow userspace access */
    WdfDeviceInitSetIoType(DeviceInit, WdfDeviceIoBuffered);

    /* Create device with context */
    WDF_OBJECT_ATTRIBUTES_INIT_CONTEXT_TYPE(&deviceAttributes, GOYA_DEVICE_CONTEXT);
    status = WdfDeviceCreate(&DeviceInit, &deviceAttributes, &device);
    if (!NT_SUCCESS(status)) {
        KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_ERROR_LEVEL,
            "GoyaBAR: WdfDeviceCreate failed 0x%x\n", status));
        return status;
    }

    /* Create symbolic link for userspace (\\.\GoyaBAR) */
    status = WdfDeviceCreateSymbolicLink(device, &symbolicLink);
    if (!NT_SUCCESS(status)) {
        KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_ERROR_LEVEL,
            "GoyaBAR: Symbolic link creation failed 0x%x\n", status));
        return status;
    }

    /* Initialize device context */
    PGOYA_DEVICE_CONTEXT ctx = GoyaGetDeviceContext(device);
    ctx->Device = device;
    RtlZeroMemory(ctx->Bar, sizeof(ctx->Bar));

    /* Create I/O queue for IOCTLs */
    WDF_IO_QUEUE_CONFIG_INIT_DEFAULT_QUEUE(&ioQueueConfig, WdfIoQueueDispatchSequential);
    ioQueueConfig.EvtIoDeviceControl = GoyaEvtIoDeviceControl;

    status = WdfIoQueueCreate(device, &ioQueueConfig, WDF_NO_OBJECT_ATTRIBUTES, &queue);
    if (!NT_SUCCESS(status)) {
        KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_ERROR_LEVEL,
            "GoyaBAR: Queue creation failed 0x%x\n", status));
        return status;
    }

    return STATUS_SUCCESS;
}

/* -----------------------------------------------------------------------
 * PrepareHardware — map PCI BARs
 * ----------------------------------------------------------------------- */

NTSTATUS
GoyaEvtDevicePrepareHardware(
    _In_ WDFDEVICE Device,
    _In_ WDFCMRESLIST ResourcesRaw,
    _In_ WDFCMRESLIST ResourcesTranslated
)
{
    PGOYA_DEVICE_CONTEXT ctx = GoyaGetDeviceContext(Device);
    ULONG resourceCount;
    ULONG barIndex = 0;
    ULONG i;

    PAGED_CODE();

    resourceCount = WdfCmResourceListGetCount(ResourcesTranslated);

    KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
        "GoyaBAR: PrepareHardware — %lu resources\n", resourceCount));

    for (i = 0; i < resourceCount; i++) {
        PCM_PARTIAL_RESOURCE_DESCRIPTOR desc =
            WdfCmResourceListGetDescriptor(ResourcesTranslated, i);

        if (desc == NULL) {
            continue;
        }

        switch (desc->Type) {
        case CmResourceTypeMemory:
        case CmResourceTypeMemoryLarge:
            if (barIndex < 6) {
                ctx->Bar[barIndex].PhysAddr = desc->u.Memory.Start;
                ctx->Bar[barIndex].Length = desc->u.Memory.Length;

                KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
                    "GoyaBAR: BAR%lu — Phys=0x%llx Len=0x%x\n",
                    barIndex,
                    desc->u.Memory.Start.QuadPart,
                    desc->u.Memory.Length));

                /* Map BAR into kernel virtual address space */
                /* Only map BAR0 (config registers) — limit to 16MB for safety */
                if (barIndex == 0) {
                    ULONG mapLength = desc->u.Memory.Length;
                    if (mapLength > 16 * 1024 * 1024) {
                        mapLength = 16 * 1024 * 1024;
                    }

                    ctx->Bar[barIndex].VirtAddr = MmMapIoSpace(
                        desc->u.Memory.Start,
                        mapLength,
                        MmNonCached
                    );

                    if (ctx->Bar[barIndex].VirtAddr != NULL) {
                        ctx->Bar[barIndex].Mapped = TRUE;
                        ctx->Bar[barIndex].Length = mapLength;
                        KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
                            "GoyaBAR: BAR%lu mapped at VA=%p\n",
                            barIndex, ctx->Bar[barIndex].VirtAddr));
                    } else {
                        KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_ERROR_LEVEL,
                            "GoyaBAR: BAR%lu MmMapIoSpace FAILED\n", barIndex));
                    }
                }

                barIndex++;
            }
            break;

        case CmResourceTypeInterrupt:
            KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
                "GoyaBAR: Interrupt resource (vector=%lu)\n",
                desc->u.Interrupt.Vector));
            break;

        default:
            break;
        }
    }

    if (!ctx->Bar[0].Mapped) {
        KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_ERROR_LEVEL,
            "GoyaBAR: BAR0 not mapped — cannot proceed\n"));
        return STATUS_DEVICE_CONFIGURATION_ERROR;
    }

    return STATUS_SUCCESS;
}

/* -----------------------------------------------------------------------
 * ReleaseHardware — unmap BARs
 * ----------------------------------------------------------------------- */

NTSTATUS
GoyaEvtDeviceReleaseHardware(
    _In_ WDFDEVICE Device,
    _In_ WDFCMRESLIST ResourcesTranslated
)
{
    PGOYA_DEVICE_CONTEXT ctx = GoyaGetDeviceContext(Device);
    ULONG i;

    UNREFERENCED_PARAMETER(ResourcesTranslated);
    PAGED_CODE();

    KdPrintEx((DPFLTR_IHVDRIVER_ID, DPFLTR_INFO_LEVEL,
        "GoyaBAR: ReleaseHardware\n"));

    for (i = 0; i < 6; i++) {
        if (ctx->Bar[i].Mapped && ctx->Bar[i].VirtAddr != NULL) {
            MmUnmapIoSpace(ctx->Bar[i].VirtAddr, ctx->Bar[i].Length);
            ctx->Bar[i].VirtAddr = NULL;
            ctx->Bar[i].Mapped = FALSE;
        }
    }

    return STATUS_SUCCESS;
}

/* -----------------------------------------------------------------------
 * IOCTL handler — read/write registers
 * ----------------------------------------------------------------------- */

VOID
GoyaEvtIoDeviceControl(
    _In_ WDFQUEUE   Queue,
    _In_ WDFREQUEST Request,
    _In_ size_t     OutputBufferLength,
    _In_ size_t     InputBufferLength,
    _In_ ULONG      IoControlCode
)
{
    NTSTATUS status = STATUS_INVALID_DEVICE_REQUEST;
    WDFDEVICE device = WdfIoQueueGetDevice(Queue);
    PGOYA_DEVICE_CONTEXT ctx = GoyaGetDeviceContext(device);
    size_t bytesReturned = 0;

    switch (IoControlCode) {

    case IOCTL_GOYA_READ32:
    {
        PGOYA_READ32_IN input;
        PGOYA_READ32_OUT output;

        if (InputBufferLength < sizeof(GOYA_READ32_IN) ||
            OutputBufferLength < sizeof(GOYA_READ32_OUT)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        status = WdfRequestRetrieveInputBuffer(Request, sizeof(GOYA_READ32_IN),
            (PVOID*)&input, NULL);
        if (!NT_SUCCESS(status)) break;

        status = WdfRequestRetrieveOutputBuffer(Request, sizeof(GOYA_READ32_OUT),
            (PVOID*)&output, NULL);
        if (!NT_SUCCESS(status)) break;

        /* Validate BAR index and offset */
        ULONG barIdx = input->BarIndex;
        if (barIdx >= 6 || !ctx->Bar[barIdx].Mapped) {
            status = STATUS_INVALID_PARAMETER;
            break;
        }

        if (input->Offset + sizeof(ULONG) > ctx->Bar[barIdx].Length) {
            status = STATUS_INVALID_PARAMETER;
            break;
        }

        /* Read 32-bit register */
        output->Value = READ_REGISTER_ULONG(
            (PULONG)((PUCHAR)ctx->Bar[barIdx].VirtAddr + input->Offset)
        );

        bytesReturned = sizeof(GOYA_READ32_OUT);
        status = STATUS_SUCCESS;
        break;
    }

    case IOCTL_GOYA_WRITE32:
    {
        PGOYA_WRITE32_IN input;

        if (InputBufferLength < sizeof(GOYA_WRITE32_IN)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        status = WdfRequestRetrieveInputBuffer(Request, sizeof(GOYA_WRITE32_IN),
            (PVOID*)&input, NULL);
        if (!NT_SUCCESS(status)) break;

        /* Validate BAR index and offset */
        ULONG barIdx = input->BarIndex;
        if (barIdx >= 6 || !ctx->Bar[barIdx].Mapped) {
            status = STATUS_INVALID_PARAMETER;
            break;
        }

        if (input->Offset + sizeof(ULONG) > ctx->Bar[barIdx].Length) {
            status = STATUS_INVALID_PARAMETER;
            break;
        }

        /* Write 32-bit register */
        WRITE_REGISTER_ULONG(
            (PULONG)((PUCHAR)ctx->Bar[barIdx].VirtAddr + input->Offset),
            input->Value
        );

        status = STATUS_SUCCESS;
        break;
    }

    case IOCTL_GOYA_GET_BAR_INFO:
    {
        PGOYA_BAR_INFO output;

        if (OutputBufferLength < sizeof(GOYA_BAR_INFO)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }

        status = WdfRequestRetrieveOutputBuffer(Request, sizeof(GOYA_BAR_INFO),
            (PVOID*)&output, NULL);
        if (!NT_SUCCESS(status)) break;

        RtlZeroMemory(output, sizeof(GOYA_BAR_INFO));
        output->BarCount = 6;

        for (ULONG i = 0; i < 6; i++) {
            output->Bars[i].PhysicalAddress = ctx->Bar[i].PhysAddr.QuadPart;
            output->Bars[i].Length = ctx->Bar[i].Length;
            output->Bars[i].IsMapped = ctx->Bar[i].Mapped;
        }

        bytesReturned = sizeof(GOYA_BAR_INFO);
        status = STATUS_SUCCESS;
        break;
    }

    default:
        status = STATUS_INVALID_DEVICE_REQUEST;
        break;
    }

    WdfRequestCompleteWithInformation(Request, status, bytesReturned);
}

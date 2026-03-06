# Goya BAR Access Driver (goya_bar.sys)

Minimal KMDF kernel driver that maps Habana Goya PCI BARs and exposes register read/write to userspace.

## What It Does

1. Claims PCI device `VEN_1DA3&DEV_0001` (Habana Goya HL-1000)
2. Maps BAR0 (config registers) into kernel virtual address space via `MmMapIoSpace`
3. Exposes three IOCTLs via `\\.\GoyaBAR`:
   - `IOCTL_GOYA_READ32` — Read a 32-bit register at BAR offset
   - `IOCTL_GOYA_WRITE32` — Write a 32-bit register at BAR offset
   - `IOCTL_GOYA_GET_BAR_INFO` — Query BAR physical addresses and sizes

All intelligence lives in userspace Python code. The driver is intentionally thin.

## Prerequisites

- Windows 11 (x64)
- Visual Studio 2022 with **Desktop development with C++** workload
- [Windows Driver Kit (WDK)](https://learn.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk)
- Windows SDK (matching version)

## Build

### Option A: Visual Studio

1. Open VS 2022 Developer Command Prompt
2. Create a new KMDF driver project, or use the provided source files
3. Build for Release x64

### Option B: Command Line (after WDK install)

```cmd
:: Set up environment
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" amd64

:: Build (requires a .vcxproj — generate from VS or use cmake)
msbuild goya_bar.vcxproj /p:Configuration=Release /p:Platform=x64
```

## Install

### Test Signing (Development)

Windows requires driver signing. For development:

```cmd
:: Enable test signing (one-time, requires reboot)
bcdedit /set testsigning on

:: Create a test certificate
makecert -r -pe -ss PrivateCertStore -n "CN=GoyaBAR Test" goya_test.cer

:: Sign the driver
signtool sign /s PrivateCertStore /n "GoyaBAR Test" /t http://timestamp.digicert.com goya_bar.sys

:: Create catalog file
inf2cat /driver:. /os:10_x64
signtool sign /s PrivateCertStore /n "GoyaBAR Test" goya_bar.cat
```

### Install the Driver

```cmd
:: Install using devcon (from WDK tools)
devcon install goya_bar.inf "PCI\VEN_1DA3&DEV_0001"

:: Or use pnputil
pnputil /add-driver goya_bar.inf /install
```

### Verify

```cmd
:: Check if device is using our driver
devcon status "PCI\VEN_1DA3&DEV_0001"

:: Check driver is loaded
sc query GoyaBAR
```

Then run the Python probe:
```cmd
cd D:\goya-on-windows
set PYTHONPATH=src
python -m goya
```

## Uninstall

```cmd
:: Remove driver
pnputil /delete-driver goya_bar.inf /uninstall

:: Disable test signing when done
bcdedit /set testsigning off
```

## Security Notes

- The driver validates all BAR indices and offsets before access
- Only BAR0 is mapped (16 MB limit for safety)
- No DMA or interrupt handling — those will be added in later phases
- The `\\.\GoyaBAR` device requires admin privileges to open

# build_and_install.ps1 — Build goya_bar.sys and install on the local machine
#
# Prerequisites:
#   - Visual Studio 2022 with C++ Desktop Development
#   - Windows Driver Kit (WDK) installed
#   - Run as Administrator
#   - Test signing enabled: bcdedit /set testsigning on
#
# Usage:
#   .\scripts\build_and_install.ps1           # Build + install
#   .\scripts\build_and_install.ps1 -BuildOnly  # Build only
#   .\scripts\build_and_install.ps1 -Uninstall  # Remove driver

param(
    [switch]$BuildOnly,
    [switch]$Uninstall,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$DriverDir = Join-Path $PSScriptRoot "..\driver"
$ProjectFile = Join-Path $DriverDir "goya_bar.vcxproj"
$InfFile = Join-Path $DriverDir "goya_bar.inf"
$HwId = "PCI\VEN_1DA3&DEV_0001"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

# --- Uninstall ---
if ($Uninstall) {
    Write-Step "Uninstalling goya_bar driver"
    try {
        pnputil /delete-driver goya_bar.inf /uninstall 2>&1 | Out-Null
        Write-Ok "Driver removed"
    } catch {
        Write-Warn "Driver may not be installed: $_"
    }
    exit 0
}

# --- Check prerequisites ---
Write-Step "Checking prerequisites"

# Check for MSBuild
$msbuild = Get-Command msbuild -ErrorAction SilentlyContinue
if (-not $msbuild) {
    # Try VS 2022 locations
    $vsLocations = @(
        "${env:ProgramFiles}\Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\MSBuild.exe",
        "${env:ProgramFiles}\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\MSBuild.exe",
        "${env:ProgramFiles}\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe"
    )
    foreach ($loc in $vsLocations) {
        if (Test-Path $loc) {
            $msbuild = $loc
            break
        }
    }
    if (-not $msbuild) {
        Write-Error "MSBuild not found. Install Visual Studio 2022 with C++ workload."
    }
}
Write-Ok "MSBuild: $($msbuild)"

# Check for WDK
$wdkRoot = "${env:ProgramFiles(x86)}\Windows Kits\10"
if (-not (Test-Path $wdkRoot)) {
    Write-Error "WDK not found at $wdkRoot. Install the Windows Driver Kit."
}
Write-Ok "WDK: $wdkRoot"

# Check project file
if (-not (Test-Path $ProjectFile)) {
    Write-Error "Project file not found: $ProjectFile"
}
Write-Ok "Project: $ProjectFile"

# --- Build ---
Write-Step "Building goya_bar.sys (Release x64)"
$buildArgs = @(
    $ProjectFile,
    "/p:Configuration=Release",
    "/p:Platform=x64",
    "/v:minimal",
    "/nologo"
)
& $msbuild @buildArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed with exit code $LASTEXITCODE"
}

# Find the built .sys file
$sysFile = Get-ChildItem -Path $DriverDir -Recurse -Filter "goya_bar.sys" | Select-Object -First 1
if (-not $sysFile) {
    Write-Error "goya_bar.sys not found after build"
}
Write-Ok "Built: $($sysFile.FullName)"

if ($BuildOnly) {
    Write-Step "Build complete (install skipped)"
    exit 0
}

# --- Check admin ---
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Must run as Administrator to install drivers"
}

# --- Check test signing ---
$testsigning = bcdedit /enum "{current}" 2>&1 | Select-String "testsigning\s+Yes"
if (-not $testsigning -and -not $Force) {
    Write-Warn "Test signing is not enabled. Enable with:"
    Write-Warn "  bcdedit /set testsigning on"
    Write-Warn "  (requires reboot)"
    Write-Warn "Use -Force to skip this check"
    exit 1
}

# --- Install ---
Write-Step "Installing driver"
pnputil /add-driver $InfFile /install
if ($LASTEXITCODE -ne 0) {
    Write-Warn "pnputil install returned $LASTEXITCODE (device may not be present)"
    Write-Warn "Driver is staged. It will activate when the Goya card is detected."
}

# --- Verify ---
Write-Step "Verifying installation"
$svcStatus = sc.exe query GoyaBAR 2>&1
if ($svcStatus -match "RUNNING") {
    Write-Ok "GoyaBAR service is RUNNING"
} elseif ($svcStatus -match "STOPPED") {
    Write-Ok "GoyaBAR service is installed (STOPPED — device may not be present)"
} else {
    Write-Warn "GoyaBAR service status unknown. Device may not be present."
    Write-Warn "Run 'python -m goya' to probe."
}

Write-Step "Done! Run the probe to verify BAR access:"
Write-Host "  cd D:\goya-on-windows" -ForegroundColor White
Write-Host '  $env:PYTHONPATH = "src"' -ForegroundColor White
Write-Host "  python -m goya" -ForegroundColor White

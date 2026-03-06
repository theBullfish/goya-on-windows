# install.ps1 — Build catalog, sign, and install goya_bar.sys
# Must be run as Administrator
param(
    [switch]$EnableTestSigning,
    [switch]$Install
)

$ErrorActionPreference = 'Stop'
$driverDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildDir = Join-Path $driverDir 'build'

# Copy .sys and .inf to a staging directory
$stageDir = Join-Path $buildDir 'stage'
if (Test-Path $stageDir) { Remove-Item $stageDir -Recurse -Force }
New-Item -ItemType Directory -Path $stageDir | Out-Null

Copy-Item (Join-Path $buildDir 'goya_bar.sys') $stageDir
Copy-Item (Join-Path $driverDir 'goya_bar.inf') $stageDir

# Find WDK tools
$wdkBin = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin' -Directory |
    Where-Object { $_.Name -match '^\d+\.\d+' } | Sort-Object Name | Select-Object -Last 1
$inf2cat = Join-Path $wdkBin.FullName 'x86\inf2cat.exe'
$signtool = Join-Path $wdkBin.FullName 'x64\signtool.exe'

Write-Host "Stage dir: $stageDir"
Write-Host "Inf2Cat: $inf2cat"
Write-Host "Signtool: $signtool"

# Create catalog file
Write-Host "`nCreating catalog..."
& $inf2cat /driver:$stageDir /os:10_X64 /verbose
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Inf2Cat failed (exit $LASTEXITCODE) - proceeding without catalog"
} else {
    # Sign the catalog
    Write-Host "Signing catalog..."
    $pfx = Join-Path $buildDir 'GoyaTest.pfx'
    & $signtool sign /fd SHA256 /f $pfx /p 'GoyaTest2026' /t http://timestamp.digicert.com (Join-Path $stageDir 'goya_bar.cat')
}

# Sign the .sys in stage dir too
Write-Host "Signing driver..."
$pfx = Join-Path $buildDir 'GoyaTest.pfx'
& $signtool sign /fd SHA256 /f $pfx /p 'GoyaTest2026' /t http://timestamp.digicert.com (Join-Path $stageDir 'goya_bar.sys')

# Enable test signing if requested
if ($EnableTestSigning) {
    Write-Host "`nEnabling test signing..."
    bcdedit /set testsigning on
    Write-Host "Test signing enabled. REBOOT REQUIRED before driver will load."
}

# Install if requested
if ($Install) {
    Write-Host "`nInstalling driver..."
    pnputil /add-driver (Join-Path $stageDir 'goya_bar.inf') /install
}

Write-Host "`nDone."
Write-Host "Files in stage dir:"
Get-ChildItem $stageDir | Format-Table Name, Length

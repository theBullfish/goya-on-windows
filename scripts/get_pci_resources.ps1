# Get PCI resource information for Habana Goya device
$dev = Get-PnpDevice -InstanceId 'PCI\VEN_1DA3*' -ErrorAction SilentlyContinue
if (-not $dev) {
    Write-Host "No Habana Goya device found"
    exit 1
}

Write-Host "=== Habana Goya PCI Device ==="
Write-Host "Instance ID: $($dev.InstanceId)"
Write-Host "Status: $($dev.Status)"
Write-Host "Class: $($dev.Class)"
Write-Host "FriendlyName: $($dev.FriendlyName)"
Write-Host "Problem: $($dev.Problem)"
Write-Host ""

# Get device properties
$props = Get-PnpDeviceProperty -InstanceId $dev.InstanceId -ErrorAction SilentlyContinue
foreach ($p in $props) {
    if ($p.KeyName -match 'Address|Bus|Location|Driver|Resource|Memory|Interrupt') {
        Write-Host "$($p.KeyName) = $($p.Data)"
    }
}

Write-Host ""
Write-Host "=== All Allocated Resources ==="

# Get memory resources via WMI
$wmiDev = Get-CimInstance -ClassName Win32_PnPEntity | Where-Object { $_.DeviceID -like '*1DA3*' }
if ($wmiDev) {
    Write-Host "WMI Name: $($wmiDev.Name)"
    Write-Host "WMI Status: $($wmiDev.Status)"
    Write-Host "ConfigManagerErrorCode: $($wmiDev.ConfigManagerErrorCode)"

    # Get allocated resources
    $resources = Get-CimAssociatedInstance -InputObject $wmiDev -ResultClassName Win32_SystemMemoryResource -ErrorAction SilentlyContinue
    foreach ($r in $resources) {
        Write-Host "Memory Resource: Start=0x$($r.StartingAddress.ToString('X')) End=0x$($r.EndingAddress.ToString('X'))"
    }
}

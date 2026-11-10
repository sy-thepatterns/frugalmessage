# Read-only capability check for the Windows study machine.
# Battery discharge and CPU package counters have different measurement
# boundaries from whole-laptop AC input power.
$ErrorActionPreference = 'Continue'

Write-Output 'Computer model:'
try {
    Get-CimInstance Win32_ComputerSystemProduct -ErrorAction Stop |
        Select-Object Vendor, Name, Version |
        Format-List
} catch {
    Write-Output "Model query unavailable: $($_.Exception.Message)"
}

Write-Output 'Battery telemetry (on battery, if supported):'
try {
    $battery = Get-CimInstance -Namespace root/WMI -ClassName BatteryStatus -ErrorAction Stop
    $battery | Select-Object PowerOnline, Charging, Discharging, DischargeRate,
        ChargeRate, RemainingCapacity, Voltage | Format-List
    if (-not $battery) { Write-Output 'No BatteryStatus instance exposed.' }
} catch {
    Write-Output "BatteryStatus unavailable: $($_.Exception.Message)"
}

Write-Output 'ACPI Power Meter instances:'
try {
    $meter = Get-Counter '\Power Meter(*)\Power' -ErrorAction Stop
    $meter.CounterSamples | Select-Object Path, CookedValue | Format-Table
    if (-not $meter.CounterSamples) { Write-Output 'No Power Meter instance exposed.' }
} catch {
    Write-Output "No usable Power Meter counter: $($_.Exception.Message)"
}

Write-Output 'Probe complete. A plug-in AC watt meter with timestamped export is preferred for whole-laptop joules.'

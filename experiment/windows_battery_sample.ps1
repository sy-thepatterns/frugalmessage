param(
    [Parameter(Mandatory = $true)][string]$OutputCsv,
    [int]$DurationSeconds = 600,
    [int]$IntervalSeconds = 1
)

# Run on battery power after checking BatteryStatus with windows_power_probe.ps1.
# The ACPI battery present rate is normally in mW. This is battery DC output,
# not adapter input or mains power. Reject unavailable or implausible values.
if ($DurationSeconds -lt 60 -or $IntervalSeconds -lt 1) {
    throw 'Use at least 60 seconds and a positive sample interval.'
}
$ErrorActionPreference = 'Stop'
$parent = Split-Path -Parent $OutputCsv
if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
if (Test-Path -LiteralPath $OutputCsv) { throw 'Refusing to overwrite existing power samples.' }
$sampleCount = 0
$stopAt = (Get-Date).ToUniversalTime().AddSeconds($DurationSeconds)
while ((Get-Date).ToUniversalTime() -lt $stopAt) {
    $status = @(Get-CimInstance -Namespace root/WMI -ClassName BatteryStatus -ErrorAction Stop)
    if ($status.Count -ne 1 -or -not $status[0].Discharging -or $status[0].PowerOnline) {
        throw 'Exactly one discharging battery must be present; connect no AC charger during this run.'
    }
    if ($status[0].RemainingCapacity -lt 5000) { throw 'Stopping capture below 5 Wh remaining battery capacity.' }
    $millwatts = [double]$status[0].DischargeRate
    if ($millwatts -le 0 -or $millwatts -gt 200000) {
        throw "Battery discharge rate is unavailable or implausible: $millwatts mW"
    }
    $sample = [pscustomobject]@{
        timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
        power_w = $millwatts / 1000.0
        raw_discharge_mw = $millwatts
        remaining_capacity = $status[0].RemainingCapacity
        boundary = 'battery_dc'
    }
    $sample | Export-Csv -LiteralPath $OutputCsv -NoTypeInformation -Encoding UTF8 -Append
    $sampleCount++
    Start-Sleep -Seconds $IntervalSeconds
}
Write-Output "Saved $sampleCount battery-side samples to $OutputCsv"

param(
    [string]$Python = '.\.venv\Scripts\python.exe',
    [int]$SampleSeconds = 3600,
    [int]$IdleSeconds = 60,
    [string]$Transport = 'fresh'
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if ($Transport -notin @('fresh', 'persistent')) { throw 'Invalid transport' }
if ($SampleSeconds -lt 120 -or $IdleSeconds -lt 30) { throw 'Allow at least 120 seconds of capture and 30 seconds idle.' }
$model = Get-CimInstance Win32_ComputerSystem
if ($model.Manufacturer -notmatch 'LENOVO') { throw 'Run this workflow on the Lenovo study laptop.' }
$docker = (Get-Command docker -ErrorAction Stop).Source
$engine = & $docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $engine -ne 'linux') { throw 'Start Docker Desktop with Linux containers first.' }
if (-not (Test-Path -LiteralPath $Python)) { throw 'Create .venv and install requirements-dev.txt first.' }
$Python = (Resolve-Path -LiteralPath $Python).Path
$battery = @(Get-CimInstance -Namespace root/WMI -ClassName BatteryStatus)
if ($battery.Count -ne 1 -or $battery[0].PowerOnline -or -not $battery[0].Discharging -or
    $battery[0].DischargeRate -le 0 -or $battery[0].DischargeRate -gt 200000) {
    throw 'Unplug the Lenovo and verify a usable discharge rate before starting.'
}
$study = 'lenovo-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$root = Join-Path (Get-Location) ('analysis/results/experimental_runs/' + $study)
New-Item -ItemType Directory -Path $root -Force | Out-Null
& $Python -m pip freeze | Set-Content (Join-Path $root 'dependencies.txt')
$model | Select-Object Manufacturer,Model | ConvertTo-Json | Set-Content (Join-Path $root 'machine.json')
$compose = @('compose','-f','experiment/compose.yaml')
& $docker @compose up -d --build db app
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL setup failed; inspect study containers before retrying.' }
$sampler = $null
$runner = $null
$runnerName = $study + '-runner'
try {
    $watts = Join-Path $root 'battery.csv'
    $samplerArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSScriptRoot +
        '\windows_battery_sample.ps1" -OutputCsv "' + $watts + '" -DurationSeconds ' + $SampleSeconds
    $sampler = Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList $samplerArgs `
        -RedirectStandardOutput (Join-Path $root 'sampler.log') -RedirectStandardError (Join-Path $root 'sampler.error.log')
    $idleStart = (Get-Date).ToUniversalTime().ToString('o')
    Start-Sleep -Seconds $IdleSeconds
    @{started_utc=$idleStart; ended_utc=(Get-Date).ToUniversalTime().ToString('o'); purpose='idle control; validate background activity before subtraction'} | ConvertTo-Json | Set-Content (Join-Path $root 'idle-interval.json')
    $sampler.Refresh()
    if ($sampler.HasExited) { throw 'Battery capture failed during idle; inspect sampler.error.log.' }
    $runArgs = 'compose -f experiment/compose.yaml run --name ' + $runnerName +
        ' --rm --entrypoint python runner -m experiment.matrix --events /data/replay/replay_events.csv' +
        ' --output /data/runs/' + $study + ' --machine lenovo-83DL-postgres --speedup 120 --repeats 3 --transport ' + $Transport
    $runner = Start-Process $docker -WindowStyle Hidden -PassThru -ArgumentList $runArgs `
        -RedirectStandardOutput (Join-Path $root 'matrix.log') -RedirectStandardError (Join-Path $root 'matrix.error.log')
    while (-not $runner.WaitForExit(1000)) {
        $sampler.Refresh()
        if ($sampler.HasExited) { throw 'Battery sampling stopped; aborting matrix to preserve measurement integrity.' }
    }
    $runner.Refresh()
    $matrixExit = $runner.ExitCode
    Start-Sleep -Seconds 5
    if ($matrixExit -ne 0) { Write-Warning 'Some matrix runs failed; preserving all artifacts and auditing the plan.' }
    $plans = @(Get-ChildItem -LiteralPath $root -Filter '*-plan.json')
    if ($plans.Count -ne 1) { throw 'Expected exactly one run plan.' }
    & $Python -m experiment.integrate_power --plan $plans[0].FullName --watts $watts `
        --meter-id Lenovo-83DL-ACPI-BatteryStatus --boundary battery_dc --output (Join-Path $root 'powered')
    if ($LASTEXITCODE -ne 0) { throw 'Power coverage failed; artifacts retained, no energy winner can be claimed.' }
    & $Python analysis/05_select_configs.py --plan (Join-Path $root ('powered/' + $plans[0].Name)) `
        --output (Join-Path $root 'selection')
    if ($LASTEXITCODE -ne 0) { throw 'Selection failed; inspect artifacts.' }
    Write-Output "Results: $root. Validate sensor cadence and idle interval before interpreting energy differences."
} finally {
    if ($runner -and -not $runner.HasExited) { & $docker stop $runnerName }
    if ($sampler -and -not $sampler.HasExited) { Stop-Process -Id $sampler.Id }
    & $docker @compose down
}

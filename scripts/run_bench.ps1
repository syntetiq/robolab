# Run Robot Test Bench
# Usage:
#   .\scripts\run_bench.ps1                          # all 3 models with video
#   .\scripts\run_bench.ps1 -Model light             # single model
#   .\scripts\run_bench.ps1 -NoVideo                 # skip video encoding
#   .\scripts\run_bench.ps1 -Model heavy -Duration 20

param(
    [string]$Model = "",
    [switch]$AllModels,
    [switch]$NoVideo,
    [switch]$DriveBase,
    [switch]$Choreo,
    [double]$DriveDistance = 1.0,
    [double]$DriveSpeed = 0.3,
    [double]$Duration = 25.0,
    [string]$Output = "C:\RoboLab_Data\bench",
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat",
    [string]$TiagoDir = "C:\RoboLab_Data\data\tiago_isaac"
)

$ErrorActionPreference = "Stop"
$ScriptPath = Join-Path $PSScriptRoot "test_robot_bench.py"

if (-not (Test-Path $ScriptPath)) {
    Write-Error "Bench script not found: $ScriptPath"
    exit 1
}
if (-not (Test-Path $IsaacPython)) {
    Write-Error "Isaac Sim python.bat not found: $IsaacPython"
    exit 1
}

$benchArgs = @(
    $ScriptPath,
    "--output", $Output,
    "--duration", $Duration,
    "--tiago-dir", $TiagoDir,
    "--headless"
)

if ($AllModels -or (-not $Model)) {
    $benchArgs += "--all-models"
} else {
    $benchArgs += @("--model", $Model)
}

if ($NoVideo) {
    $benchArgs += "--no-video"
}

if ($Choreo) {
    $benchArgs += @("--choreo", "--drive-distance", $DriveDistance, "--drive-speed", $DriveSpeed)
} elseif ($DriveBase) {
    $benchArgs += @("--drive-base", "--drive-distance", $DriveDistance, "--drive-speed", $DriveSpeed)
}

Write-Host "[RunBench] Isaac Python: $IsaacPython"
Write-Host "[RunBench] Script: $ScriptPath"
Write-Host "[RunBench] Output: $Output"
Write-Host "[RunBench] Model: $(if ($AllModels -or (-not $Model)) { 'ALL' } else { $Model })"
Write-Host "[RunBench] Duration: $Duration s"
Write-Host "[RunBench] Video: $(if ($NoVideo) { 'OFF' } else { 'ON' })"
Write-Host "[RunBench] Mode: $(if ($Choreo) { 'CHOREO' } elseif ($DriveBase) { "DRIVE ${DriveDistance}m at ${DriveSpeed} m/s" } else { 'STATIC' })"
Write-Host ""

$env:PYTHONUNBUFFERED = "1"
& $IsaacPython @benchArgs
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Error "[RunBench] Bench exited with code $exitCode"
    exit $exitCode
}

Write-Host ""
Write-Host "[RunBench] Done. Results in: $Output"

# Show summary files
Get-ChildItem -Path $Output -Recurse -Filter "summary.txt" | ForEach-Object {
    Write-Host ""
    Write-Host "=== $($_.Directory.Name) ==="
    Get-Content $_.FullName
}

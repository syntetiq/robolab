# Run Robot Test Bench
# Usage:
#   .\scripts\run_bench.ps1                          # all 3 models with video
#   .\scripts\run_bench.ps1 -Model light             # single model
#   .\scripts\run_bench.ps1 -NoVideo                 # skip video encoding
#   .\scripts\run_bench.ps1 -Grasp -Fast            # quick grasp run (no video, 55s, shorter settle)
#   .\scripts\run_bench.ps1 -Model heavy -Duration 20

param(
    [string]$Model = "",
    [switch]$AllModels,
    [switch]$NoVideo,
    [switch]$Fast,
    [switch]$DriveBase,
    [switch]$Choreo,
    [switch]$Grasp,
    [double]$DriveDistance = 1.0,
    [double]$DriveSpeed = 0.3,
    [double]$Duration = 25.0,
    [string]$Output = "",
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat",
    [string]$TiagoDir = "C:\RoboLab_Data\data\tiago_isaac",
    [double]$MugX = 2.0,
    [double]$MugY = 0.0,
    [double]$PlaceDx = 0.0,
    [double]$PlaceDy = -0.20,
    [double]$LiftHeight = 0.20,
    [double]$TorsoSpeed = 0.05,
    [double]$TorsoLowerSpeed = 0.02,
    [double]$ShiftRotSpeed = 0.15,
    [double]$ApproachClearance = 0.13,
    [ValidateSet("top", "side", "auto")]
    [string]$GraspMode = "top",
    [double]$TopPregraspHeight = 0.06,
    [double]$TopDescendSpeed = 0.015,
    [double]$TopDescendClearance = 0.025,
    [double]$TopXyTol = 0.02,
    [double]$TopVerifyXyTol = 0.03,
    [double]$TopLiftTestHeight = 0.015,
    [double]$TopLiftTestHold = 0.6,
    [double]$TopRetryYStep = 0.008,
    [double]$TopRetryZStep = 0.008,
    [int]$TopMaxRetries = 2,
    [double]$GripperLengthM = 0.10,
    [switch]$Fridge,
    [switch]$NoFridge
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

if (-not $Output) {
    $Output = "C:\RoboLab_Data\bench"
    if ($Grasp) { $Output = "C:\RoboLab_Data\episodes" }
}

$benchArgs = @(
    $ScriptPath,
    "--output", $Output,
    "--duration", $Duration,
    "--tiago-dir", $TiagoDir,
    "--headless"
)

if ($Grasp -or $Choreo -or $DriveBase) {
    # Action scenarios always use single model (default: heavy)
    $benchArgs += @("--model", $(if ($Model) { $Model } else { "heavy" }))
} elseif ($AllModels -or (-not $Model)) {
    $benchArgs += "--all-models"
} else {
    $benchArgs += @("--model", $Model)
}

if ($NoVideo -or $Fast) {
    $benchArgs += "--no-video"
}
if ($Fast) {
    if ($Grasp -and $Duration -eq 25.0) { $Duration = 55.0 }
    $benchArgs += "--fast"
}

if ($Grasp) {
    $inv = [System.Globalization.CultureInfo]::InvariantCulture
    $DriveDistanceStr = [string]::Format($inv, "{0:0.######}", $DriveDistance)
    $DriveSpeedStr = [string]::Format($inv, "{0:0.######}", $DriveSpeed)
    $MugXStr = [string]::Format($inv, "{0:0.######}", $MugX)
    $MugYStr = [string]::Format($inv, "{0:0.######}", $MugY)
    $PlaceDxStr = [string]::Format($inv, "{0:0.######}", $PlaceDx)
    $PlaceDyStr = [string]::Format($inv, "{0:0.######}", $PlaceDy)
    $LiftHeightStr = [string]::Format($inv, "{0:0.######}", $LiftHeight)
    $TorsoSpeedStr = [string]::Format($inv, "{0:0.######}", $TorsoSpeed)
    $TorsoLowerSpeedStr = [string]::Format($inv, "{0:0.######}", $TorsoLowerSpeed)
    $ShiftRotSpeedStr = [string]::Format($inv, "{0:0.######}", $ShiftRotSpeed)
    $ApproachClearanceStr = [string]::Format($inv, "{0:0.######}", $ApproachClearance)
    $TopPregraspHeightStr = [string]::Format($inv, "{0:0.######}", $TopPregraspHeight)
    $TopDescendSpeedStr = [string]::Format($inv, "{0:0.######}", $TopDescendSpeed)
    $TopDescendClearanceStr = [string]::Format($inv, "{0:0.######}", $TopDescendClearance)
    $TopXyTolStr = [string]::Format($inv, "{0:0.######}", $TopXyTol)
    $TopVerifyXyTolStr = [string]::Format($inv, "{0:0.######}", $TopVerifyXyTol)
    $TopLiftTestHeightStr = [string]::Format($inv, "{0:0.######}", $TopLiftTestHeight)
    $TopLiftTestHoldStr = [string]::Format($inv, "{0:0.######}", $TopLiftTestHold)
    $TopRetryYStepStr = [string]::Format($inv, "{0:0.######}", $TopRetryYStep)
    $TopRetryZStepStr = [string]::Format($inv, "{0:0.######}", $TopRetryZStep)
    $GripperLengthStr = [string]::Format($inv, "{0:0.######}", $GripperLengthM)
    $benchArgs += @(
        "--grasp",
        "--drive-distance", $DriveDistanceStr,
        "--drive-speed", $DriveSpeedStr,
        "--mug-x", $MugXStr,
        "--mug-y", $MugYStr,
        "--place-dx", $PlaceDxStr,
        "--place-dy", $PlaceDyStr,
        "--lift-height", $LiftHeightStr,
        "--torso-speed", $TorsoSpeedStr,
        "--torso-lower-speed", $TorsoLowerSpeedStr,
        "--shift-rot-speed", $ShiftRotSpeedStr,
        "--approach-clearance", $ApproachClearanceStr,
        "--grasp-mode", $GraspMode,
        "--top-pregrasp-height", $TopPregraspHeightStr,
        "--top-descend-speed", $TopDescendSpeedStr,
        "--top-descend-clearance", $TopDescendClearanceStr,
        "--top-xy-tol", $TopXyTolStr,
        "--top-verify-xy-tol", $TopVerifyXyTolStr,
        "--top-lift-test-height", $TopLiftTestHeightStr,
        "--top-lift-test-hold-s", $TopLiftTestHoldStr,
        "--top-retry-y-step", $TopRetryYStepStr,
        "--top-retry-z-step", $TopRetryZStepStr,
        "--top-max-retries", $TopMaxRetries,
        "--gripper-length-m", $GripperLengthStr
    )
    if ($NoFridge) { $benchArgs += "--no-fridge" }
    elseif ($Fridge) { $benchArgs += "--fridge" }
} elseif ($Choreo) {
    $benchArgs += @("--choreo", "--drive-distance", $DriveDistance, "--drive-speed", $DriveSpeed)
} elseif ($DriveBase) {
    $benchArgs += @("--drive-base", "--drive-distance", $DriveDistance, "--drive-speed", $DriveSpeed)
}

Write-Host "[RunBench] Isaac Python: $IsaacPython"
Write-Host "[RunBench] Script: $ScriptPath"
Write-Host "[RunBench] Output: $Output"
Write-Host "[RunBench] Model: $(if ($AllModels -or (-not $Model)) { 'ALL' } else { $Model })"
Write-Host "[RunBench] Duration: $Duration s"
Write-Host "[RunBench] Video: $(if ($NoVideo -or $Fast) { 'OFF' } else { 'ON' })"
if ($Fast) { Write-Host "[RunBench] Fast: shorter settle, no video" }
Write-Host "[RunBench] Mode: $(if ($Grasp) { "GRASP($GraspMode) center=($MugX,$MugY) place=($PlaceDx,$PlaceDy)m lift=${LiftHeight}m torso=${TorsoSpeed}/${TorsoLowerSpeed} clearance=${ApproachClearance}m gripperLen=${GripperLengthM}m top[h=${TopPregraspHeight},dz=${TopDescendClearance},xy=${TopXyTol}]" } elseif ($Choreo) { 'CHOREO' } elseif ($DriveBase) { "DRIVE ${DriveDistance}m at ${DriveSpeed} m/s" } else { 'STATIC' })"
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

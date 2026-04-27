# Batch stability test for grasp scenario.
# Runs multiple no-video episodes and writes aggregate metrics.
#
# Example:
#   .\scripts\run_grasp_stability.ps1 -Runs 12 -Fast -JitterXY 0.02

param(
    [int]$Runs = 10,
    [switch]$Fast,
    [double]$JitterXY = 0.015,
    [ValidateSet("top", "side", "auto")]
    [string]$GraspMode = "",
    [double]$GripperLengthM = -1,
    [int]$RunTimeoutSec = 420,
    [string]$OutputRoot = "C:\RoboLab_Data\stability",
    [string]$ConfigPath = "",
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat"
)

$ErrorActionPreference = "Stop"
$runBench = Join-Path $PSScriptRoot "run_bench.ps1"
if (-not (Test-Path $runBench)) {
    Write-Error "run_bench.ps1 not found: $runBench"
    exit 1
}

if (-not $ConfigPath) {
    $ConfigPath = Join-Path (Split-Path $PSScriptRoot -Parent) "config\grasp_tuning.json"
}
if (-not (Test-Path $ConfigPath)) {
    Write-Error "Config not found: $ConfigPath"
    exit 1
}

$cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$suiteDir = Join-Path $OutputRoot ("grasp_suite_" + $timestamp)
New-Item -Path $suiteDir -ItemType Directory -Force | Out-Null

$results = @()
$successCount = 0
$startSuite = Get-Date
if (-not $GraspMode) {
    $GraspMode = if ($cfg.grasp_mode) { [string]$cfg.grasp_mode } else { "top" }
}
if ($GripperLengthM -lt 0) {
    $GripperLengthM = if ($cfg.gripper_length_m) { [double]$cfg.gripper_length_m } else { 0.10 }
}

for ($i = 1; $i -le $Runs; $i++) {
    $runName = "run_{0:D3}" -f $i
    $runDir = Join-Path $suiteDir $runName
    New-Item -Path $runDir -ItemType Directory -Force | Out-Null

    # Random mug XY perturbation to test robustness.
    $dx = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * $JitterXY
    $dy = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * $JitterXY
    $mugX = [double]$cfg.mug_x + $dx
    $mugY = [double]$cfg.mug_y + $dy

    $duration = if ($Fast) { [double]$cfg.duration_s_fast } else { [double]$cfg.duration_s_video }
    $runStart = Get-Date

    Write-Host ("[{0}/{1}] {2} mug=({3:N3},{4:N3}) duration={5}s" -f $i, $Runs, $runName, $mugX, $mugY, $duration)

    $rbArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $runBench,
        "-Grasp",
        "-NoVideo",
        "-Output", $runDir,
        "-IsaacPython", $IsaacPython,
        "-Duration", ([string]$duration),
        "-MugX", ([string]$mugX),
        "-MugY", ([string]$mugY),
        "-PlaceDx", ([string]([double]$cfg.place_dx)),
        "-PlaceDy", ([string]([double]$cfg.place_dy)),
        "-LiftHeight", ([string]([double]$cfg.lift_height)),
        "-TorsoSpeed", ([string]([double]$cfg.torso_speed)),
        "-TorsoLowerSpeed", ([string]([double]$cfg.torso_lower_speed)),
        "-ShiftRotSpeed", ([string]([double]$cfg.shift_rot_speed)),
        "-DriveSpeed", ([string]([double]$cfg.drive_speed)),
        "-ApproachClearance", ([string]([double]$cfg.approach_clearance)),
        "-GraspMode", $GraspMode,
        "-TopPregraspHeight", ([string]([double]$cfg.top_pregrasp_height)),
        "-TopDescendSpeed", ([string]([double]$cfg.top_descend_speed)),
        "-TopDescendClearance", ([string]([double]$cfg.top_descend_clearance)),
        "-TopXyTol", ([string]([double]$cfg.top_xy_tol)),
        "-TopVerifyXyTol", ([string]([double]$(if ($cfg.top_verify_xy_tol) { $cfg.top_verify_xy_tol } else { 0.03 }))),
        "-TopLiftTestHeight", ([string]([double]$cfg.top_lift_test_height)),
        "-TopLiftTestHold", ([string]([double]$cfg.top_lift_test_hold_s)),
        "-TopRetryYStep", ([string]([double]$cfg.top_retry_y_step)),
        "-TopRetryZStep", ([string]([double]$cfg.top_retry_z_step)),
        "-TopMaxRetries", ([string]([int]$cfg.top_max_retries)),
        "-GripperLengthM", ([string]$GripperLengthM)
    )
    if ($Fast) {
        $rbArgs += "-Fast"
    }

    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $rbArgs -PassThru -NoNewWindow
    $finished = $proc.WaitForExit($RunTimeoutSec * 1000)
    if (-not $finished) {
        try { Stop-Process -Id $proc.Id -Force } catch {}
        $results += [pscustomobject]@{
            run = $runName
            mug_x = [math]::Round($mugX, 4)
            mug_y = [math]::Round($mugY, 4)
            success = $false
            retries = -1
            retries_top = -1
            retries_side = -1
            mode_final = "timeout"
            fallback_used = $false
            gripper_length_m = $GripperLengthM
            lift_delta_m = 0.0
            final_tilt_deg = 0.0
            wall_time_s = [math]::Round(((Get-Date) - $runStart).TotalSeconds, 2)
            fail_code = "timeout"
        }
        continue
    }
    if ($proc.ExitCode -ne 0) {
        $results += [pscustomobject]@{
            run = $runName
            mug_x = [math]::Round($mugX, 4)
            mug_y = [math]::Round($mugY, 4)
            success = $false
            retries = -1
            retries_top = -1
            retries_side = -1
            mode_final = "bench_error"
            fallback_used = $false
            gripper_length_m = $GripperLengthM
            lift_delta_m = 0.0
            final_tilt_deg = 0.0
            wall_time_s = [math]::Round(((Get-Date) - $runStart).TotalSeconds, 2)
            fail_code = "bench_exit_" + $proc.ExitCode
        }
        continue
    }

    $logPath = Join-Path (Join-Path $runDir "heavy") "physics_log.json"
    if (-not (Test-Path $logPath)) {
        $results += [pscustomobject]@{
            run = $runName
            mug_x = [math]::Round($mugX, 4)
            mug_y = [math]::Round($mugY, 4)
            success = $false
            retries = -1
            retries_top = -1
            retries_side = -1
            mode_final = "unknown"
            fallback_used = $false
            gripper_length_m = $GripperLengthM
            lift_delta_m = 0.0
            final_tilt_deg = 0.0
            wall_time_s = [math]::Round(((Get-Date) - $runStart).TotalSeconds, 2)
            fail_code = "missing_log"
        }
        continue
    }

    $payload = Get-Content $logPath -Raw | ConvertFrom-Json
    $report = $payload.report
    $success = [bool]$report.grasp_success
    if ($success) { $successCount++ }
    $failCode = if ($success) { "" } else { [string]$report.verdict }

    $results += [pscustomobject]@{
        run = $runName
        mug_x = [math]::Round($mugX, 4)
        mug_y = [math]::Round($mugY, 4)
        success = $success
        retries = [int]$report.grasp_retry_count
        retries_top = [int]$report.grasp_retry_count_top
        retries_side = [int]$report.grasp_retry_count_side
        mode_final = [string]$report.grasp_active_mode_final
        fallback_used = [bool]$report.grasp_fallback_used
        gripper_length_m = [double]$report.gripper_length_m
        lift_delta_m = [double]$report.grasp_lift_delta_m
        final_tilt_deg = [double]$report.grasp_final_tilt_deg
        wall_time_s = [math]::Round(((Get-Date) - $runStart).TotalSeconds, 2)
        fail_code = $failCode
    }
}

$suiteWall = [math]::Round(((Get-Date) - $startSuite).TotalSeconds, 2)
$successRate = if ($Runs -gt 0) { [math]::Round((100.0 * $successCount / $Runs), 2) } else { 0.0 }
$totalRetries = ($results | Measure-Object -Property retries -Sum).Sum
$avgRetries = if ($Runs -gt 0) { [math]::Round(($totalRetries / $Runs), 3) } else { 0.0 }

$csvPath = Join-Path $suiteDir "stability_results.csv"
$jsonPath = Join-Path $suiteDir "stability_results.json"
$summaryPath = Join-Path $suiteDir "stability_summary.txt"

$results | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $csvPath
$results | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 $jsonPath

@(
    "TIAGo Grasp Stability Suite"
    "==========================="
    "runs: $Runs"
    "success_count: $successCount"
    "success_rate_percent: $successRate"
    "avg_retries: $avgRetries"
    "jitter_xy_m: $JitterXY"
    "grasp_mode: $GraspMode"
    "gripper_length_m: $GripperLengthM"
    "suite_wall_time_s: $suiteWall"
    "config: $ConfigPath"
    "csv: $csvPath"
    "json: $jsonPath"
) | Out-File -Encoding utf8 $summaryPath

Write-Host ""
Write-Host "[Stability] Suite finished"
Write-Host "[Stability] Success: $successCount/$Runs ($successRate`%)"
Write-Host "[Stability] Avg retries: $avgRetries"
Write-Host "[Stability] Summary: $summaryPath"

# 15 tests in a row: approach_clearance +1 cm each episode (stop earlier).
# Episode 1: 13 cm, Episode 2: 14 cm, ... Episode 15: 27 cm. All with video.
# Output: table of clearance vs grasp_success, lift_delta, episode_id.
#
# Usage: .\scripts\run_approach_sweep_15.ps1

param(
    [double]$StartClearanceM = 0.13,
    [double]$StepM = 0.01,
    [int]$Runs = 15,
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat"
)

$ErrorActionPreference = "Stop"
$runBench = Join-Path $PSScriptRoot "run_bench.ps1"
$episodesRoot = "C:\RoboLab_Data\episodes"
if (-not (Test-Path $runBench)) { Write-Error "run_bench.ps1 not found"; exit 1 }
if (-not (Test-Path $episodesRoot)) { New-Item -Path $episodesRoot -ItemType Directory -Force | Out-Null }

$results = [System.Collections.ArrayList]@()
$inv = [System.Globalization.CultureInfo]::InvariantCulture

for ($i = 1; $i -le $Runs; $i++) {
    $clearance = $StartClearanceM + ($i - 1) * $StepM
    $clearanceStr = [string]::Format($inv, "{0:0.######}", $clearance)

    Write-Host ""
    Write-Host "========== Run $i/$Runs | approach_clearance = $clearanceStr m ($([int]($clearance*100)) cm) ==========" -ForegroundColor Cyan

    # Random mug position for this run
    $dx = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * 0.02
    $dy = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * 0.02
    $mugX = 2.0 + $dx
    $mugY = 0.0 + $dy
    $mugXStr = [string]::Format($inv, "{0:0.######}", $mugX)
    $mugYStr = [string]::Format($inv, "{0:0.######}", $mugY)

    & $runBench -Grasp -GraspMode top -Output $episodesRoot -Duration 70 `
        -ApproachClearance $clearanceStr -MugX $mugXStr -MugY $mugYStr -IsaacPython $IsaacPython

    if ($LASTEXITCODE -ne 0) {
        [void]$results.Add([pscustomobject]@{
            run = $i
            approach_clearance_m = $clearance
            approach_clearance_cm = [int]($clearance * 100)
            grasp_success = $null
            grasp_lift_delta_m = $null
            grasp_retry_count = $null
            verdict = "RUN_FAILED"
            episode_id = $null
        })
        continue
    }

    # Latest episode folder (UUID-like)
    $latest = Get-ChildItem -Path $episodesRoot -Directory | Where-Object { $_.Name -match '^[0-9a-f]{8}-[0-9a-f]{4}-' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $epId = $null
    $graspSuccess = $null
    $liftDelta = $null
    $retryCount = $null
    $verdict = $null

    if ($latest) {
        $epId = $latest.Name
        $physicsLog = Join-Path $latest.FullName "physics_log.json"
        $metaPath = Join-Path $latest.FullName "metadata.json"
        if (Test-Path $physicsLog) {
            try {
                $log = Get-Content $physicsLog -Raw | ConvertFrom-Json
                if ($log.report) {
                    $graspSuccess = $log.report.grasp_success
                    $liftDelta = $log.report.grasp_lift_delta_m
                    $retryCount = $log.report.grasp_retry_count
                    $verdict = $log.report.verdict
                }
            } catch {}
        }
        if ($null -eq $graspSuccess -and (Test-Path $metaPath)) {
            try {
                $meta = Get-Content $metaPath -Raw | ConvertFrom-Json
                if ($meta.results) {
                    $graspSuccess = $meta.results.grasp_success
                    $liftDelta = $meta.results.grasp_lift_delta_m
                    $retryCount = $meta.results.grasp_retry_count
                    $verdict = $meta.results.verdict
                }
            } catch {}
        }
    }

    [void]$results.Add([pscustomobject]@{
        run = $i
        approach_clearance_m = $clearance
        approach_clearance_cm = [int]($clearance * 100)
        grasp_success = $graspSuccess
        grasp_lift_delta_m = $liftDelta
        grasp_retry_count = $retryCount
        verdict = $verdict
        episode_id = $epId
    })
}

# Table
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  APPROACH SWEEP RESULTS (15 runs)" -ForegroundColor Green
Write-Host "  Param: approach_clearance (+1 cm per run)" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

$table = $results | Format-Table -Property run, approach_clearance_cm, approach_clearance_m, grasp_success, grasp_lift_delta_m, grasp_retry_count, verdict, episode_id -AutoSize -Wrap
$table | Out-String

# CSV
$sweepDir = Join-Path "C:\RoboLab_Data" "approach_sweep_15"
if (-not (Test-Path $sweepDir)) { New-Item -Path $sweepDir -ItemType Directory -Force | Out-Null }
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$csvPath = Join-Path $sweepDir "sweep_$timestamp.csv"
$results | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
Write-Host "CSV: $csvPath" -ForegroundColor Yellow

$txtPath = Join-Path $sweepDir "sweep_$timestamp.txt"
$results | Format-Table -AutoSize | Out-String | Set-Content $txtPath -Encoding UTF8
Write-Host "Table: $txtPath" -ForegroundColor Yellow

# Summary
$successCount = ($results | Where-Object { $_.grasp_success -eq $true }).Count
Write-Host ""
Write-Host "Success: $successCount / $Runs" -ForegroundColor $(if ($successCount -gt 0) { "Green" } else { "Gray" })
exit 0

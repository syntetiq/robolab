# Quick grasp test: 3 fast runs (no video) with different approach_clearance.
# On first success -> re-run WITH video.

param(
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat"
)

$ErrorActionPreference = "Stop"
$runBench = Join-Path $PSScriptRoot "run_bench.ps1"
$episodesRoot = "C:\RoboLab_Data\episodes"
if (-not (Test-Path $runBench)) { Write-Error "run_bench.ps1 not found"; exit 1 }

$clearances = @(0.03, 0.08, 0.13)
$inv = [System.Globalization.CultureInfo]::InvariantCulture
$results = [System.Collections.ArrayList]@()
$successClearance = $null

foreach ($c in $clearances) {
    $cStr = [string]::Format($inv, "{0:0.######}", $c)
    $cCm = [int]($c * 100)

    $dx = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * 0.015
    $dy = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * 0.015
    $mugX = 2.0 + $dx
    $mugY = 0.0 + $dy

    Write-Host ""
    Write-Host "===== clearance=${cCm}cm  NO VIDEO =====" -ForegroundColor Cyan

    & $runBench -Grasp -GraspMode top -Fast -Output $episodesRoot -Duration 55 `
        -ApproachClearance $c -MugX $mugX -MugY $mugY -IsaacPython $IsaacPython

    $exitCode = $LASTEXITCODE
    $success = $null; $liftDelta = $null; $retries = $null; $verdict = $null

    if ($exitCode -eq 0) {
        $summaryPath = Join-Path $episodesRoot "heavy\summary.txt"
        if (Test-Path $summaryPath) {
            $lines = Get-Content $summaryPath
            foreach ($line in $lines) {
                if ($line -match 'grasp_success:\s*(.+)') { $success = $Matches[1].Trim() -eq 'True' }
                if ($line -match 'grasp_lift_delta_m:\s*(.+)') { $liftDelta = [double]$Matches[1].Trim() }
                if ($line -match 'grasp_retry_count:\s*(.+)') { $retries = [int]$Matches[1].Trim() }
                if ($line -match 'verdict:\s*(.+)') { $verdict = $Matches[1].Trim() }
            }
        }
    } else {
        $verdict = "RUN_FAILED"
    }

    [void]$results.Add([pscustomobject]@{
        clearance_cm = $cCm
        grasp_success = $success
        lift_delta_m = $liftDelta
        retries = $retries
        verdict = $verdict
    })

    $statusColor = if ($success) { "Green" } else { "Gray" }
    Write-Host "[${cCm}cm] success=$success lift=$liftDelta retries=$retries $verdict" -ForegroundColor $statusColor

    if ($success -eq $true -and $null -eq $successClearance) {
        $successClearance = $c
    }
}

Write-Host ""
Write-Host "===========================================" -ForegroundColor Green
Write-Host "  QUICK GRASP TEST RESULTS" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green
$results | Format-Table -AutoSize | Out-String | Write-Host

if ($null -ne $successClearance) {
    $cCm = [int]($successClearance * 100)
    Write-Host ""
    Write-Host "SUCCESS at ${cCm}cm! Re-running WITH VIDEO..." -ForegroundColor Green

    $dx = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * 0.015
    $dy = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * 0.015
    $mugX = 2.0 + $dx
    $mugY = 0.0 + $dy

    & $runBench -Grasp -GraspMode top -Output $episodesRoot -Duration 70 `
        -ApproachClearance $successClearance -MugX $mugX -MugY $mugY -IsaacPython $IsaacPython

    if ($LASTEXITCODE -eq 0) {
        $latest = Get-ChildItem -Path $episodesRoot -Directory | Where-Object { $_.Name -match '^[0-9a-f]{8}-' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($latest) {
            Write-Host ""
            Write-Host "VIDEO episode: $($latest.FullName)" -ForegroundColor Green
        }
    }
} else {
    Write-Host ""
    Write-Host "No success. Check descend_clearance and xy_tol tuning." -ForegroundColor Red
}

exit 0

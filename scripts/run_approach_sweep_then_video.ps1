# Sweep approach_clearance without video (fast). On first success, re-run with video.
# Clearances: 0.01, 0.03, 0.05, 0.08, 0.10, 0.13, 0.16, 0.20
#
# Usage: .\scripts\run_approach_sweep_then_video.ps1

param(
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat"
)

$ErrorActionPreference = "Stop"
$runBench = Join-Path $PSScriptRoot "run_bench.ps1"
$episodesRoot = "C:\RoboLab_Data\episodes"
if (-not (Test-Path $runBench)) { Write-Error "run_bench.ps1 not found"; exit 1 }

$clearances = @(0.01, 0.03, 0.05, 0.08, 0.10, 0.13, 0.16, 0.20)
$inv = [System.Globalization.CultureInfo]::InvariantCulture
$results = [System.Collections.ArrayList]@()
$successClearance = $null

foreach ($c in $clearances) {
    $cStr = [string]::Format($inv, "{0:0.######}", $c)
    $cCm = [int]($c * 100)

    # Random mug
    $dx = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * 0.015
    $dy = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * 0.015
    $mugX = 2.0 + $dx
    $mugY = 0.0 + $dy

    Write-Host ""
    Write-Host "===== clearance=${cCm}cm  mug=($([string]::Format('{0:N3}', $mugX)),$([string]::Format('{0:N3}', $mugY)))  NO VIDEO =====" -ForegroundColor Cyan

    & $runBench -Grasp -GraspMode top -Fast -Output $episodesRoot -Duration 55 `
        -ApproachClearance $c -MugX $mugX -MugY $mugY -IsaacPython $IsaacPython

    $exitCode = $LASTEXITCODE
    $epId = $null; $success = $null; $liftDelta = $null; $retries = $null; $verdict = $null

    if ($exitCode -eq 0) {
        # Read summary from heavy/summary.txt
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
        clearance_m = $c
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

# Print table
Write-Host ""
Write-Host "===========================================" -ForegroundColor Green
Write-Host "  APPROACH SWEEP RESULTS (no video)" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green
$results | Format-Table -AutoSize | Out-String | Write-Host

# Save CSV
$sweepDir = Join-Path "C:\RoboLab_Data" "approach_sweep_fast"
if (-not (Test-Path $sweepDir)) { New-Item -Path $sweepDir -ItemType Directory -Force | Out-Null }
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$results | Export-Csv -Path (Join-Path $sweepDir "sweep_$ts.csv") -NoTypeInformation -Encoding UTF8
Write-Host "CSV: $(Join-Path $sweepDir "sweep_$ts.csv")" -ForegroundColor Yellow

# If success found, re-run with video at that clearance
if ($null -ne $successClearance) {
    $cCm = [int]($successClearance * 100)
    Write-Host ""
    Write-Host "===========================================" -ForegroundColor Green
    Write-Host "  SUCCESS at ${cCm}cm! Re-running WITH VIDEO" -ForegroundColor Green
    Write-Host "===========================================" -ForegroundColor Green

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
    Write-Host "No success in sweep. Review table and adjust parameters." -ForegroundColor Red
}

exit 0

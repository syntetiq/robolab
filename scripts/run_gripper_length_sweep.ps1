# Sweep effective gripper length and compare grasp stability metrics.
#
# Example:
#   .\scripts\run_gripper_length_sweep.ps1 -Lengths "0.05,0.08,0.12,0.16" -RunsPerLength 3 -GraspMode side -Fast

param(
    [string]$Lengths = "0.05,0.08,0.12,0.16",
    [int]$RunsPerLength = 3,
    [ValidateSet("top", "side", "auto")]
    [string]$GraspMode = "side",
    [switch]$Fast,
    [double]$JitterXY = 0.015,
    [string]$OutputRoot = "C:\RoboLab_Data\gripper_length_sweep",
    [string]$ConfigPath = "",
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat"
)

$ErrorActionPreference = "Stop"
$runStability = Join-Path $PSScriptRoot "run_grasp_stability.ps1"
if (-not (Test-Path $runStability)) {
    Write-Error "run_grasp_stability.ps1 not found: $runStability"
    exit 1
}

$lengthValues = @()
foreach ($raw in ($Lengths -split ",")) {
    $t = $raw.Trim()
    if (-not $t) { continue }
    $lengthValues += [double]$t
}
if ($lengthValues.Count -eq 0) {
    Write-Error "No valid lengths provided"
    exit 1
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$sweepDir = Join-Path $OutputRoot ("sweep_" + $timestamp)
New-Item -Path $sweepDir -ItemType Directory -Force | Out-Null

$rows = @()

for ($i = 0; $i -lt $lengthValues.Count; $i++) {
    $L = $lengthValues[$i]
    Write-Host ("[{0}/{1}] length={2:N3}m mode={3}" -f ($i + 1), $lengthValues.Count, $L, $GraspMode)

    & $runStability `
        -Runs $RunsPerLength `
        -Fast:$Fast `
        -JitterXY $JitterXY `
        -GraspMode $GraspMode `
        -GripperLengthM $L `
        -OutputRoot $sweepDir `
        -ConfigPath $ConfigPath `
        -IsaacPython $IsaacPython

    $suite = Get-ChildItem -Path $sweepDir -Directory | Sort-Object LastWriteTime | Select-Object -Last 1
    if (-not $suite) {
        $rows += [pscustomobject]@{
            gripper_length_m = $L
            runs = $RunsPerLength
            success_count = 0
            success_rate_percent = 0.0
            avg_retries = 0.0
            suite_path = ""
            note = "missing suite dir"
        }
        continue
    }

    $summary = Join-Path $suite.FullName "stability_summary.txt"
    if (-not (Test-Path $summary)) {
        $rows += [pscustomobject]@{
            gripper_length_m = $L
            runs = $RunsPerLength
            success_count = 0
            success_rate_percent = 0.0
            avg_retries = 0.0
            suite_path = $suite.FullName
            note = "missing summary"
        }
        continue
    }

    $text = Get-Content $summary -Raw
    $successCount = if ($text -match "success_count:\s*([0-9]+)") { [int]$Matches[1] } else { 0 }
    $successRate = if ($text -match "success_rate_percent:\s*([0-9]+(?:\.[0-9]+)?)") { [double]$Matches[1] } else { 0.0 }
    $avgRetries = if ($text -match "avg_retries:\s*([0-9]+(?:\.[0-9]+)?)") { [double]$Matches[1] } else { 0.0 }

    $rows += [pscustomobject]@{
        gripper_length_m = $L
        runs = $RunsPerLength
        success_count = $successCount
        success_rate_percent = $successRate
        avg_retries = $avgRetries
        suite_path = $suite.FullName
        note = ""
    }
}

$rows = $rows | Sort-Object @{Expression="success_rate_percent";Descending=$true}, @{Expression="avg_retries";Descending=$false}

$csv = Join-Path $sweepDir "length_sweep_results.csv"
$txt = Join-Path $sweepDir "length_sweep_summary.txt"
$json = Join-Path $sweepDir "length_sweep_results.json"

$rows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $csv
$rows | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 $json

$lines = @(
    "TIAGo Gripper Length Sweep"
    "=========================="
    ("mode: {0}" -f $GraspMode)
    ("runs_per_length: {0}" -f $RunsPerLength)
    ("jitter_xy_m: {0}" -f $JitterXY)
    ("lengths: {0}" -f ($lengthValues -join ", "))
    ""
    "Ranked results:"
)

foreach ($r in $rows) {
    $lines += ("L={0:N3}m | success={1}/{2} ({3}%) | avg_retries={4} | suite={5}" -f
        $r.gripper_length_m, $r.success_count, $r.runs, $r.success_rate_percent, $r.avg_retries, $r.suite_path)
}

$lines += ""
$lines += ("csv: {0}" -f $csv)
$lines += ("json: {0}" -f $json)

$lines | Out-File -Encoding utf8 $txt

Write-Host ""
Write-Host "[LengthSweep] Done"
Write-Host "[LengthSweep] Summary: $txt"

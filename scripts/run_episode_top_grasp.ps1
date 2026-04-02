# Single episode: vertical (top) grasp of a mug at random position on table.
# Writes video and report to C:\RoboLab_Data\episodes\<uuid> in general format
# (metadata.json, telemetry.json, camera_0/1/2.mp4, physics_log.json, LeRobot meta/data/videos).
#
# Usage:
#   .\scripts\run_episode_top_grasp.ps1
#   .\scripts\run_episode_top_grasp.ps1 -JitterXY 0.03

param(
    [double]$JitterXY = 0.02,
    [double]$MugCenterX = 2.0,
    [double]$MugCenterY = 0.0,
    [double]$Duration = 70.0,
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat"
)

$ErrorActionPreference = "Stop"
$runBench = Join-Path $PSScriptRoot "run_bench.ps1"
if (-not (Test-Path $runBench)) {
    Write-Error "run_bench.ps1 not found: $runBench"
    exit 1
}

# Random mug position on table
$dx = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * $JitterXY
$dy = (Get-Random -Minimum (-1000000) -Maximum 1000001) / 1000000.0 * $JitterXY
$mugX = $MugCenterX + $dx
$mugY = $MugCenterY + $dy

$episodesRoot = "C:\RoboLab_Data\episodes"
if (-not (Test-Path $episodesRoot)) {
    New-Item -Path $episodesRoot -ItemType Directory -Force | Out-Null
}

Write-Host "[Episode] Vertical (top) grasp, random mug at ($([string]::Format('{0:N3}', $mugX)), $([string]::Format('{0:N3}', $mugY))), video ON, output: $episodesRoot"
Write-Host ""

& $runBench `
    -Grasp `
    -GraspMode top `
    -Output $episodesRoot `
    -Duration $Duration `
    -MugX $mugX `
    -MugY $mugY `
    -IsaacPython $IsaacPython

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Error "[Episode] run_bench exited with code $exitCode"
    exit $exitCode
}

# Show latest episode folder
$latest = Get-ChildItem -Path $episodesRoot -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latest) {
    Write-Host ""
    Write-Host "[Episode] Result: $($latest.FullName)"
    if (Test-Path (Join-Path $latest.FullName "metadata.json")) {
        Get-Content (Join-Path $latest.FullName "metadata.json") | ConvertFrom-Json | Select-Object id, status, task, duration_sec, @{N="grasp_success";E={ $_.results.grasp_success }} | Format-List
    }
}
exit 0

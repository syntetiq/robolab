<#
.SYNOPSIS
    Run a task-config episode in Isaac Sim.

.PARAMETER Config
    Path to task config JSON file (relative to repo root or absolute).
    Default: config/tasks/scene_survey.json

.PARAMETER Output
    Output directory for video and logs. Default: C:\RoboLab_Data\episodes

.PARAMETER Duration
    Simulation duration in seconds (overrides task timeouts budget). Default: 120.

.PARAMETER NoVideo
    Skip video recording (faster iteration).

.PARAMETER Model
    Robot model (heavy | light). Default: heavy.

.EXAMPLE
    .\scripts\run_task_config.ps1 -Config config/tasks/test_fridge_open_close.json
    .\scripts\run_task_config.ps1 -Config config/tasks/test_full_kitchen.json -Duration 300
    .\scripts\run_task_config.ps1 -Config config/tasks/scene_survey.json -NoVideo
#>
param(
    [string]$Config   = "config/tasks/scene_survey.json",
    [string]$Output   = "C:\RoboLab_Data\episodes",
    [double]$Duration = 120.0,
    [switch]$NoVideo,
    [string]$Model    = "heavy"
)

$ScriptRoot   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot     = Split-Path -Parent $ScriptRoot
$IsaacPython  = "C:\Users\max\Documents\IsaacSim\python.bat"
$ScriptPath   = Join-Path $ScriptRoot "test_robot_bench.py"

if (-not (Test-Path $IsaacPython)) {
    Write-Error "Isaac Sim python.bat not found: $IsaacPython"
    exit 1
}

# Resolve config path relative to repo root if not absolute
if (-not [System.IO.Path]::IsPathRooted($Config)) {
    $Config = Join-Path $RepoRoot $Config
}
if (-not (Test-Path $Config)) {
    Write-Error "Task config not found: $Config"
    exit 1
}

# Read episode_name and optional simulation_duration_s from JSON (used as default when -Duration not passed)
$configJson   = Get-Content $Config | ConvertFrom-Json
$episodeName  = if ($configJson.episode_name) { $configJson.episode_name } else { "episode" }
if ($configJson.simulation_duration_s -and [double]$configJson.simulation_duration_s -gt 0 -and $Duration -eq 120.0) {
    $Duration = [double]$configJson.simulation_duration_s
    Write-Host "  (Duration from config: simulation_duration_s = $Duration)"
}
$timestamp    = Get-Date -Format "yyyyMMdd_HHmmss"
$episodeDir   = Join-Path $Output "${episodeName}_${timestamp}"
New-Item -Path $episodeDir -ItemType Directory -Force | Out-Null

Write-Host ""
Write-Host "=========================================="
Write-Host "  Task Config Episode"
Write-Host "  Config:  $Config"
Write-Host "  Episode: $episodeName"
Write-Host "  Output:  $episodeDir"
Write-Host "  Duration: ${Duration}s"
Write-Host "=========================================="
Write-Host ""

$inv = [System.Globalization.CultureInfo]::InvariantCulture
$DurationStr = [string]::Format($inv, "{0:0.##}", $Duration)

$benchArgs = @(
    $ScriptPath,
    "--task-config", $Config,
    "--output",      $episodeDir,
    "--duration",    $DurationStr,
    "--model",       $Model,
    "--headless"
)

if ($NoVideo) {
    $benchArgs += "--no-video"
}

Write-Host "Command: $IsaacPython $($benchArgs -join ' ')"
Write-Host ""

& $IsaacPython @benchArgs
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "[OK] Episode finished: $episodeDir" -ForegroundColor Green
} else {
    Write-Host "[FAIL] Exit code: $exitCode" -ForegroundColor Red
}

exit $exitCode

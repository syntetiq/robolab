# Smoke test: episode -> collector --moveit -> sync
# Verifies the full pipeline: run Tiago collector with MoveIt, then check artifacts.
#
# Usage:
#   .\scripts\smoke_full_pipeline.ps1
#   .\scripts\smoke_full_pipeline.ps1 -UseApi    # Use RoboLab API (requires server)
#   .\scripts\smoke_full_pipeline.ps1 -Duration 10

param(
    [int]$Duration = 5,
    [string]$OutputBase = "C:\RoboLab_Data",
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat",
    [string]$EnvUsd = "C:\RoboLab_Data\scenes\Small_House_Interactive.usd",
    [string]$TiagoUsd = "C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional.usd",
    [switch]$RequireRealTiago,
    [switch]$UseApi,
    [string]$ApiBase = "http://localhost:3000"
)

$ErrorActionPreference = "Stop"
$EpisodeId = [guid]::NewGuid().ToString()
$EpisodeDir = Join-Path (Join-Path $OutputBase "episodes") $EpisodeId

Write-Host "[Smoke] Episode ID: $EpisodeId"
Write-Host "[Smoke] Output dir: $EpisodeDir"
Write-Host "[Smoke] Duration: $Duration s"
Write-Host "[Smoke] MoveIt mode: enabled"

# Ensure output dir exists
New-Item -ItemType Directory -Force -Path $EpisodeDir | Out-Null

if ($UseApi) {
    Write-Host "[Smoke] Using API mode (base: $ApiBase)"
    try {
        # Create episode
        $createBody = @{
            name = "Smoke Test $EpisodeId"
            durationSec = $Duration
            sceneId = $null
            launchProfileId = $null
        } | ConvertTo-Json
        $createResp = Invoke-RestMethod -Uri "$ApiBase/api/episodes" -Method POST -Body $createBody -ContentType "application/json"
        $EpisodeId = $createResp.id
        Write-Host "[Smoke] Created episode: $EpisodeId"

        # Start episode (requires launch profile with enableMoveIt)
        Invoke-RestMethod -Uri "$ApiBase/api/episodes/$EpisodeId/start" -Method POST | Out-Null
        Write-Host "[Smoke] Episode started, waiting $Duration s..."
        Start-Sleep -Seconds $Duration

        # Stop episode
        Invoke-RestMethod -Uri "$ApiBase/api/episodes/$EpisodeId/stop" -Method POST | Out-Null
        Write-Host "[Smoke] Episode stopped"

        # Sync
        Invoke-RestMethod -Uri "$ApiBase/api/episodes/$EpisodeId/sync" -Method POST | Out-Null
        Write-Host "[Smoke] Sync completed"

        $EpisodeDir = Join-Path (Join-Path $OutputBase "episodes") $EpisodeId
    } catch {
        Write-Error "[Smoke] API mode failed: $_"
        exit 1
    }
} else {
    # Standalone: run collector directly
    $ScriptPath = Join-Path $PSScriptRoot "data_collector_tiago.py"
    if (-not (Test-Path $ScriptPath)) {
        $ScriptPath = Join-Path (Get-Location) "scripts\data_collector_tiago.py"
    }
    if (-not (Test-Path $ScriptPath)) {
        Write-Error "[Smoke] data_collector_tiago.py not found"
        exit 1
    }
    if (-not (Test-Path $IsaacPython)) {
        Write-Error "[Smoke] Isaac Sim python.bat not found: $IsaacPython"
        exit 1
    }
    if (-not (Test-Path $EnvUsd)) {
        Write-Warning "[Smoke] Env USD not found: $EnvUsd (may fail)"
    }

    Write-Host "[Smoke] Running collector with --moveit --duration $Duration"
    # Keep Isaac ROS2 bridge isolated from active conda/ROS overlays in parent shell.
    $pathItems = ($env:Path -split ';' | Where-Object {
        $_ -and ($_ -notmatch 'Mambaforge') -and ($_ -notmatch 'Miniconda') -and ($_ -notmatch 'ros2_humble')
    })
    $env:Path = (($pathItems -join ';') + ';C:\Users\max\Documents\IsaacSim\exts\isaacsim.ros2.bridge\humble\lib')
    $env:HOME = "C:\Users\max"
    $env:ROS_DISTRO = "humble"
    $env:RMW_IMPLEMENTATION = "rmw_fastrtps_cpp"
    $env:ROS_DOMAIN_ID = "0"
    $env:ROS_LOCALHOST_ONLY = "0"
    $collectorArgs = @(
        $ScriptPath,
        "--env", $EnvUsd,
        "--tiago-usd", $TiagoUsd,
        "--output_dir", $EpisodeDir,
        "--duration", $Duration,
        "--headless",
        "--moveit"
    )
    if ($RequireRealTiago) {
        $collectorArgs += "--require-real-tiago"
    }
    & $IsaacPython @collectorArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "[Smoke] Collector exited with code $LASTEXITCODE"
        exit 1
    }
    # Collector does not write metadata.json (runner does when using API). Create minimal one for standalone smoke.
    $metaPath = Join-Path $EpisodeDir "metadata.json"
    if (-not (Test-Path $metaPath)) {
        @{
            id = $EpisodeId
            name = "Smoke Test $EpisodeId"
            startedAt = (Get-Date).ToString("o")
            outputDir = $EpisodeDir
        } | ConvertTo-Json | Set-Content $metaPath -Encoding UTF8
        Write-Host "[Smoke] Created minimal metadata.json for standalone run"
    }
}

# Verify required artifacts
$RequiredFiles = @(
    "dataset.json",
    "metadata.json",
    "dataset_manifest.json",
    "telemetry.json",
    "camera_0.mp4"
)

$Missing = @()
foreach ($f in $RequiredFiles) {
    $p = Join-Path $EpisodeDir $f
    if (Test-Path $p) {
        $size = (Get-Item $p).Length
        Write-Host "[Smoke] OK $f ($size bytes)"
    } else {
        Write-Host "[Smoke] MISSING $f"
        $Missing += $f
    }
}

# Check dataset.json for moveit_mode_enabled when --moveit was used
if (-not $UseApi) {
    $dsPath = Join-Path $EpisodeDir "dataset.json"
    if (Test-Path $dsPath) {
        $ds = Get-Content $dsPath -Raw | ConvertFrom-Json
        $moveitEnabled = $ds.metadata.moveit_mode_enabled
        if ($moveitEnabled) {
            Write-Host "[Smoke] OK moveit_mode_enabled=true in dataset"
        } else {
            Write-Host "[Smoke] WARN moveit_mode_enabled=false (expected true for --moveit)"
        }
    }
}

if ($Missing.Count -gt 0) {
    Write-Error "[Smoke] FAIL: Missing files: $($Missing -join ', ')"
    exit 1
}

Write-Host "[Smoke] PASS: All artifacts present"

param(
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat",
    [string]$RuntimeScenesDir = "C:\RoboLab_Data\scenes",
    [string]$OutputRoot = "C:\RoboLab_Data\episodes\scene_robot_videos",
    [int]$DurationSec = 180
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptRoot "..")
Set-Location $RepoRoot

function Resolve-SceneList {
    param([string]$RuntimeDir)
    $patterns = @(
        "*Office*_TiagoCompatible.usda",
        "*Meeting*_TiagoCompatible.usda",
        "*Canonical*_TiagoCompatible.usda",
        "*Kitchen*_TiagoCompatible.usda"
    )
    $collected = @()
    foreach ($pattern in $patterns) {
        $collected += Get-ChildItem -Path $RuntimeDir -Filter $pattern -ErrorAction SilentlyContinue
    }
    $unique = $collected | Sort-Object FullName -Unique
    if ($unique.Count -eq 0) {
        throw "No Tiago-compatible Office/Kitchen scene wrappers found in '$RuntimeDir'."
    }
    return $unique | ForEach-Object { $_.FullName }
}

if (-not (Test-Path $IsaacPython)) {
    throw "Isaac python not found: $IsaacPython"
}
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

$scenes = Resolve-SceneList -RuntimeDir $RuntimeScenesDir
$failed = @()

foreach ($scene in $scenes) {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "[RUN] presentation video: $scene"
    Write-Host "============================================================"

    $presentationArgs = @(
        "scripts/scene_presentation_video.py",
        "--scene-usd", $scene,
        "--isaac-python", $IsaacPython,
        "--output-root", $OutputRoot,
        "--duration", $DurationSec.ToString(),
        "--headless"
    )
    & python @presentationArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] presentation video failed: $scene" -ForegroundColor Red
        $failed += $scene
    } else {
        Write-Host "[OK] presentation video ready: $scene" -ForegroundColor Green
    }
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "[SUMMARY] Presentation video failures:" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "[SUMMARY] All presentation videos rendered successfully." -ForegroundColor Green
exit 0

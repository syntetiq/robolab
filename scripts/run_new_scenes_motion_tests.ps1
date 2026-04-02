param(
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat",
    [string]$RuntimeScenesDir = "C:\RoboLab_Data\scenes",
    [string]$OutputRoot = "C:\RoboLab_Data\episodes",
    [int]$DurationSec = 90
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
    $existing = @()
    foreach ($pattern in $patterns) {
        $existing += Get-ChildItem -Path $RuntimeDir -Filter $pattern -ErrorAction SilentlyContinue |
            ForEach-Object { (Resolve-Path $_.FullName).Path }
    }
    $existing = $existing | Sort-Object -Unique

    if ($existing.Count -eq 0) {
        throw "No compatible scene wrappers found in '$RuntimeDir'. Run preparation scripts first."
    }
    return $existing
}

if (-not (Test-Path $IsaacPython)) {
    throw "Isaac python not found: $IsaacPython"
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

$sceneList = Resolve-SceneList -RuntimeDir $RuntimeScenesDir
Write-Host "[INFO] Scene count: $($sceneList.Count)"
$failed = @()

foreach ($scenePath in $sceneList) {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "[RUN] Scene smoke for: $scenePath"
    Write-Host "============================================================"

    $smokeArgs = @(
        "scripts/scene_motion_smoke.py",
        "--scene-usd", $scenePath,
        "--isaac-python", $IsaacPython,
        "--output-root", $OutputRoot,
        "--duration", $DurationSec.ToString(),
        "--headless"
    )

    & python @smokeArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] scene: $scenePath (exit=$LASTEXITCODE)" -ForegroundColor Red
        $failed += $scenePath
    } else {
        Write-Host "[OK] scene: $scenePath" -ForegroundColor Green
    }
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "[SUMMARY] Failed scenes:" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "[SUMMARY] All scenes passed. Videos in: $OutputRoot" -ForegroundColor Green
exit 0

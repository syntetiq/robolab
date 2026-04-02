<#
.SYNOPSIS
    Prepare Office USDZ scenes for RoboLab runners.

.DESCRIPTION
    Copies Office USDZ assets from the repository to runtime scene storage and
    generates Tiago-compatible USDA wrappers.
#>
param(
    [string]$SourceDir = "",
    [string]$RuntimeScenesDir = "C:\RoboLab_Data\scenes",
    [switch]$CleanOldWrappers
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
if (-not $SourceDir) {
    $SourceDir = Join-Path $RepoRoot "scenes\Office"
    if (-not (Test-Path $SourceDir)) {
        $alt = Join-Path $RepoRoot "scenes\office"
        if (Test-Path $alt) { $SourceDir = $alt }
    }
}

if (-not (Test-Path $SourceDir)) {
    throw "Office source dir not found: $SourceDir"
}
[void](New-Item -ItemType Directory -Force -Path $RuntimeScenesDir)

$officeFiles = Get-ChildItem -Path $SourceDir -File -Filter "*.usdz" | Sort-Object Name
if ($officeFiles.Count -eq 0) {
    throw "No .usdz files found in $SourceDir"
}

Write-Host "[OfficePrep] Copying USDZ assets to runtime scenes dir: $RuntimeScenesDir"
foreach ($file in $officeFiles) {
    Copy-Item -Path $file.FullName -Destination (Join-Path $RuntimeScenesDir $file.Name) -Force
    Write-Host "  copied: $($file.Name)"
}

if ($CleanOldWrappers) {
    Get-ChildItem -Path $RuntimeScenesDir -Filter "*_TiagoCompatible.usda" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*Office*" -or $_.Name -like "*Meeting*" -or $_.Name -like "*Studio*" } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

Write-Host "[OfficePrep] Generating Tiago-compatible wrappers..."
$manifestPath = Join-Path $RepoRoot "config\scene_prep_manifest.json"
python (Join-Path $ScriptRoot "adapt_scenes_for_tiago.py") `
    --input-dir "$RuntimeScenesDir" `
    --output-dir "$RuntimeScenesDir" `
    --include "*Office*" `
    --recursive `
    --manifest "$manifestPath"

python (Join-Path $ScriptRoot "adapt_scenes_for_tiago.py") `
    --input-dir "$RuntimeScenesDir" `
    --output-dir "$RuntimeScenesDir" `
    --include "*Meeting*" `
    --recursive `
    --manifest "$manifestPath"

python (Join-Path $ScriptRoot "adapt_scenes_for_tiago.py") `
    --input-dir "$RuntimeScenesDir" `
    --output-dir "$RuntimeScenesDir" `
    --include "*Canonical*" `
    --recursive `
    --manifest "$manifestPath"

Write-Host "[OfficePrep] Done."

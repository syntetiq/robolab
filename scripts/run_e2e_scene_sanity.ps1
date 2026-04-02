param(
    [switch]$RunSceneFit,
    [switch]$RunFixedTaskSmoke,
    [string]$RuntimeScenesDir = "C:\RoboLab_Data\scenes",
    [string]$OutputRoot = "C:\RoboLab_Data\episodes",
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat"
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptRoot "..")
Set-Location $RepoRoot

$results = [ordered]@{
    timestamp = (Get-Date).ToString("s")
    checks = @()
}

function Add-CheckResult {
    param([string]$Name, [bool]$Ok, [string]$Notes)
    $results.checks += [ordered]@{
        name  = $Name
        ok    = $Ok
        notes = $Notes
    }
}

function Invoke-Check {
    param([string]$Name, [scriptblock]$Action)
    Write-Host ""
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Add-CheckResult -Name $Name -Ok $false -Notes "exit=$LASTEXITCODE"
        return $false
    }
    Add-CheckResult -Name $Name -Ok $true -Notes "ok"
    return $true
}

$allOk = $true
$allOk = (Invoke-Check "MVP readiness gates (static + regression)" {
    powershell -ExecutionPolicy Bypass -File "scripts/run_mvp_readiness_gates.ps1" -SkipTsc -RuntimeScenesDir "$RuntimeScenesDir"
}) -and $allOk

if ($RunSceneFit) {
    $allOk = (Invoke-Check "Strict scene-fit (Office/Kitchen)" {
        powershell -ExecutionPolicy Bypass -File "scripts/run_scene_fit_validations.ps1" -RuntimeScenesDir "$RuntimeScenesDir" -OutputRoot "$OutputRoot" -IsaacPython "$IsaacPython"
    }) -and $allOk
}

if ($RunFixedTaskSmoke) {
    $allOk = (Invoke-Check "Fixed task smoke (single config)" {
        powershell -ExecutionPolicy Bypass -File "scripts/run_task_config.ps1" -Config "config/tasks/fixed_banana_to_sink.json" -Output "$OutputRoot"
    }) -and $allOk
}

$results.goNoGo = if ($allOk) { "GO" } else { "NO_GO" }
$results.criteria = [ordered]@{
    fixedRegression = "Must pass"
    sceneFit = if ($RunSceneFit) { "Must pass" } else { "Not executed" }
    fixedTaskSmoke = if ($RunFixedTaskSmoke) { "Must pass" } else { "Not executed" }
}

$reportPath = Join-Path $OutputRoot ("e2e_scene_sanity_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".json")
$results | ConvertTo-Json -Depth 8 | Set-Content -Path $reportPath -Encoding UTF8

Write-Host ""
Write-Host "[E2E] Go/No-Go: $($results.goNoGo)" -ForegroundColor $(if ($allOk) { "Green" } else { "Red" })
Write-Host "[E2E] Report: $reportPath"

if (-not $allOk) { exit 1 }
exit 0

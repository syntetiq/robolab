<#
.SYNOPSIS
    Run MVP readiness regression gates for fixed kitchen experiments and teleop contracts.

.DESCRIPTION
    Executes non-simulation regression checks:
    - fixed experiment regressions
    - MVP task suite coverage
    - Python syntax checks for teleop-related scripts
    - TypeScript compile check (optional)
#>
param(
    [switch]$SkipTsc,
    [switch]$RunSceneFit,
    [string]$RuntimeScenesDir = "C:\RoboLab_Data\scenes",
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat"
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    Write-Host ""
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Name"
    }
}

Set-Location $RepoRoot

Invoke-Step "Fridge experiment regression" { python "scripts/test_fridge_experiment3_regression.py" }
Invoke-Step "Mug rearrange regression" { python "scripts/test_mug_rearrange_regression.py" }
Invoke-Step "Banana to sink regression" { python "scripts/test_banana_to_sink_regression.py" }
Invoke-Step "MVP task suite coverage" { python "scripts/test_mvp_task_suite_regression.py" }
Invoke-Step "Fixed baseline lock" { python "scripts/test_fixed_baseline_lock.py" }
Invoke-Step "Scene assets regression" { python "scripts/test_scene_assets_regression.py" }
Invoke-Step "Scene resolution regression" { python "scripts/test_scene_resolution_regression.py" }
Invoke-Step "Python syntax (teleop chain)" {
    python -m py_compile "scripts/servo_joint_trajectory_bridge.py" "scripts/check_object_diversity.py" "scripts/build_kitchen_scene_wrapper.py" "scripts/test_scene_assets_regression.py" "scripts/check_scene_physics_coverage.py" "scripts/scene_fit_validator.py" "scripts/test_fixed_baseline_lock.py" "scripts/test_scene_resolution_regression.py"
}
Invoke-Step "PowerShell parse (teleop + task runners)" {
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile("scripts/run_vr_teleop.ps1", [ref]$null, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) { $errors | ForEach-Object { throw $_.Message } }
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile("scripts/run_all_task_configs.ps1", [ref]$null, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) { $errors | ForEach-Object { throw $_.Message } }
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile("scripts/prepare_office_scene_assets.ps1", [ref]$null, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) { $errors | ForEach-Object { throw $_.Message } }
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile("scripts/run_scene_fit_validations.ps1", [ref]$null, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) { $errors | ForEach-Object { throw $_.Message } }
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile("scripts/run_e2e_scene_sanity.ps1", [ref]$null, [ref]$errors) | Out-Null
    if ($errors.Count -gt 0) { $errors | ForEach-Object { throw $_.Message } }
}

Invoke-Step "Scene physics coverage (wrapper contract)" {
    python "scripts/check_scene_physics_coverage.py" --runtime-scenes-dir "$RuntimeScenesDir"
}

if ($RunSceneFit) {
    Invoke-Step "Strict scene-fit validation (Office/Kitchen)" {
        powershell -ExecutionPolicy Bypass -File "scripts/run_scene_fit_validations.ps1" -RuntimeScenesDir "$RuntimeScenesDir" -IsaacPython "$IsaacPython"
    }
}

if (-not $SkipTsc) {
    Invoke-Step "TypeScript compile check" { npx tsc --noEmit }
}

Write-Host ""
Write-Host "[OK] MVP readiness non-simulation gates passed." -ForegroundColor Green

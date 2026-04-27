<#
.SYNOPSIS
    Run fixed kitchen task-config scenarios with video recording.

.DESCRIPTION
    Runs all configs matching config/tasks/fixed_*.json in stable sort order.
    Use -Include to run a subset by wildcard.
    Output: C:\RoboLab_Data\episodes\<episode_name>_<timestamp>\

.PARAMETER Output
    Base directory for episode folders. Default: C:\RoboLab_Data\episodes

.PARAMETER Include
    Optional wildcard filter (e.g. *fridge* or *mug*).

.EXAMPLE
    .\scripts\run_all_task_configs.ps1
    .\scripts\run_all_task_configs.ps1 -Include *fridge*
#>
param(
    [string]$Output = "C:\RoboLab_Data\episodes",
    [string]$Include = "*"
)

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Split-Path -Parent $ScriptRoot
$RunTask    = Join-Path $ScriptRoot "run_task_config.ps1"

$configs = Get-ChildItem -Path (Join-Path $RepoRoot "config/tasks") -Filter "fixed_*.json" |
    Where-Object { $_.Name -like $Include } |
    Sort-Object Name |
    ForEach-Object { "config/tasks/$($_.Name)" }

if ($configs.Count -eq 0) {
    Write-Error "No task configs matched filter '$Include' in config/tasks/fixed_*.json"
    exit 1
}

$total = $configs.Count
$failed = @()
$n = 0
foreach ($cfg in $configs) {
    $n++
    $cfgPath = if ([System.IO.Path]::IsPathRooted($cfg)) { $cfg } else { Join-Path $RepoRoot $cfg }
    Write-Host ""
    Write-Host "========== [$n/$total] $cfg ==========" -ForegroundColor Cyan
    & $RunTask -Config $cfgPath -Output $Output
    if ($LASTEXITCODE -ne 0) {
        $failed += $cfg
    }
}

Write-Host ""
Write-Host "=========================================="
Write-Host "  All runs finished"
Write-Host "  Passed: $($total - $failed.Count)/$total"
if ($failed.Count -gt 0) {
    Write-Host "  Failed configs:" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    exit 1
}
Write-Host "=========================================="
exit 0

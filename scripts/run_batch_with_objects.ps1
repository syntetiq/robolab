<#
.SYNOPSIS
    Batch data collection: 5 task scenarios x N scenes, with diverse object spawning.
    Runs each combination as a standalone MoveIt smoke test episode.

.USAGE
    .\scripts\run_batch_with_objects.ps1
    .\scripts\run_batch_with_objects.ps1 -DurationSec 60 -CooldownSec 30
#>
param(
    [int]$DurationSec = 50,
    [int]$CooldownSec = 45,
    [string]$ObjectsDir = "C:\RoboLab_Data\data\object_sets",
    [string]$TiagoUsd = "C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional.usd",
    [string]$OrchestratorScript = ""
)

$ErrorActionPreference = "Continue"
$pfx = "[BatchObj]"
$ScriptsDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $ScriptsDir

if (-not $OrchestratorScript) {
    $OrchestratorScript = Join-Path $ScriptsDir "run_tiago_moveit_execute_smoke.ps1"
}

$scenarios = @(
    "plan_pick_sink",
    "plan_pick_fridge",
    "plan_pick_dishwasher",
    "open_close_fridge",
    "open_close_dishwasher"
)

$scenes = @(
    @{ Name = "Small_House"; Path = "C:\RoboLab_Data\scenes\Small_House_Interactive.usd" },
    @{ Name = "Office"; Path = "C:\RoboLab_Data\scenes\Office_Interactive.usd" },
    @{ Name = "Kitchen"; Path = "C:\RoboLab_Data\scenes\Kitchen_TiagoCompatible.usda" }
)

$validScenes = $scenes | Where-Object { Test-Path $_.Path }
if ($validScenes.Count -eq 0) {
    Write-Host "$pfx ERROR: No valid scenes found!"
    exit 1
}

$totalRuns = $scenarios.Count * $validScenes.Count
$runIdx = 0
$results = [System.Collections.Generic.List[object]]::new()

$objCount = 0
if (Test-Path $ObjectsDir) {
    $objCount = (Get-ChildItem $ObjectsDir -Filter "*.usd*").Count
}

Write-Host "$pfx =============================================="
Write-Host "$pfx  Batch Data Collection with Object Diversity"
Write-Host "$pfx =============================================="
Write-Host "$pfx Scenarios: $($scenarios.Count)"
Write-Host "$pfx Scenes: $($validScenes.Count) ($($validScenes | ForEach-Object { $_.Name }))"
Write-Host "$pfx Total runs: $totalRuns"
Write-Host "$pfx Duration per run: ${DurationSec}s"
Write-Host "$pfx Object assets: $objCount"
Write-Host "$pfx Cooldown: ${CooldownSec}s"
Write-Host ""

foreach ($scene in $validScenes) {
    foreach ($scenario in $scenarios) {
        $runIdx++
        $runLabel = "$($scene.Name) / $scenario"
        Write-Host ""
        Write-Host ("=" * 60)
        Write-Host "$pfx [$runIdx/$totalRuns] $runLabel"
        Write-Host ("=" * 60)

        $startTime = Get-Date
        $exitCode = -1
        try {
            & powershell.exe -ExecutionPolicy Bypass -File $OrchestratorScript `
                -Duration $DurationSec `
                -Intent $scenario `
                -EnvUsd $scene.Path `
                -TiagoUsd $TiagoUsd `
                -SpawnObjects `
                -ObjectsDir $ObjectsDir `
                -IntentDelaySec 10 `
                -IntentResultTimeoutSec 35 `
                -MaxRetriesPerIntent 2
            $exitCode = $LASTEXITCODE
        } catch {
            Write-Host "$pfx ERROR: $_"
            $exitCode = -99
        }

        $elapsed = [Math]::Round(((Get-Date) - $startTime).TotalSeconds)
        $status = if ($exitCode -eq 0) { "OK" } else { "FAIL(exit=$exitCode)" }
        Write-Host "$pfx [$runIdx/$totalRuns] $runLabel -> $status (${elapsed}s)"

        $results.Add([PSCustomObject]@{
            Run      = $runIdx
            Scene    = $scene.Name
            Scenario = $scenario
            Status   = $status
            Elapsed  = "${elapsed}s"
        })

        if ($runIdx -lt $totalRuns -and $exitCode -eq 0) {
            Write-Host "$pfx Cooldown ${CooldownSec}s..."
            Start-Sleep -Seconds $CooldownSec
        } elseif ($exitCode -ne 0) {
            Write-Host "$pfx Skipping cooldown after failure, proceeding..."
            Start-Sleep -Seconds 10
        }
    }
}

Write-Host ""
Write-Host ("=" * 60)
Write-Host "$pfx BATCH RESULTS ($totalRuns runs)"
Write-Host ("=" * 60)
$results | Format-Table -AutoSize
$ok = ($results | Where-Object { $_.Status -eq "OK" }).Count
$fail = $totalRuns - $ok
Write-Host "$pfx Passed: $ok / $totalRuns"
if ($fail -gt 0) {
    Write-Host "$pfx Failed: $fail"
    $results | Where-Object { $_.Status -ne "OK" } | Format-Table -AutoSize
}

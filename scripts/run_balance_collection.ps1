<#
.SYNOPSIS
    Balance dataset: run targeted batch collection on under-represented scenes.
    Aims for a minimum number of episodes per scene per intent.

.USAGE
    .\scripts\run_balance_collection.ps1
    .\scripts\run_balance_collection.ps1 -TargetPerScenePerIntent 5 -DurationSec 50
#>
param(
    [int]$TargetPerScenePerIntent = 5,
    [int]$DurationSec = 50,
    [int]$CooldownSec = 45,
    [string]$ObjectsDir = "C:\RoboLab_Data\data\object_sets",
    [string]$TiagoUsd = "C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional.usd",
    [string]$OrchestratorScript = "",
    [string]$EpisodesDir = "C:\RoboLab_Data\episodes"
)

$ErrorActionPreference = "Continue"
$pfx = "[Balance]"
$ScriptsDir = $PSScriptRoot

if (-not $OrchestratorScript) {
    $OrchestratorScript = Join-Path $ScriptsDir "run_tiago_moveit_execute_smoke.ps1"
}

$intents = @(
    "plan_pick_sink",
    "plan_pick_fridge",
    "plan_pick_dishwasher",
    "open_close_fridge",
    "open_close_dishwasher"
)

$scenes = @(
    @{ Name = "Kitchen";        Path = "C:\RoboLab_Data\scenes\Kitchen_TiagoCompatible.usda";
       DBName = "Kitchen USDZ (Task-ready)" },
    @{ Name = "L_Kitchen";      Path = "C:\RoboLab_Data\scenes\L-Shaped_Contemporary_Modular_Kitchen_TiagoCompatible.usda";
       DBName = "L-Shaped Modular Kitchen USDZ" },
    @{ Name = "Modern_Kitchen"; Path = "C:\RoboLab_Data\scenes\Modern_Kitchen_TiagoCompatible.usda";
       DBName = "Modern Kitchen USDZ" },
    @{ Name = "Small_House";    Path = "C:\RoboLab_Data\scenes\Small_House_Interactive.usd";
       DBName = "Home Kitchen" }
)

$validScenes = $scenes | Where-Object { Test-Path $_.Path }

# Count existing episodes per scene from disk (scan metadata.json for task info).
function Count-ExistingEpisodes {
    param([string]$SceneName)
    $count = 0
    if (Test-Path $EpisodesDir) {
        Get-ChildItem $EpisodesDir -Directory | ForEach-Object {
            $metaFile = Join-Path $_.FullName "metadata.json"
            if (Test-Path $metaFile) {
                try {
                    $meta = Get-Content $metaFile -Raw | ConvertFrom-Json
                    $sceneMeta = $meta.scene.name
                    if (-not $sceneMeta) { $sceneMeta = $meta.sceneName }
                    if ($sceneMeta -eq $SceneName) { $count++ }
                } catch {}
            }
        }
    }
    return $count
}

# Build the run plan: which (scene, intent) combos need more episodes.
$plan = [System.Collections.Generic.List[object]]::new()

Write-Host "$pfx =============================================="
Write-Host "$pfx  Dataset Balancing Collection"
Write-Host "$pfx  Target: $TargetPerScenePerIntent eps/scene/intent"
Write-Host "$pfx =============================================="
Write-Host ""

foreach ($scene in $validScenes) {
    $existing = Count-ExistingEpisodes -SceneName $scene.DBName
    $perIntent = [math]::Floor($existing / $intents.Count)
    $deficit = [math]::Max(0, $TargetPerScenePerIntent - $perIntent)

    Write-Host "$pfx $($scene.Name): $existing existing (~$perIntent/intent), deficit=$deficit/intent"

    if ($deficit -gt 0) {
        foreach ($intent in $intents) {
            for ($r = 0; $r -lt $deficit; $r++) {
                $plan.Add([PSCustomObject]@{
                    Scene  = $scene
                    Intent = $intent
                    Rep    = $r + 1
                })
            }
        }
    }
}

$totalRuns = $plan.Count
if ($totalRuns -eq 0) {
    Write-Host ""
    Write-Host "$pfx All scenes already balanced! Nothing to do."
    exit 0
}

Write-Host ""
Write-Host "$pfx Planned runs: $totalRuns"
Write-Host "$pfx Estimated time: $([math]::Round($totalRuns * ($DurationSec + $CooldownSec) / 60)) min"
Write-Host ""

$runIdx = 0
$results = [System.Collections.Generic.List[object]]::new()

foreach ($run in $plan) {
    $runIdx++
    $scene = $run.Scene
    $intent = $run.Intent
    $runLabel = "$($scene.Name) / $intent (rep $($run.Rep))"

    Write-Host ""
    Write-Host ("=" * 60)
    Write-Host "$pfx [$runIdx/$totalRuns] $runLabel"
    Write-Host ("=" * 60)

    $startTime = Get-Date
    $exitCode = -1
    try {
        & powershell.exe -ExecutionPolicy Bypass -File $OrchestratorScript `
            -Duration $DurationSec `
            -Intent $intent `
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
        Intent   = $intent
        Rep      = $run.Rep
        Status   = $status
        Elapsed  = "${elapsed}s"
    })

    if ($runIdx -lt $totalRuns -and $exitCode -eq 0) {
        Write-Host "$pfx Cooldown ${CooldownSec}s..."
        Start-Sleep -Seconds $CooldownSec
    } elseif ($exitCode -ne 0) {
        Write-Host "$pfx Skipping cooldown after failure..."
        Start-Sleep -Seconds 10
    }
}

Write-Host ""
Write-Host ("=" * 60)
Write-Host "$pfx BALANCE RESULTS ($totalRuns runs)"
Write-Host ("=" * 60)
$results | Format-Table -AutoSize
$ok = ($results | Where-Object { $_.Status -eq "OK" }).Count
$fail = $totalRuns - $ok
Write-Host "$pfx Passed: $ok / $totalRuns"
if ($fail -gt 0) {
    Write-Host "$pfx Failed: $fail"
    $results | Where-Object { $_.Status -ne "OK" } | Format-Table -AutoSize
}

Write-Host ""
Write-Host "$pfx Final distribution:"
foreach ($scene in $validScenes) {
    $total = Count-ExistingEpisodes -SceneName $scene.DBName
    Write-Host "$pfx   $($scene.Name): $total episodes"
}

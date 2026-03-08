<#
.SYNOPSIS
    Mass data collection: runs N episodes for each of the 6 scenarios.
    Keeps only the 20 most recent episodes (pruneOldEpisodes runs on every start).

.USAGE
    .\scripts\run_mass_collection.ps1
    .\scripts\run_mass_collection.ps1 -EpisodesPerScenario 5 -DurationSec 480
#>
param(
    [int]$EpisodesPerScenario = 3,
    [int]$DurationSec         = 0,        # 0 = use per-scenario duration map
    [int]$CooldownSec         = 90,       # wait between episodes (GPU cooldown)
    [string]$ApiBase          = "http://localhost:3000",
    [string]$SceneId          = "c6830f5e-3c89-4a5a-9d15-f9de401ad9a6",  # Home Kitchen
    [string]$OrchestratorScript = "$PSScriptRoot\run_tiago_moveit_execute_smoke.ps1"
)

$ErrorActionPreference = "Stop"
$pfx = "[MassCollect]"

$scenarios = @(
    "approach_workzone",
    "plan_pick_sink",
    "plan_pick_fridge",
    "plan_pick_dishwasher",
    "open_close_fridge",
    "open_close_dishwasher"
)

# Duration map: simpler scenarios need less time.
$durationMap = @{
    "approach_workzone"    = 180
    "plan_pick_sink"       = 300
    "plan_pick_fridge"     = 480
    "plan_pick_dishwasher" = 480
    "open_close_fridge"    = 480
    "open_close_dishwasher"= 480
}

$totalRuns = $scenarios.Count * $EpisodesPerScenario
$runIdx    = 0
$results   = [System.Collections.Generic.List[object]]::new()

Write-Host "$pfx Starting mass collection: $EpisodesPerScenario eps x $($scenarios.Count) scenarios = $totalRuns total"
Write-Host "$pfx API: $ApiBase"
Write-Host "$pfx Cooldown between runs: $CooldownSec s"
Write-Host ""

foreach ($scenario in $scenarios) {
    $dur = if ($DurationSec -gt 0) { $DurationSec } else { $durationMap[$scenario] }

    for ($ep = 1; $ep -le $EpisodesPerScenario; $ep++) {
        $runIdx++
        Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        Write-Host "$pfx [$runIdx/$totalRuns] Scenario=$scenario  Episode=$ep/$EpisodesPerScenario  Duration=${dur}s"
        Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        # ── Step 1: Create episode via API ──────────────────────────────────
        $episodeId = $null
        try {
            $body = @{ name = "$scenario ep$ep"; durationSec = $dur; sceneId = $SceneId } | ConvertTo-Json
            $resp = Invoke-RestMethod -Uri "$ApiBase/api/episodes" -Method POST `
                        -Body $body -ContentType "application/json" -TimeoutSec 30
            $episodeId = $resp.id
            Write-Host "$pfx Created episode $episodeId"
        } catch {
            Write-Host "$pfx ERROR creating episode: $_"
            $results.Add([PSCustomObject]@{
                Scenario=$scenario; Episode=$ep; EpisodeId="N/A"; Status="create_failed"; Error="$_"
            })
            continue
        }

        # ── Step 2: Start orchestration ──────────────────────────────────────
        try {
            $orchBody = @{
                intent      = $scenario
                durationSec = $dur
                force       = $true
            } | ConvertTo-Json
            $orchResp = Invoke-RestMethod `
                -Uri "$ApiBase/api/episodes/$episodeId/orchestration" `
                -Method POST -Body $orchBody -ContentType "application/json" -TimeoutSec 60
            Write-Host "$pfx Orchestration started (pid=$($orchResp.pid))"
        } catch {
            Write-Host "$pfx ERROR starting orchestration: $_"
            $results.Add([PSCustomObject]@{
                Scenario=$scenario; Episode=$ep; EpisodeId=$episodeId; Status="orch_failed"; Error="$_"
            })
            continue
        }

        # ── Step 3: Poll until done ──────────────────────────────────────────
        $pollDeadline = [DateTime]::UtcNow.AddSeconds($dur + 120)
        $orchStatus   = "unknown"
        $intentResult = "unknown"

        while ([DateTime]::UtcNow -lt $pollDeadline) {
            Start-Sleep -Seconds 15
            try {
                $poll = Invoke-RestMethod `
                    -Uri "$ApiBase/api/episodes/$episodeId/orchestration" `
                    -Method GET -TimeoutSec 20
                $orchStatus   = $poll.status
                $intentResult = $poll.intentResult
                Write-Host "$pfx   poll → status=$orchStatus intentResult=$intentResult"
                if ($orchStatus -in @("succeeded", "failed", "timeout")) { break }
            } catch {
                Write-Host "$pfx   poll error (non-fatal): $_"
            }
        }

        $epStatus = if ($orchStatus -eq "succeeded") { "ok" } else { "failed:$orchStatus" }
        Write-Host "$pfx Episode $episodeId finished → $epStatus (intentResult=$intentResult)"

        $results.Add([PSCustomObject]@{
            Scenario=$scenario; Episode=$ep; EpisodeId=$episodeId
            Status=$epStatus; IntentResult=$intentResult; Duration=$dur
        })

        # ── Step 4: Cooldown between episodes ───────────────────────────────
        if ($runIdx -lt $totalRuns) {
            Write-Host "$pfx Cooling down ${CooldownSec}s before next episode..."
            Start-Sleep -Seconds $CooldownSec
        }
    }
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "$pfx SUMMARY ($runIdx runs)"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
$results | Format-Table -AutoSize
$ok = ($results | Where-Object { $_.Status -eq "ok" }).Count
Write-Host "$pfx Success: $ok / $runIdx"

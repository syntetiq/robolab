<#
.SYNOPSIS
    Top-up collection: run specific scenarios to fill gaps.
#>
param(
    [string]$ApiBase = "http://localhost:3000",
    [string]$SceneId = "c6830f5e-3c89-4a5a-9d15-f9de401ad9a6",
    [int]$CooldownSec = 90
)

$ErrorActionPreference = "Stop"
$pfx = "[TopUp]"

$runs = @(
    @{ scenario = "approach_workzone"; dur = 180 },
    @{ scenario = "approach_workzone"; dur = 180 },
    @{ scenario = "open_close_fridge"; dur = 480 }
)

$totalRuns = $runs.Count
$runIdx = 0
$results = [System.Collections.Generic.List[object]]::new()

Write-Host "$pfx Starting top-up: $totalRuns episodes"

foreach ($run in $runs) {
    $runIdx++
    $scenario = $run.scenario
    $dur = $run.dur
    Write-Host ""
    Write-Host "$pfx [$runIdx/$totalRuns] $scenario ${dur}s"

    # Create episode
    $body = @{ name = "topup $scenario"; durationSec = $dur; sceneId = $SceneId } | ConvertTo-Json
    $resp = Invoke-RestMethod -Uri "$ApiBase/api/episodes" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 30
    $epId = $resp.id
    Write-Host "$pfx  Episode: $epId"

    # Start orchestration
    $orchBody = @{ intent = $scenario; durationSec = $dur; force = $true } | ConvertTo-Json
    $orchResp = Invoke-RestMethod -Uri "$ApiBase/api/episodes/$epId/orchestration" -Method POST -Body $orchBody -ContentType "application/json" -TimeoutSec 60
    Write-Host "$pfx  Orchestration pid=$($orchResp.pid)"

    # Poll
    $deadline = [DateTime]::UtcNow.AddSeconds($dur + 180)
    $status = "unknown"
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 15
        try {
            $poll = Invoke-RestMethod -Uri "$ApiBase/api/episodes/$epId/orchestration" -Method GET -TimeoutSec 20
            $status = $poll.status
            Write-Host "$pfx  status=$status"
            if ($status -in @("succeeded", "failed", "timeout")) { break }
        } catch {
            Write-Host "$pfx  poll error: $_"
        }
    }

    $epStatus = if ($status -eq "succeeded") { "ok" } else { "FAIL:$status" }
    Write-Host "$pfx  -> $epStatus"
    $results.Add([PSCustomObject]@{ Scenario=$scenario; EpisodeId=$epId; Status=$epStatus })

    if ($runIdx -lt $totalRuns) {
        Write-Host "$pfx  Cooldown ${CooldownSec}s..."
        Start-Sleep -Seconds $CooldownSec
    }
}

Write-Host ""
Write-Host "$pfx SUMMARY:"
$results | Format-Table -AutoSize
$ok = ($results | Where-Object { $_.Status -eq "ok" }).Count
Write-Host "$pfx $ok / $totalRuns succeeded"

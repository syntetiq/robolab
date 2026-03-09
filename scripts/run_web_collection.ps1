<#
.SYNOPSIS
    Run data collection through the web app API with full MoveIt pipeline.
    Creates episodes visible in the UI, starts MoveGroup+FJT proxy externally,
    and publishes MoveIt intents for each episode.

.USAGE
    .\scripts\run_web_collection.ps1
    .\scripts\run_web_collection.ps1 -SceneCount 3 -DurationSec 50
#>
param(
    [string]$ApiBase = "http://localhost:3000/api",
    [int]$DurationSec = 50,
    [string[]]$Intents = @("plan_pick_sink","plan_pick_fridge","open_close_fridge"),
    [int]$SceneCount = 3,
    [int]$CooldownSec = 40,
    [int]$IntentDelaySec = 12,
    [string]$RosSetup = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat",
    [string]$PyExe = "C:\Users\max\Mambaforge\envs\ros2_humble\python.exe",
    [string]$MoveGroupExe = "C:\Users\max\Mambaforge\envs\ros2_humble\Scripts\ros2.exe"
)

$ErrorActionPreference = "Continue"
$pfx = "[WebColl]"
$ScriptsDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $ScriptsDir
$LogDir = Join-Path $RepoRoot "logs\web_collection\$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Invoke-Api {
    param([string]$Method, [string]$Path, [object]$Body = $null)
    $uri = "$ApiBase$Path"
    $params = @{ Method = $Method; Uri = $uri; ContentType = "application/json" }
    if ($Body) { $params["Body"] = ($Body | ConvertTo-Json -Depth 5) }
    try {
        return Invoke-RestMethod @params
    } catch {
        Write-Host "$pfx API error ($Method $Path): $_" -ForegroundColor Red
        return $null
    }
}

# ── Verify API ──
$scenes = Invoke-Api -Method GET -Path "/scenes"
if (-not $scenes) {
    Write-Host "$pfx ERROR: Cannot reach API at $ApiBase/scenes"
    exit 1
}
$sceneList = $scenes | Select-Object -First $SceneCount

# ── Find/create MoveIt launch profile ──
$profiles = Invoke-Api -Method GET -Path "/launch-profiles"
$moveitProfile = $profiles | Where-Object {
    $_.enableMoveIt -eq $true -and $_.runnerMode -eq "LOCAL_RUNNER" -and
    $_.scriptName -eq "data_collector_tiago.py" -and $_.enableVrTeleop -ne $true
} | Select-Object -First 1

if (-not $moveitProfile) {
    Write-Host "$pfx Creating MoveIt launch profile..."
    $moveitProfile = Invoke-Api -Method POST -Path "/launch-profiles" -Body @{
        name = "MoveIt Data Collection"
        runnerMode = "LOCAL_RUNNER"
        scriptName = "data_collector_tiago.py"
        enableMoveIt = $true
        enableWebRTC = $false
        enableVrTeleop = $false
        robotPovCameraPrim = "/World/Tiago"
        ros2SetupCommand = "call $RosSetup"
    }
    if (-not $moveitProfile) {
        Write-Host "$pfx WARN: Could not create launch profile, proceeding without one"
    }
}
$profileId = $moveitProfile.id
Write-Host "$pfx Using launch profile: $($moveitProfile.name) ($profileId)"

# ── Start MoveGroup + FJT Proxy + Intent Bridge ──
Write-Host "$pfx Starting ROS2 support processes..."

$moveGroupYaml = Join-Path $ScriptsDir "tiago_move_group_working.yaml"
$fjtProxy = Join-Path $ScriptsDir "ros2_fjt_proxy.py"
$intentBridge = Join-Path $ScriptsDir "moveit_intent_bridge.py"

$mgBat = Join-Path $LogDir "run_mg.bat"
Set-Content $mgBat "@echo off`r`ncall `"$RosSetup`"`r`n`"$MoveGroupExe`" run moveit_ros_move_group move_group --ros-args --params-file `"$moveGroupYaml`""

$fjtBat = Join-Path $LogDir "run_fjt.bat"
Set-Content $fjtBat "@echo off`r`ncall `"$RosSetup`"`r`n`"$PyExe`" `"$fjtProxy`""

$bridgeBat = Join-Path $LogDir "run_bridge.bat"
Set-Content $bridgeBat "@echo off`r`ncall `"$RosSetup`"`r`n`"$PyExe`" `"$intentBridge`" --robot tiago --planning-group arm_torso --frame-id base_footprint"

$mgProc = Start-Process -PassThru -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/c `"$mgBat`"" `
    -RedirectStandardOutput (Join-Path $LogDir "move_group.stdout.log") `
    -RedirectStandardError  (Join-Path $LogDir "move_group.stderr.log")
Write-Host "$pfx Started move_group pid=$($mgProc.Id)"

Start-Sleep -Seconds 10
$fjtProc = Start-Process -PassThru -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/c `"$fjtBat`"" `
    -RedirectStandardOutput (Join-Path $LogDir "fjt_proxy.stdout.log") `
    -RedirectStandardError  (Join-Path $LogDir "fjt_proxy.stderr.log")
Write-Host "$pfx Started fjt_proxy pid=$($fjtProc.Id)"

Start-Sleep -Seconds 5
$bridgeProc = Start-Process -PassThru -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/c `"$bridgeBat`"" `
    -RedirectStandardOutput (Join-Path $LogDir "bridge.stdout.log") `
    -RedirectStandardError  (Join-Path $LogDir "bridge.stderr.log")
Write-Host "$pfx Started intent_bridge pid=$($bridgeProc.Id)"

Start-Sleep -Seconds 5

# ── Helper: publish intent via ROS2 ──
function Publish-Intent {
    param([string]$Intent)
    $pubBat = Join-Path $LogDir "pub_intent.bat"
    Set-Content $pubBat "@echo off`r`ncall `"$RosSetup`"`r`n`"$MoveGroupExe`" topic pub --once /tiago/moveit/intent std_msgs/msg/String `"{data: '$Intent'}`""
    $p = Start-Process -PassThru -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/c `"$pubBat`"" `
        -RedirectStandardOutput (Join-Path $LogDir "pub.stdout.log") `
        -RedirectStandardError  (Join-Path $LogDir "pub.stderr.log")
    $p | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue
}

# ── Collection loop ──
Write-Host ""
Write-Host "$pfx =========================================="
Write-Host "$pfx  Web App Data Collection with MoveIt"
Write-Host "$pfx =========================================="
Write-Host "$pfx Scenes: $($sceneList.Count)"
Write-Host "$pfx Intents: $($Intents -join ', ')"
Write-Host "$pfx Duration: ${DurationSec}s | Cooldown: ${CooldownSec}s"
Write-Host ""

$totalEpisodes = $sceneList.Count * $Intents.Count
$runIdx = 0
$results = [System.Collections.Generic.List[object]]::new()

foreach ($scene in $sceneList) {
    foreach ($intent in $Intents) {
        $runIdx++
        $label = "$($scene.name) / $intent"
        Write-Host ""
        Write-Host ("=" * 60)
        Write-Host "$pfx [$runIdx/$totalEpisodes] $label"
        Write-Host ("=" * 60)

        # Create episode via API
        $body = @{
            sceneId = $scene.id
            launchProfileId = $profileId
            tasks = "[`"$intent`"]"
            durationSec = $DurationSec
            notes = "Web collection | $intent | $($scene.name)"
        }
        $episode = Invoke-Api -Method POST -Path "/episodes" -Body $body
        if (-not $episode -or -not $episode.id) {
            Write-Host "$pfx FAIL: Could not create episode"
            $results.Add([PSCustomObject]@{ Run=$runIdx; Scene=$scene.name; Intent=$intent; Status="CREATE_FAIL"; EpisodeId="" })
            continue
        }
        $epId = $episode.id
        Write-Host "$pfx Created episode: $epId"

        # Start episode via API (launches Isaac Sim data collector)
        $startResult = Invoke-Api -Method POST -Path "/episodes/$epId/start"
        if (-not $startResult) {
            Write-Host "$pfx FAIL: Could not start episode $epId"
            $results.Add([PSCustomObject]@{ Run=$runIdx; Scene=$scene.name; Intent=$intent; Status="START_FAIL"; EpisodeId=$epId })
            continue
        }
        Write-Host "$pfx Started episode $epId (Isaac Sim launching...)"

        # Wait for Isaac Sim to initialize before publishing intents
        Write-Host "$pfx Waiting ${IntentDelaySec}s for sim initialization..."
        Start-Sleep -Seconds $IntentDelaySec

        # Publish go_home then the actual intent
        Write-Host "$pfx Publishing go_home..."
        Publish-Intent -Intent "go_home"
        Start-Sleep -Seconds 8
        Write-Host "$pfx Publishing $intent..."
        Publish-Intent -Intent $intent

        # Wait for episode to complete
        $maxWait = $DurationSec + 90
        $elapsed = 0
        $finalStatus = "unknown"
        while ($elapsed -lt $maxWait) {
            Start-Sleep -Seconds 10
            $elapsed += 10
            $ep = Invoke-Api -Method GET -Path "/episodes/$epId"
            if ($ep) {
                $finalStatus = $ep.status
                if ($finalStatus -in @("completed", "stopped", "failed")) { break }
            }
            if ($elapsed % 30 -eq 0) {
                Write-Host "$pfx   ... waiting ($elapsed/${maxWait}s) status=$finalStatus"
            }
        }

        $statusLabel = if ($finalStatus -in @("completed", "stopped")) { "OK" } else { "FAIL($finalStatus)" }
        Write-Host "$pfx [$runIdx/$totalEpisodes] $label -> $statusLabel (episode=$epId)"

        $results.Add([PSCustomObject]@{
            Run = $runIdx
            Scene = $scene.name
            Intent = $intent
            Status = $statusLabel
            EpisodeId = $epId
        })

        # Sync episode data to public/
        if ($finalStatus -in @("completed", "stopped")) {
            $syncResult = Invoke-Api -Method POST -Path "/episodes/$epId/sync"
            if ($syncResult) { Write-Host "$pfx Synced episode to web UI" }
        }

        if ($runIdx -lt $totalEpisodes) {
            Write-Host "$pfx Cooldown ${CooldownSec}s..."
            Start-Sleep -Seconds $CooldownSec
        }
    }
}

# ── Cleanup ──
Write-Host ""
Write-Host "$pfx Stopping ROS2 support processes..."
@($bridgeProc, $fjtProc, $mgProc) | ForEach-Object {
    if ($_ -and -not $_.HasExited) {
        try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
}

Write-Host ""
Write-Host ("=" * 60)
Write-Host "$pfx RESULTS ($totalEpisodes episodes)"
Write-Host ("=" * 60)
$results | Format-Table -AutoSize
$ok = ($results | Where-Object { $_.Status -eq "OK" }).Count
$fail = $totalEpisodes - $ok
Write-Host "$pfx Passed: $ok / $totalEpisodes"
if ($fail -gt 0) {
    Write-Host "$pfx Failed: $fail"
}
Write-Host "$pfx Logs: $LogDir"

param(
    $RosSetupArg,
    $PyExeArg,
    $PubScriptArg,
    $IntentListArg,
    $DelaySec,
    $BridgeErrPathArg,
    $ResultTimeoutArg,
    $MaxRetriesArg,
    $PreGoHomeArg,
    $RetryMinus4Arg,
    $WarmupGoHomeArg
)

Start-Sleep -Seconds $DelaySec
$baseEnv = 'set HOME=C:\Users\max&& set ROS_DOMAIN_ID=0&& set ROS_LOCALHOST_ONLY=0&& call ' + $RosSetupArg + ' &&'

# Wait for joint_state.json (written by Isaac Sim, read by FJT proxy).
# This is faster and more reliable than polling ros2 topic info inside Start-Job.
$jsFile = "C:\RoboLab_Data\fjt_proxy\joint_state.json"
$ready = $false
for ($i = 0; $i -lt 120; $i++) {
    if (Test-Path $jsFile) {
        $ready = $true
        Write-Output "[ExecSmokeJob] Prereqs ready: joint_state.json exists (iter $i)"
        break
    }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) {
    Write-Output "[ExecSmokeJob] joint_state.json not found after 60s - proceeding anyway"
}
Start-Sleep -Seconds 3

function Wait-ForBridgeResultFromOffset {
    param(
        [string]$BridgePath,
        [int]$Offset,
        [int]$TimeoutSec
    )
    $off = [Math]::Max(0, $Offset)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        if (Test-Path $BridgePath) {
            $lines = Get-Content -Path $BridgePath -ErrorAction SilentlyContinue
            if ($lines -and $lines.Count -gt $off) {
                for ($idx = $off; $idx -lt $lines.Count; $idx++) {
                    $ln = $lines[$idx]
                    if ($ln -match "MoveGroup goal succeeded") {
                        return @{ Success = $true; Code = 1; Offset = $idx + 1; Message = "MoveGroup goal succeeded" }
                    }
                    if ($ln -match "MoveGroup goal finished with code") {
                        $parts = $ln -split "code "
                        $c = if ($parts.Count -gt 1) { [int]($parts[1].Trim().Split()[0]) } else { -99 }
                        return @{ Success = $false; Code = $c; Offset = $idx + 1; Message = "MoveGroup goal finished with code $c" }
                    }
                }
                $off = $lines.Count
            }
        }
        Start-Sleep -Milliseconds 300
    }
    return @{ Success = $false; Code = 0; Offset = $off; Message = "Timeout waiting for MoveGroup result in bridge log" }
}

function Wait-ForBridgeIntentAckFromOffset {
    param(
        [string]$BridgePath,
        [int]$Offset,
        [string]$IntentName,
        [int]$TimeoutSec = 6
    )
    $off = [Math]::Max(0, $Offset)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $escaped = [Regex]::Escape($IntentName)
    $pattern = "Intent received:\s*" + $escaped
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        if (Test-Path $BridgePath) {
            $lines = Get-Content -Path $BridgePath -ErrorAction SilentlyContinue
            if ($lines -and $lines.Count -gt $off) {
                for ($idx = $off; $idx -lt $lines.Count; $idx++) {
                    $ln = $lines[$idx]
                    if ($ln -match $pattern) {
                        return @{ Seen = $true; Offset = $idx + 1 }
                    }
                }
                $off = $lines.Count
            }
        }
        Start-Sleep -Milliseconds 200
    }
    return @{ Seen = $false; Offset = $off }
}

$sequence = New-Object System.Collections.Generic.List[string]
$intentItems = "$IntentListArg".Split(",") | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }
foreach ($intent in $intentItems) {
    if (-not $intent) { continue }
    if ($PreGoHomeArg -and $intent -ne "go_home") {
        # Skip go_home pre-stage if the previous intent is already go_home
        # (avoids "already at target" controller failures).
        $prev = if ($sequence.Count -gt 0) { $sequence[$sequence.Count - 1] } else { "" }
        if ($prev -ne "go_home") {
            $sequence.Add("go_home")
        }
    }
    $sequence.Add($intent)
}
if ($sequence.Count -eq 0) {
    $sequence.Add("go_home")
}

if ($WarmupGoHomeArg -and $sequence.Count -gt 0 -and $sequence[0] -ne "go_home") {
    Write-Output "[ExecSmokeJob] Warm-up: publish go_home before primary sequence"
    $warmupSucceeded = $false
    for ($warmAttempt = 1; $warmAttempt -le 2; $warmAttempt++) {
        cmd /d /s /c "$baseEnv $PyExeArg $PubScriptArg /tiago_test/moveit/intent go_home" | Out-Null
        $warmRes = Wait-ForBridgeResultFromOffset -BridgePath $BridgeErrPathArg -Offset 0 -TimeoutSec $ResultTimeoutArg
        if ($warmRes.Success) {
            Write-Output "[ExecSmokeJob] Warm-up result: $($warmRes.Message)"
            $warmupSucceeded = $true
            $lastSucceededIntent = "go_home"
            break
        }
        Write-Output "[ExecSmokeJob] Warm-up result: $($warmRes.Message)"
        Start-Sleep -Seconds 2
    }
    if (-not $warmupSucceeded) {
        Write-Output "[ExecSmokeJob] WARN: warm-up go_home failed; continuing with sequence"
    }
}

$offset = 0
if (Test-Path $BridgeErrPathArg) {
    $existing = Get-Content -Path $BridgeErrPathArg -ErrorAction SilentlyContinue
    if ($existing) {
        $offset = $existing.Count
    }
}

$lastSucceededIntent = ""

foreach ($intent in $sequence) {
    # Skip go_home if we just succeeded with go_home (warmup or previous stage).
    if ($intent -eq "go_home" -and $lastSucceededIntent -eq "go_home") {
        Write-Output "[ExecSmokeJob] Skipping duplicate go_home (already at home pose)"
        continue
    }
    $intentSucceeded = $false
    $attemptMax = [Math]::Max(0, [int]$MaxRetriesArg) + 1
    for ($attempt = 1; $attempt -le $attemptMax; $attempt++) {
        Write-Output "[ExecSmokeJob] Publish intent: $intent (attempt $attempt/$attemptMax)"
        cmd /d /s /c "$baseEnv $PyExeArg $PubScriptArg /tiago_test/moveit/intent $intent" | Out-Null
        $ack = Wait-ForBridgeIntentAckFromOffset -BridgePath $BridgeErrPathArg -Offset $offset -IntentName $intent -TimeoutSec 6
        $offset = $ack.Offset
        if (-not $ack.Seen) {
            Write-Output "[ExecSmokeJob] WARN: intent ack not observed for '$intent'"
            if ($attempt -lt $attemptMax) {
                Start-Sleep -Milliseconds 700
                continue
            }
        }
        $res = Wait-ForBridgeResultFromOffset -BridgePath $BridgeErrPathArg -Offset $offset -TimeoutSec $ResultTimeoutArg
        $offset = $res.Offset
        if ($res.Success) {
            Write-Output "[ExecSmokeJob] Result: $($res.Message)"
            $intentSucceeded = $true
            $lastSucceededIntent = $intent
            break
        }

        Write-Output "[ExecSmokeJob] Result: $($res.Message) (code=$($res.Code))"
        if ($attempt -lt $attemptMax) {
            Write-Output "[ExecSmokeJob] Retrying intent '$intent' (attempt $attempt/$attemptMax, code=$($res.Code))..."
            Start-Sleep -Seconds 2
            continue
        }
        break
    }

    if (-not $intentSucceeded) {
        return @{
            Success = $false
            Message = "Intent '$intent' failed after retries."
        }
    }
}

return @{
    Success = $true
    Message = "Intent sequence completed successfully."
}

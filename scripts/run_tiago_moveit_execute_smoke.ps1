param(
    [int]$Duration = 40,
    [string]$Intent = "plan_pick_sink",
    [string]$TiagoUsd = "C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional.usd",
    [switch]$UseFakeControllers,
    [switch]$RequireRealTiago,
    [int]$IntentDelaySec = 0,
    [int]$IntentResultTimeoutSec = 35,
    [string]$RosSetup = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat",
    [string]$MoveGroupExe = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\lib\moveit_ros_move_group\move_group.EXE"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$SmokeScript = Join-Path $PSScriptRoot "smoke_full_pipeline.ps1"
$BridgeScript = Join-Path $PSScriptRoot "moveit_intent_bridge.py"
$FakeControllersScript = Join-Path $PSScriptRoot "fake_tiago_trajectory_controllers.py"
$PubScript = Join-Path $PSScriptRoot "ros2_pub_string.py"
$MoveGroupYaml = Join-Path $PSScriptRoot "tiago_move_group_working.yaml"
$PyExe = "C:\Users\max\Mambaforge\envs\ros2_humble\python.exe"
$RunStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunLogDir = Join-Path $RepoRoot ("logs\exec_smoke\" + $RunStamp)
[void](New-Item -ItemType Directory -Force -Path $RunLogDir)

$started = @{}

function Stop-ProcessesByPattern {
    param(
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and ($_.CommandLine -match $Pattern)
    }
    foreach ($proc in $procs) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host "[ExecSmoke] Stopped stale $Name pid=$($proc.ProcessId)"
        }
        catch {
            Write-Host "[ExecSmoke] WARN: failed to stop stale $Name pid=$($proc.ProcessId): $($_.Exception.Message)"
        }
    }
}

function Start-LoggedCmdProcess {
    param(
        [Parameter(Mandatory = $true)][string]$CmdLine,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$StdoutPath,
        [Parameter(Mandatory = $true)][string]$StderrPath
    )
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/d /s /c $CmdLine" -PassThru -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
    Write-Host "[ExecSmoke] Started $Name pid=$($proc.Id)"
    return $proc
}

function Wait-ForLogPattern {
    param(
        [Parameter(Mandatory = $true)][string[]]$Paths,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [int]$TimeoutSec = 20,
        [string]$Name = "process"
    )
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        foreach ($path in $Paths) {
            if (Test-Path $path) {
                $text = Get-Content -Path $path -Raw -ErrorAction SilentlyContinue
                if ($text -match $Pattern) {
                    Write-Host "[ExecSmoke] $Name ready: matched '$Pattern' in $(Split-Path $path -Leaf)"
                    return $true
                }
            }
        }
        Start-Sleep -Milliseconds 250
    }
    Write-Host "[ExecSmoke] WARN: timeout waiting for $Name pattern '$Pattern'"
    return $false
}

function Wait-ForBridgeResult {
    param(
        [Parameter(Mandatory = $true)][string[]]$BridgeLogPaths,
        [int]$TimeoutSec = 35
    )
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        foreach ($path in $BridgeLogPaths) {
            if (-not (Test-Path $path)) {
                continue
            }
            $text = Get-Content -Path $path -Raw -ErrorAction SilentlyContinue
            if ($text -match "MoveGroup goal succeeded") {
                return @{
                    Success = $true
                    Message = "MoveGroup goal succeeded"
                }
            }
            if ($text -match "MoveGroup goal finished with code (-?\d+)") {
                $code = $Matches[1]
                return @{
                    Success = $false
                    Message = "MoveGroup goal finished with code $code"
                }
            }
        }
        Start-Sleep -Milliseconds 300
    }
    return @{
        Success = $false
        Message = "Timeout waiting for MoveGroup result in bridge log"
    }
}

if (-not (Test-Path $SmokeScript)) { throw "Smoke script not found: $SmokeScript" }
if (-not (Test-Path $BridgeScript)) { throw "Bridge script not found: $BridgeScript" }
if ($UseFakeControllers -and (-not (Test-Path $FakeControllersScript))) { throw "Fake controllers script not found: $FakeControllersScript" }
if (-not (Test-Path $MoveGroupYaml)) { throw "MoveGroup YAML not found: $MoveGroupYaml" }
if (-not (Test-Path $RosSetup)) { throw "ROS setup not found: $RosSetup" }
if (-not (Test-Path $MoveGroupExe)) { throw "MoveGroup exe not found: $MoveGroupExe" }
if (-not (Test-Path $PyExe)) { throw "Python exe not found: $PyExe" }

Write-Host "[ExecSmoke] Repo root: $RepoRoot"
Write-Host "[ExecSmoke] Duration: $Duration s"
Write-Host "[ExecSmoke] Intent: $Intent"
Write-Host "[ExecSmoke] Tiago USD: $TiagoUsd"
Write-Host "[ExecSmoke] Use fake controllers: $($UseFakeControllers.IsPresent)"
Write-Host "[ExecSmoke] Require real Tiago: $($RequireRealTiago.IsPresent)"
if ($IntentDelaySec -le 0) {
    $IntentDelaySec = [Math]::Max(6, [Math]::Min([int]($Duration / 3), [Math]::Max(1, $Duration - 4)))
}
Write-Host "[ExecSmoke] Intent delay: $IntentDelaySec s"
Write-Host "[ExecSmoke] Logs dir: $RunLogDir"

$CommonEnv = "set PYTHONUNBUFFERED=1&& set HOME=C:\Users\max&& set ROS_DOMAIN_ID=0&& set ROS_LOCALHOST_ONLY=0&& call $RosSetup &&"

try {
    Stop-ProcessesByPattern -Pattern "moveit_intent_bridge\.py" -Name "moveit bridge"
    Stop-ProcessesByPattern -Pattern "fake_tiago_trajectory_controllers\.py" -Name "fake trajectory controllers"
    Stop-ProcessesByPattern -Pattern "move_group\.EXE.+tiago_move_group_working\.yaml" -Name "move_group"

    $moveGroupOut = Join-Path $RunLogDir "move_group.out.log"
    $moveGroupErr = Join-Path $RunLogDir "move_group.err.log"
    $bridgeOut = Join-Path $RunLogDir "bridge.out.log"
    $bridgeErr = Join-Path $RunLogDir "bridge.err.log"

    # 1) move_group
    $MoveGroupCmd = "`"$CommonEnv $MoveGroupExe --ros-args --params-file $MoveGroupYaml`""
    $started.move_group = Start-LoggedCmdProcess -CmdLine $MoveGroupCmd -Name "move_group" -StdoutPath $moveGroupOut -StderrPath $moveGroupErr
    [void](Wait-ForLogPattern -Paths @($moveGroupOut, $moveGroupErr) -Pattern "MoveGroup context initialization complete|You can start planning now|MoveGroup debug mode is ON" -TimeoutSec 25 -Name "move_group")

    # 2) optional fake trajectory controllers
    if ($UseFakeControllers) {
        $fakeOut = Join-Path $RunLogDir "fake_ctrl.out.log"
        $fakeErr = Join-Path $RunLogDir "fake_ctrl.err.log"
        $FakeCtrlCmd = "`"$CommonEnv $PyExe $FakeControllersScript`""
        $started.fake = Start-LoggedCmdProcess -CmdLine $FakeCtrlCmd -Name "fake trajectory controllers" -StdoutPath $fakeOut -StderrPath $fakeErr
    } else {
        Write-Host "[ExecSmoke] Fake controllers disabled; expecting direct controllers from Isaac collector"
    }

    # 3) bridge in execute mode
    $BridgeCmd = "`"$CommonEnv $PyExe $BridgeScript --robot tiago --intent-topic /tiago_test/moveit/intent --planning-group arm_torso --frame-id base_footprint`""
    $started.bridge = Start-LoggedCmdProcess -CmdLine $BridgeCmd -Name "moveit bridge" -StdoutPath $bridgeOut -StderrPath $bridgeErr
    [void](Wait-ForLogPattern -Paths @($bridgeOut, $bridgeErr) -Pattern "Bridge: subscribe .+ -> action /move_action" -TimeoutSec 20 -Name "moveit bridge")

    # 4) send single intent while smoke is running
    $intentJob = Start-Job -ScriptBlock {
        param($RosSetupArg, $PyExeArg, $PubScriptArg, $IntentArg, $DelaySec)
        Start-Sleep -Seconds $DelaySec
        $baseEnv = "set HOME=C:\Users\max&& set ROS_DOMAIN_ID=0&& set ROS_LOCALHOST_ONLY=0&& call $RosSetupArg &&"
        $ready = $false
        for ($i = 0; $i -lt 30; $i++) {
            $topicInfo = cmd /d /s /c "$baseEnv ros2 topic info /joint_states 2>nul"
            $actions = cmd /d /s /c "$baseEnv ros2 action list 2>nul"
            $hasPublisher = ($topicInfo -match "Publisher count:\s+([1-9]\d*)")
            $hasArmAction = ($actions -match "/arm_controller/follow_joint_trajectory")
            $hasTorsoAction = ($actions -match "/torso_controller/follow_joint_trajectory")
            if ($hasPublisher -and $hasArmAction -and $hasTorsoAction) {
                $ready = $true
                break
            }
            Start-Sleep -Milliseconds 500
        }
        if (-not $ready) {
            Write-Output "[ExecSmokeJob] WARN: readiness timeout; publishing intent anyway"
        }
        cmd /d /s /c "$baseEnv $PyExeArg $PubScriptArg /tiago_test/moveit/intent $IntentArg"
    } -ArgumentList $RosSetup, $PyExe, $PubScript, $Intent, $IntentDelaySec

    $smokeExit = 0
    try {
        $smokeArgs = @("-ExecutionPolicy", "Bypass", "-File", $SmokeScript, "-Duration", $Duration, "-TiagoUsd", $TiagoUsd)
        if ($RequireRealTiago) {
            $smokeArgs += "-RequireRealTiago"
        }
        & powershell @smokeArgs
        $smokeExit = $LASTEXITCODE
    }
    finally {
        Receive-Job -Job $intentJob -Wait -AutoRemoveJob | Out-Null
    }

    if ($smokeExit -ne 0) {
        throw "[ExecSmoke] Smoke failed with exit code $smokeExit"
    }

    $result = Wait-ForBridgeResult -BridgeLogPaths @($bridgeOut, $bridgeErr) -TimeoutSec $IntentResultTimeoutSec
    Write-Host "[ExecSmoke] Bridge result: $($result.Message)"
    if (-not $result.Success) {
        throw "[ExecSmoke] Bridge did not report success: $($result.Message)"
    }
    Write-Host "[ExecSmoke] move_group logs: $moveGroupOut | $moveGroupErr"
    Write-Host "[ExecSmoke] bridge logs: $bridgeOut | $bridgeErr"
    if ($UseFakeControllers) {
        Write-Host "[ExecSmoke] fake controller logs: $fakeOut | $fakeErr"
    }

    Write-Host "[ExecSmoke] Done"
}
finally {
    foreach ($key in @("bridge", "fake", "move_group")) {
        if ($started.ContainsKey($key) -and $started[$key]) {
            try {
                Stop-Process -Id $started[$key].Id -Force -ErrorAction SilentlyContinue
                Write-Host "[ExecSmoke] Stopped $key pid=$($started[$key].Id)"
            }
            catch {}
        }
    }
}

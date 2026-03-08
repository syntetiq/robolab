param(
    [int]$Duration = 40,
    [string]$Intent = "plan_pick_sink",
    [string]$IntentSequence = "",
    [string]$TiagoUsd = "C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional.usd",
    [switch]$UseFakeControllers,
    [switch]$RequireRealTiago,
    [int]$IntentDelaySec = 0,
    [int]$IntentResultTimeoutSec = 35,
    [int]$MaxRetriesPerIntent = 2,
    [bool]$PreGoHomeBetweenStages = $true,
    [bool]$RetryOnCodeMinus4 = $true,
    [bool]$WarmupGoHome = $true,
    [string]$RosSetup = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat",
    [string]$MoveGroupExe = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\lib\moveit_ros_move_group\move_group.EXE"
)

$ErrorActionPreference = "Stop"
$pfx = '[ExecSmoke]'

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

# Auto-prune old log directories — keep only the 15 most recent.
$logParent = Join-Path $RepoRoot "logs\exec_smoke"
$oldLogDirs = Get-ChildItem $logParent -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -Skip 15
foreach ($old in $oldLogDirs) {
    Remove-Item $old.FullName -Recurse -Force -ErrorAction SilentlyContinue
}

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
            Write-Host "$pfx Stopped stale $Name pid=$($proc.ProcessId)"
        }
        catch {
            Write-Host "$pfx WARN: failed to stop stale $Name pid=$($proc.ProcessId): $($_.Exception.Message)"
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
    Write-Host "$pfx Started $Name pid=$($proc.Id)"
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
                    Write-Host "$pfx $Name ready: matched '$Pattern' in $(Split-Path $path -Leaf)"
                    return $true
                }
            }
        }
        Start-Sleep -Milliseconds 250
    }
    Write-Host "$pfx WARN: timeout waiting for $Name pattern '$Pattern'"
    return $false
}

function Wait-ForBridgeResult {
    param(
        [Parameter(Mandatory = $true)][string[]]$BridgeLogPaths,
        [int]$TimeoutSec = 35,
        [int]$Offset = 0
    )
    $currentOffset = [Math]::Max(0, $Offset)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        foreach ($path in $BridgeLogPaths) {
            if (-not (Test-Path $path)) {
                continue
            }
            $lines = Get-Content -Path $path -ErrorAction SilentlyContinue
            if (-not $lines) { continue }
            if ($lines.Count -le $currentOffset) { continue }
            for ($i = $currentOffset; $i -lt $lines.Count; $i++) {
                $line = $lines[$i]
                if ($line -match "MoveGroup goal succeeded") {
                    return @{
                        Success = $true
                        Message = "MoveGroup goal succeeded"
                        Code = 1
                        Offset = $i + 1
                    }
                }
                if ($line -match "MoveGroup goal finished with code (-?\d+)") {
                    $code = [int]$Matches[1]
                    return @{
                        Success = $false
                        Message = "MoveGroup goal finished with code $code"
                        Code = $code
                        Offset = $i + 1
                    }
                }
            }
            $currentOffset = $lines.Count
        }
        Start-Sleep -Milliseconds 300
    }
    return @{
        Success = $false
        Message = "Timeout waiting for MoveGroup result in bridge log"
        Code = 0
        Offset = $currentOffset
    }
}

if (-not (Test-Path $SmokeScript)) { throw "Smoke script not found: $SmokeScript" }
if (-not (Test-Path $BridgeScript)) { throw "Bridge script not found: $BridgeScript" }
if ($UseFakeControllers -and (-not (Test-Path $FakeControllersScript))) { throw "Fake controllers script not found: $FakeControllersScript" }
if (-not (Test-Path $MoveGroupYaml)) { throw "MoveGroup YAML not found: $MoveGroupYaml" }
if (-not (Test-Path $RosSetup)) { throw "ROS setup not found: $RosSetup" }
if (-not (Test-Path $MoveGroupExe)) { throw "MoveGroup exe not found: $MoveGroupExe" }
if (-not (Test-Path $PyExe)) { throw "Python exe not found: $PyExe" }

Write-Host "$pfx Repo root: $RepoRoot"
Write-Host "$pfx Duration: $Duration s"
Write-Host "$pfx Intent: $Intent"
Write-Host "$pfx Tiago USD: $TiagoUsd"
Write-Host "$pfx Use fake controllers: $($UseFakeControllers.IsPresent)"
Write-Host "$pfx Require real Tiago: $($RequireRealTiago.IsPresent)"
if ($IntentDelaySec -le 0) {
    $IntentDelaySec = [Math]::Max(6, [Math]::Min([int]($Duration / 3), [Math]::Max(1, $Duration - 4)))
}
if ($MaxRetriesPerIntent -lt 0) {
    $MaxRetriesPerIntent = 0
}
$intentList = @()
if ($IntentSequence -and $IntentSequence.Trim().Length -gt 0) {
    $intentList = $IntentSequence.Split(",") | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }
}
if (-not $intentList -or $intentList.Count -eq 0) {
    $intentList = @($Intent.Trim().ToLower())
}
$effectiveIntentCount = $intentList.Count
if ($PreGoHomeBetweenStages) {
    $effectiveIntentCount += ($intentList | Where-Object { $_ -ne "go_home" }).Count
}
$estimatedDuration = $IntentDelaySec + ($effectiveIntentCount * 10) + 20
if ($Duration -lt $estimatedDuration) {
    Write-Host "$pfx Increasing duration to $estimatedDuration s for gated sequence."
    $Duration = $estimatedDuration
}
Write-Host "$pfx Intent delay: $IntentDelaySec s"
Write-Host "$pfx Intent sequence: $($intentList -join ', ')"
Write-Host "$pfx Pre-go-home: $PreGoHomeBetweenStages | Retry(-4): $RetryOnCodeMinus4 | Max retries: $MaxRetriesPerIntent"
Write-Host "$pfx Logs dir: $RunLogDir"

$CommonEnv = "set PYTHONUNBUFFERED=1&& set HOME=C:\Users\max&& set ROS_DOMAIN_ID=0&& set ROS_LOCALHOST_ONLY=0&& call $RosSetup &&"

try {
    Stop-ProcessesByPattern -Pattern "moveit_intent_bridge\.py" -Name "moveit bridge"
    Stop-ProcessesByPattern -Pattern "ros2_fjt_proxy\.py" -Name "fjt proxy"
    Stop-ProcessesByPattern -Pattern "fake_tiago_trajectory_controllers\.py" -Name "fake trajectory controllers"
    Stop-ProcessesByPattern -Pattern "move_group\.EXE.+tiago_move_group_working\.yaml" -Name "move_group"

    # Ensure proxy IPC dir exists and is clean.
    $ProxyDir = "C:\RoboLab_Data\fjt_proxy"
    New-Item -ItemType Directory -Force -Path $ProxyDir | Out-Null
    Remove-Item "$ProxyDir\pending_*.json" -ErrorAction SilentlyContinue
    Remove-Item "$ProxyDir\done_*.json"    -ErrorAction SilentlyContinue
    Remove-Item "$ProxyDir\joint_state.json" -ErrorAction SilentlyContinue

    $moveGroupOut = Join-Path $RunLogDir "move_group.out.log"
    $moveGroupErr = Join-Path $RunLogDir "move_group.err.log"
    $bridgeOut    = Join-Path $RunLogDir "bridge.out.log"
    $bridgeErr    = Join-Path $RunLogDir "bridge.err.log"
    $proxyOut     = Join-Path $RunLogDir "fjt_proxy.out.log"
    $proxyErr     = Join-Path $RunLogDir "fjt_proxy.err.log"
    $ProxyScript  = Join-Path $PSScriptRoot "ros2_fjt_proxy.py"

    # 1) move_group
    $MoveGroupCmd = "`"$CommonEnv $MoveGroupExe --ros-args --params-file $MoveGroupYaml`""
    $started.move_group = Start-LoggedCmdProcess -CmdLine $MoveGroupCmd -Name "move_group" -StdoutPath $moveGroupOut -StderrPath $moveGroupErr
    [void](Wait-ForLogPattern -Paths @($moveGroupOut, $moveGroupErr) -Pattern "MoveGroup context initialization complete|You can start planning now|MoveGroup debug mode is ON" -TimeoutSec 25 -Name "move_group")

    # 2) ros2_fjt_proxy: runs in conda Python, hosts FJT servers + publishes /joint_states.
    # Communicates with Isaac Sim via JSON files in $ProxyDir.
    $proxyExtraEnv = 'set FJT_PROXY_DIR=' + $ProxyDir + '&&'
    $ProxyCmd = "`"$CommonEnv $proxyExtraEnv $PyExe $ProxyScript --shared-dir $ProxyDir`""
    $started.proxy = Start-LoggedCmdProcess -CmdLine $ProxyCmd -Name "fjt proxy" -StdoutPath $proxyOut -StderrPath $proxyErr
    [void](Wait-ForLogPattern -Paths @($proxyOut, $proxyErr) -Pattern "Action servers ready|Spinning.*ready" -TimeoutSec 15 -Name "fjt proxy")

    # 3) optional fake trajectory controllers (legacy fallback, normally disabled)
    if ($UseFakeControllers) {
        $fakeOut = Join-Path $RunLogDir "fake_ctrl.out.log"
        $fakeErr = Join-Path $RunLogDir "fake_ctrl.err.log"
        $FakeCtrlCmd = "`"$CommonEnv $PyExe $FakeControllersScript`""
        $started.fake = Start-LoggedCmdProcess -CmdLine $FakeCtrlCmd -Name "fake trajectory controllers" -StdoutPath $fakeOut -StderrPath $fakeErr
    }

    # 4) bridge in EXECUTION mode: MoveGroup plans AND executes via ros2_fjt_proxy.
    $BridgeCmd = "`"$CommonEnv $PyExe $BridgeScript --robot tiago --intent-topic /tiago_test/moveit/intent --planning-group arm_torso --frame-id base_footprint`""
    $started.bridge = Start-LoggedCmdProcess -CmdLine $BridgeCmd -Name "moveit bridge" -StdoutPath $bridgeOut -StderrPath $bridgeErr
    [void](Wait-ForLogPattern -Paths @($bridgeOut, $bridgeErr) -Pattern "Bridge: subscribe .+ -> action /move_action" -TimeoutSec 20 -Name "moveit bridge")

    # 4) send gated intent sequence while smoke is running
    # Run intent job in a separate file to avoid PS5.1 ScriptBlock parsing quirks.
    $IntentJobScript = Join-Path $PSScriptRoot "exec_smoke_intent_job.ps1"
    $intentJob = Start-Job -FilePath $IntentJobScript -ArgumentList @(
        $RosSetup,
        $PyExe,
        $PubScript,
        $intentList,
        $IntentDelaySec,
        $bridgeErr,
        $IntentResultTimeoutSec,
        $MaxRetriesPerIntent,
        $PreGoHomeBetweenStages,
        $RetryOnCodeMinus4,
        $WarmupGoHome
    )
    $smokeOut = Join-Path $RunLogDir "smoke.out.log"
    $smokeErr = Join-Path $RunLogDir "smoke.err.log"
    $condaRos2Bin  = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\bin"
    $condaRos2Site = "C:\Users\max\Mambaforge\envs\ros2_humble\Lib\site-packages"
    $smokeArgs = @(
        "-ExecutionPolicy", "Bypass", "-File", $SmokeScript,
        "-Duration", $Duration,
        "-TiagoUsd", $TiagoUsd,
        "-Ros2DllDir", $condaRos2Bin,
        "-Ros2SitePackages", $condaRos2Site
    )
    if ($RequireRealTiago) {
        $smokeArgs += "-RequireRealTiago"
    }
    $started.smoke = Start-Process -FilePath "powershell.exe" -ArgumentList $smokeArgs -PassThru -RedirectStandardOutput $smokeOut -RedirectStandardError $smokeErr
    Write-Host "$pfx Started smoke pid=$($started.smoke.Id)"
    [void](Wait-ForLogPattern -Paths @($smokeOut, $smokeErr) -Pattern "Running collector with --moveit|Simulation App Starting|app ready" -TimeoutSec 45 -Name "smoke collector")

    $intentJobOutput = Receive-Job -Job $intentJob -Wait -AutoRemoveJob
    foreach ($jobLine in $intentJobOutput) {
        if ($jobLine -is [string]) {
            Write-Host $jobLine
        }
    }

    $intentSummary = $intentJobOutput | Where-Object { $_ -is [hashtable] -and $_.ContainsKey("Success") } | Select-Object -Last 1
    if (-not $intentSummary) {
        $errMsg = "$pfx Bridge did not report success: Intent sequence job returned no summary."
        throw $errMsg
    }
    $bridgeResultMsg = if ($intentSummary.Success) { "MoveGroup goal succeeded" } else { $intentSummary.Message }
    Write-Host "$pfx Bridge result: $bridgeResultMsg"
    if (-not $intentSummary.Success) {
        $failMsg = "$pfx Bridge did not report success: " + $intentSummary.Message
        throw $failMsg
    }
    # Do NOT force-kill Isaac Sim after intent success.
    # The data_collector saves dataset/video at the end of its natural duration.
    # Let it run as an orphan until it exits on its own. Only ROS components are stopped in finally.
    Write-Host "$pfx move_group out=$moveGroupOut err=$moveGroupErr"
    Write-Host "$pfx bridge out=$bridgeOut err=$bridgeErr"
    Write-Host "$pfx proxy out=$proxyOut err=$proxyErr"
    Write-Host "$pfx smoke out=$smokeOut err=$smokeErr"
    if ($UseFakeControllers) {
        Write-Host "$pfx fake ctrl out=$fakeOut err=$fakeErr"
    }

    Write-Host "$pfx Done"
}
finally {
    # "smoke" (Isaac Sim) is intentionally excluded: it saves data at the end of its natural duration.
    foreach ($key in @("bridge", "proxy", "fake", "move_group")) {
        if ($started.ContainsKey($key) -and $started[$key]) {
            try {
                Stop-Process -Id $started[$key].Id -Force -ErrorAction SilentlyContinue
                $stoppedPid = $started[$key].Id
                Write-Host ('[ExecSmoke] Stopped ' + $key + ' pid=' + $stoppedPid)
            }
            catch {}
        }
    }
}

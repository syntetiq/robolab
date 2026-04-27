param(
    [string]$RosSetup = "C:\Users\max\mambaforge\envs\ros2_humble\Library\local_setup.bat",
    [string]$MoveGroupExe = "C:\Users\max\mambaforge\envs\ros2_humble\Library\lib\moveit_ros_move_group\move_group.EXE",
    [string]$PyExe = "C:\Users\max\mambaforge\envs\ros2_humble\python.exe",
    [string]$ProxyDir = "C:\RoboLab_Data\fjt_proxy",
    [string]$LogDir = "",
    [string]$PidFile = "",
    [string]$IntentTopic = "/tiago/moveit/intent",
    [string]$PlanningGroup = "arm_torso",
    [string]$FrameId = "base_footprint",
    [int]$RosDomainId = 77,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$pfx = "[MoveItStack]"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$MoveGroupYaml = Join-Path $PSScriptRoot "tiago_move_group_working.yaml"
$BridgeScript = Join-Path $PSScriptRoot "moveit_intent_bridge.py"
$ProxyScript = Join-Path $PSScriptRoot "ros2_fjt_proxy.py"

function Stop-StackProcesses {
    $patterns = @(
        @{ Pattern = "move_group\.EXE.+tiago_move_group_working\.yaml"; Name = "move_group" },
        @{ Pattern = "ros2_fjt_proxy\.py"; Name = "fjt_proxy" },
        @{ Pattern = "moveit_intent_bridge\.py"; Name = "intent_bridge" }
    )
    foreach ($p in $patterns) {
        $procs = Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -and ($_.CommandLine -match $p.Pattern)
        }
        foreach ($proc in $procs) {
            try {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                Write-Host "$pfx Stopped $($p.Name) pid=$($proc.ProcessId)"
            } catch {
                Write-Host "$pfx WARN: could not stop $($p.Name) pid=$($proc.ProcessId)"
            }
        }
    }
}

if ($Stop) {
    Stop-StackProcesses
    exit 0
}

if (-not $LogDir) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $LogDir = Join-Path $RepoRoot "logs\moveit_stack\$stamp"
}
[void](New-Item -ItemType Directory -Force -Path $LogDir)

foreach ($f in @($RosSetup, $MoveGroupExe, $PyExe, $MoveGroupYaml, $BridgeScript, $ProxyScript)) {
    if (-not (Test-Path $f)) { throw "$pfx Required file not found: $f" }
}

New-Item -ItemType Directory -Force -Path $ProxyDir | Out-Null
Remove-Item "$ProxyDir\pending_*.json" -ErrorAction SilentlyContinue
Remove-Item "$ProxyDir\done_*.json" -ErrorAction SilentlyContinue
Remove-Item "$ProxyDir\joint_state.json" -ErrorAction SilentlyContinue

# local_setup.bat uses lowercase 'mambaforge' in PYTHONPATH/AMENT_PREFIX_PATH.
# Python exe must match that casing to avoid WDAC DLL-load blocks on Windows.
$CondaEnvRoot = Split-Path -Parent (Split-Path -Parent $RosSetup)
$CommonEnv = "set PYTHONUNBUFFERED=1&& set HOME=$env:USERPROFILE&& set ROS_DOMAIN_ID=$RosDomainId&& set ROS_LOCALHOST_ONLY=1&& call $RosSetup &&"

Stop-StackProcesses

function Start-LoggedCmd {
    param([string]$CmdLine, [string]$Name, [string]$OutLog, [string]$ErrLog)
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/d /s /c $CmdLine" `
        -PassThru -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
    Write-Host "$pfx Started $Name pid=$($proc.Id)"
    return $proc
}

function Wait-Ready {
    param([string[]]$Paths, [string]$Pattern, [int]$TimeoutSec = 25, [string]$Name = "process")
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        foreach ($p in $Paths) {
            if (Test-Path $p) {
                $text = Get-Content -Path $p -Raw -ErrorAction SilentlyContinue
                if ($text -match $Pattern) {
                    Write-Host "$pfx $Name ready ($([int]$sw.Elapsed.TotalSeconds)s)"
                    return $true
                }
            }
        }
        Start-Sleep -Milliseconds 300
    }
    Write-Host "$pfx WARN: $Name not ready after ${TimeoutSec}s"
    return $false
}

$pids = @()

$mgOut = Join-Path $LogDir "move_group.out.log"
$mgErr = Join-Path $LogDir "move_group.err.log"
$mgCmd = "`"$CommonEnv $MoveGroupExe --ros-args --params-file $MoveGroupYaml`""
$mgProc = Start-LoggedCmd -CmdLine $mgCmd -Name "move_group" -OutLog $mgOut -ErrLog $mgErr
$pids += $mgProc.Id
Wait-Ready -Paths @($mgOut, $mgErr) -Pattern "MoveGroup context initialization complete|You can start planning now|MoveGroup debug mode is ON" -TimeoutSec 30 -Name "move_group"

$pxOut = Join-Path $LogDir "fjt_proxy.out.log"
$pxErr = Join-Path $LogDir "fjt_proxy.err.log"
$proxyEnv = "set FJT_PROXY_DIR=$ProxyDir&&"
$pxCmd = "`"$CommonEnv $proxyEnv $PyExe $ProxyScript --shared-dir $ProxyDir`""
$pxProc = Start-LoggedCmd -CmdLine $pxCmd -Name "fjt_proxy" -OutLog $pxOut -ErrLog $pxErr
$pids += $pxProc.Id
Wait-Ready -Paths @($pxOut, $pxErr) -Pattern "Action servers ready|Spinning.*ready" -TimeoutSec 15 -Name "fjt_proxy"

$brOut = Join-Path $LogDir "bridge.out.log"
$brErr = Join-Path $LogDir "bridge.err.log"
$brCmd = "`"$CommonEnv $PyExe $BridgeScript --robot tiago --intent-topic $IntentTopic --planning-group $PlanningGroup --frame-id $FrameId`""
$brProc = Start-LoggedCmd -CmdLine $brCmd -Name "intent_bridge" -OutLog $brOut -ErrLog $brErr
$pids += $brProc.Id
Wait-Ready -Paths @($brOut, $brErr) -Pattern "Bridge: subscribe .+ -> action /move_action" -TimeoutSec 20 -Name "intent_bridge"

if ($PidFile) {
    $pids -join "`n" | Set-Content -Path $PidFile -Encoding utf8
    Write-Host "$pfx PIDs written to $PidFile"
}

Write-Host "$pfx All 3 processes started: move_group=$($mgProc.Id) fjt_proxy=$($pxProc.Id) bridge=$($brProc.Id)"
Write-Host "$pfx Logs: $LogDir"
Write-Host "$pfx Stack ready."

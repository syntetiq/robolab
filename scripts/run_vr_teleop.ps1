param(
    [int]$Duration = 300,
    [string]$TiagoUsd = "C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional.usd",
    [string]$EnvUsd = "C:\RoboLab_Data\scenes\Small_House_Interactive.usd",
    [string]$OutputRoot = "C:\RoboLab_Data\episodes",
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat",
    [switch]$MockVR,
    [switch]$EnableWebRTC,
    [int]$WebRTCPort = 8211,
    [float]$Scale = 1.0,
    [float]$Rate = 30.0,
    [int]$RosDomainId = 77,
    [switch]$WristCamera,
    [switch]$ExternalCamera,
    [string]$RosSetup = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat",
    [string]$MoveGroupExe = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\lib\moveit_ros_move_group\move_group.EXE",
    [string]$ProxyDir = "C:\RoboLab_Data\fjt_proxy"
)

$ErrorActionPreference = "Stop"
$pfx = '[VRTeleop]'

$RepoRoot    = Split-Path -Parent $PSScriptRoot
$ScriptsDir  = $PSScriptRoot
$ServoYaml   = Join-Path $ScriptsDir "tiago_servo_config.yaml"
$MoveGroupYaml = Join-Path $ScriptsDir "tiago_move_group_working.yaml"
$VRTeleopScript = Join-Path $ScriptsDir "vr_teleop_node.py"
$DataCollector  = Join-Path $ScriptsDir "data_collector_tiago.py"
$FJTProxy       = Join-Path $ScriptsDir "ros2_fjt_proxy.py"
$ServoBridge    = Join-Path $ScriptsDir "servo_joint_trajectory_bridge.py"
$PyExe = "C:\Users\max\Mambaforge\envs\ros2_humble\python.exe"

$RunStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunLogDir = Join-Path $RepoRoot ("logs\vr_teleop\" + $RunStamp)
$EpisodeOutDir = Join-Path $OutputRoot ("vr_teleop_" + $RunStamp)
[void](New-Item -ItemType Directory -Force -Path $RunLogDir)
[void](New-Item -ItemType Directory -Force -Path $EpisodeOutDir)

$logParent = Join-Path $RepoRoot "logs\vr_teleop"
$oldLogDirs = Get-ChildItem $logParent -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -Skip 10
foreach ($old in $oldLogDirs) {
    Remove-Item $old.FullName -Recurse -Force -ErrorAction SilentlyContinue
}

function Write-Log { param([string]$m) ; Write-Host "$pfx $m" }

Write-Log "=== VR Teleoperation Session ==="
Write-Log "Scene   : $EnvUsd"
Write-Log "Robot   : $TiagoUsd"
Write-Log "Output  : $EpisodeOutDir"
Write-Log "Duration: ${Duration}s"
Write-Log "Mock VR : $MockVR"
Write-Log "WebRTC  : $EnableWebRTC (port $WebRTCPort)"
Write-Log "ROS     : domain=$RosDomainId localhost_only=1"
Write-Log "Logs    : $RunLogDir"

foreach ($required in @($IsaacPython, $DataCollector, $FJTProxy, $ServoBridge, $VRTeleopScript, $PyExe, $RosSetup, $MoveGroupExe, $ServoYaml, $MoveGroupYaml)) {
    if (-not (Test-Path $required)) {
        throw "$pfx Required file not found: $required"
    }
}

# ── 0. Clean shared IPC files ─────────────────────────────────────────
$env:ROS_DOMAIN_ID = "$RosDomainId"
$env:ROS_LOCALHOST_ONLY = "1"
$env:FJT_PROXY_DIR = $ProxyDir
if (Test-Path $ProxyDir) {
    Remove-Item "$ProxyDir\pending_*.json" -ErrorAction SilentlyContinue
    Remove-Item "$ProxyDir\done_*.json" -ErrorAction SilentlyContinue
    Remove-Item "$ProxyDir\joint_state.json" -ErrorAction SilentlyContinue
    Remove-Item "$ProxyDir\base_cmd.json" -ErrorAction SilentlyContinue
}
[void](New-Item -ItemType Directory -Force -Path $ProxyDir)
Write-Log "IPC dir ready: $ProxyDir"

# ── 1. Source ROS2 environment ────────────────────────────────────────
Write-Log "Sourcing ROS2 environment..."
cmd /c "$RosSetup > NUL 2>&1"

# ── 2. Start Isaac Sim data collector in VR mode ──────────────────────
$dcArgs = @(
    $DataCollector,
    "--tiago-usd", $TiagoUsd,
    "--env", $EnvUsd,
    "--output_dir", $EpisodeOutDir,
    "--duration", $Duration,
    "--vr",
    "--moveit",
    "--mobile-base"
)
if ($EnableWebRTC) {
    $dcArgs += "--webrtc"
    Write-Log "WebRTC streaming enabled - head camera POV at http://localhost:${WebRTCPort}/streaming/webrtc-demo/"
}
if ($WristCamera)     { $dcArgs += "--wrist-camera" }
if ($ExternalCamera)  { $dcArgs += "--external-camera" }
Write-Log "Starting Isaac Sim data collector (VR mode)..."
$dcProc = Start-Process -PassThru -NoNewWindow -FilePath $IsaacPython -ArgumentList $dcArgs `
    -RedirectStandardOutput (Join-Path $RunLogDir "data_collector.stdout.log") `
    -RedirectStandardError  (Join-Path $RunLogDir "data_collector.stderr.log")
Write-Log "  PID=$($dcProc.Id)"
Start-Sleep -Seconds 20

# ── 3. Start FJT proxy (bridges ROS2 ↔ Isaac Sim via file IPC) ───────
$fjtArgs = @($FJTProxy)
Write-Log "Starting ROS2 FJT proxy..."
$fjtProc = Start-Process -PassThru -NoNewWindow -FilePath $PyExe -ArgumentList $fjtArgs `
    -RedirectStandardOutput (Join-Path $RunLogDir "fjt_proxy.stdout.log") `
    -RedirectStandardError  (Join-Path $RunLogDir "fjt_proxy.stderr.log")
Write-Log "  PID=$($fjtProc.Id)"
Start-Sleep -Seconds 3

# ── 4. Start MoveGroup (required for Servo planning scene) ───────────
$mgArgs = @("--ros-args", "--params-file", $MoveGroupYaml)
Write-Log "Starting MoveGroup..."
$mgProc = Start-Process -PassThru -NoNewWindow -FilePath $MoveGroupExe -ArgumentList $mgArgs `
    -RedirectStandardOutput (Join-Path $RunLogDir "move_group.stdout.log") `
    -RedirectStandardError  (Join-Path $RunLogDir "move_group.stderr.log")
Write-Log "  PID=$($mgProc.Id)"
Start-Sleep -Seconds 5

# ── 5. Start MoveIt Servo + bridge to FJT action ─────────────────────
$servoArgs = @(
    "run", "moveit_servo", "servo_node",
    "--ros-args",
    "--params-file", $ServoYaml,
    "--params-file", $MoveGroupYaml
)
Write-Log "Starting MoveIt Servo..."
$servoCmdLine = "call `"$RosSetup`" && ros2 " + ($servoArgs -join " ")
$servoProc = Start-Process -PassThru -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/d /s /c `"$servoCmdLine`"" `
    -RedirectStandardOutput (Join-Path $RunLogDir "servo.stdout.log") `
    -RedirectStandardError  (Join-Path $RunLogDir "servo.stderr.log")
Write-Log "  PID=$($servoProc.Id)"
Start-Sleep -Seconds 3

$bridgeArgs = @(
    $ServoBridge,
    "--trajectory-topic", "/arm_controller/joint_trajectory",
    "--action-name", "/arm_controller/follow_joint_trajectory"
)
Write-Log "Starting Servo->FJT bridge..."
$bridgeProc = Start-Process -PassThru -NoNewWindow -FilePath $PyExe -ArgumentList $bridgeArgs `
    -RedirectStandardOutput (Join-Path $RunLogDir "servo_bridge.stdout.log") `
    -RedirectStandardError  (Join-Path $RunLogDir "servo_bridge.stderr.log")
Write-Log "  PID=$($bridgeProc.Id)"
Start-Sleep -Seconds 2

# ── 6. Start VR Teleop Node ──────────────────────────────────────────
$vrArgs = @(
    $VRTeleopScript,
    "--scale", $Scale,
    "--rate", $Rate
)
if ($MockVR) { $vrArgs += "--mock" }

Write-Log "Starting VR Teleop Node..."
$vrProc = Start-Process -PassThru -NoNewWindow -FilePath $PyExe -ArgumentList $vrArgs `
    -RedirectStandardOutput (Join-Path $RunLogDir "vr_teleop.stdout.log") `
    -RedirectStandardError  (Join-Path $RunLogDir "vr_teleop.stderr.log")
Write-Log "  PID=$($vrProc.Id)"

# ── 7. Wait for duration or user interrupt ────────────────────────────
$procs = @{
    "DataCollector" = $dcProc
    "FJTProxy"      = $fjtProc
    "MoveGroup"     = $mgProc
    "Servo"         = $servoProc
    "ServoBridge"   = $bridgeProc
    "VRTeleop"      = $vrProc
}

Write-Log ""
Write-Log "All processes running. Session will last ${Duration}s."
Write-Log "Press Ctrl+C to stop early."
Write-Log ""

$elapsed = 0
$checkInterval = 5
try {
    while ($elapsed -lt $Duration) {
        Start-Sleep -Seconds $checkInterval
        $elapsed += $checkInterval
        $crashed = @()
        foreach ($kv in $procs.GetEnumerator()) {
            if ($kv.Value.HasExited) {
                $crashed += "$($kv.Key)(exit=$($kv.Value.ExitCode))"
            }
        }
        if ($crashed.Count -gt 0) {
            Write-Log "WARNING: Processes exited early: $($crashed -join ', ')"
        }
        if ($elapsed % 30 -eq 0) {
            Write-Log "Elapsed: ${elapsed}s / ${Duration}s"
        }
    }
} finally {
    Write-Log "Shutting down all processes..."
    foreach ($kv in $procs.GetEnumerator()) {
        if (-not $kv.Value.HasExited) {
            Write-Log "  Stopping $($kv.Key) (PID=$($kv.Value.Id))..."
            try { Stop-Process -Id $kv.Value.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
    Write-Log "All processes stopped. Logs in: $RunLogDir"
}

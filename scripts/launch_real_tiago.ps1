<#
.SYNOPSIS
  Launch stack for real Tiago robot data collection.

.DESCRIPTION
  Starts the full pipeline for collecting manipulation data on
  real hardware: MoveIt2, the sim2real safety bridge, intent bridge,
  and data recording via ROS2 bag / rosbag2.

  Unlike sim, there is no FJT proxy — MoveIt talks directly to
  the real robot's ros2_control controllers.

.PARAMETER Intent
  MoveIt intent to execute (e.g., plan_pick_sink, go_home).

.PARAMETER DryRun
  Run sim2real bridge in dry-run mode (no real commands).

.PARAMETER RecordBag
  Record a ROS2 bag alongside the episode.

.EXAMPLE
  .\scripts\launch_real_tiago.ps1 -Intent plan_pick_sink
  .\scripts\launch_real_tiago.ps1 -Intent go_home -DryRun
#>

param(
    [string]$Intent = "go_home",
    [switch]$DryRun,
    [switch]$RecordBag,
    [string]$ConfigPath = "config/sim2real.yaml",
    [string]$OutputDir = "C:\RoboLab_Data\real_episodes",
    [int]$Duration = 60
)

$ErrorActionPreference = "Stop"
$pfx = "[RealTiago]"

Write-Host "$pfx ============================================" -ForegroundColor Cyan
Write-Host "$pfx   Real Tiago Launch Stack" -ForegroundColor Cyan
Write-Host "$pfx   Intent:  $Intent" -ForegroundColor Cyan
Write-Host "$pfx   DryRun:  $DryRun" -ForegroundColor Cyan
Write-Host "$pfx   Config:  $ConfigPath" -ForegroundColor Cyan
Write-Host "$pfx ============================================" -ForegroundColor Cyan

# Validate config
if (-not (Test-Path $ConfigPath)) {
    Write-Host "$pfx ERROR: Config not found: $ConfigPath" -ForegroundColor Red
    exit 1
}

# Check ROS2 environment
$ros2Check = Get-Command ros2 -ErrorAction SilentlyContinue
if (-not $ros2Check) {
    Write-Host "$pfx ERROR: ros2 not found in PATH. Source your ROS2 workspace first." -ForegroundColor Red
    exit 1
}

# Verify robot is reachable via /joint_states
Write-Host "$pfx Checking robot connectivity..."
$jsCheck = ros2 topic list 2>&1 | Select-String "/joint_states"
if (-not $jsCheck) {
    Write-Host "$pfx WARNING: /joint_states topic not found. Is the robot powered on?" -ForegroundColor Yellow
    if (-not $DryRun) {
        Write-Host "$pfx Aborting (use -DryRun for offline testing)" -ForegroundColor Red
        exit 1
    }
}

# Create episode directory
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$episodeDir = Join-Path $OutputDir "real_${Intent}_${timestamp}"
New-Item -ItemType Directory -Path $episodeDir -Force | Out-Null
Write-Host "$pfx Episode dir: $episodeDir"

# Step 1: Start MoveIt (if not already running)
$moveitRunning = ros2 node list 2>&1 | Select-String "move_group"
if (-not $moveitRunning) {
    Write-Host "$pfx Starting MoveIt move_group..."
    $moveitProc = Start-Process -FilePath "ros2" -ArgumentList @(
        "run", "moveit_ros_move_group", "move_group",
        "--ros-args",
        "--params-file", "scripts/tiago_move_group_real.yaml"
    ) -PassThru -WindowStyle Hidden
    Write-Host "$pfx   MoveIt PID: $($moveitProc.Id)"
    Start-Sleep -Seconds 5
} else {
    Write-Host "$pfx MoveIt already running"
}

# Step 2: Start sim2real bridge
Write-Host "$pfx Starting sim2real safety bridge..."
$bridgeArgs = @("scripts/sim2real_bridge.py", "--config", $ConfigPath, "--live")
if ($DryRun) {
    $bridgeArgs += "--dry-run"
}
$bridgeProc = Start-Process -FilePath "python" -ArgumentList $bridgeArgs `
    -PassThru -WindowStyle Hidden -RedirectStandardOutput "$episodeDir\sim2real_bridge.log"
Write-Host "$pfx   Bridge PID: $($bridgeProc.Id)"
Start-Sleep -Seconds 2

# Step 3: Start ROS2 bag recording (optional)
$bagProc = $null
if ($RecordBag) {
    $bagDir = Join-Path $episodeDir "rosbag"
    Write-Host "$pfx Starting rosbag recording..."
    $bagProc = Start-Process -FilePath "ros2" -ArgumentList @(
        "bag", "record",
        "/joint_states",
        "/head_front_camera/image_raw",
        "/wrist_right_camera/image_raw",
        "/external_camera/image_raw",
        "/mobile_base_controller/cmd_vel",
        "-o", $bagDir
    ) -PassThru -WindowStyle Hidden
    Write-Host "$pfx   Bag PID: $($bagProc.Id)"
}

# Step 4: Start intent bridge
Write-Host "$pfx Starting MoveIt intent bridge..."
$intentProc = Start-Process -FilePath "ros2" -ArgumentList @(
    "run", "moveit_intent_bridge", "moveit_intent_bridge",
    "--ros-args"
) -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2

# Step 5: Send intent
Write-Host "$pfx Sending intent: $Intent" -ForegroundColor Green
$startTime = Get-Date

ros2 topic pub --once /moveit_intent std_msgs/msg/String "{data: '$Intent'}" 2>&1 | Out-Null

Write-Host "$pfx Waiting for execution (max ${Duration}s)..."
Start-Sleep -Seconds $Duration

$elapsed = ((Get-Date) - $startTime).TotalSeconds
Write-Host "$pfx Execution time: $([math]::Round($elapsed, 1))s"

# Step 6: Save metadata
$metadata = @{
    intent = $Intent
    timestamp = $timestamp
    duration_s = [math]::Round($elapsed, 1)
    config = $ConfigPath
    dry_run = [bool]$DryRun
    robot = "tiago_dual_real"
} | ConvertTo-Json -Depth 5

Set-Content -Path "$episodeDir\metadata.json" -Value $metadata -Encoding utf8

# Cleanup
Write-Host "$pfx Cleaning up processes..."
if ($bridgeProc -and -not $bridgeProc.HasExited) {
    Stop-Process -Id $bridgeProc.Id -Force -ErrorAction SilentlyContinue
}
if ($bagProc -and -not $bagProc.HasExited) {
    Stop-Process -Id $bagProc.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host "$pfx ============================================" -ForegroundColor Green
Write-Host "$pfx   Episode saved: $episodeDir" -ForegroundColor Green
Write-Host "$pfx   Metadata: $episodeDir\metadata.json" -ForegroundColor Green
if ($RecordBag) {
    Write-Host "$pfx   Rosbag:   $episodeDir\rosbag" -ForegroundColor Green
}
Write-Host "$pfx ============================================" -ForegroundColor Green

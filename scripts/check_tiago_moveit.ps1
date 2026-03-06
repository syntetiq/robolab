# Check if tiago_moveit_config is available (built or from package).
# Usage: .\scripts\check_tiago_moveit.ps1

$ErrorActionPreference = "Stop"
$ros2Setup = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat"
$wsSetup = "C:\ros2_ws\install\local_setup.bat"

Write-Host "[Check] Testing tiago_moveit_config availability..."

if (-not (Test-Path $ros2Setup)) {
    Write-Host "[Check] FAIL: ROS2 setup not found at $ros2Setup"
    exit 1
}

# Try to run ros2 launch tiago_moveit_config --show-args (quick check, no GUI)
$cmd = "cmd /c `"call `"$ros2Setup`" && call `"$wsSetup`" 2>nul && ros2 pkg prefix tiago_moveit_config 2>nul`""
try {
    $result = cmd /c "call `"$ros2Setup`" && (call `"$wsSetup`" 2>nul && ros2 pkg prefix tiago_moveit_config 2>nul) || echo NOT_FOUND"
    if ($LASTEXITCODE -eq 0 -and $result -and $result -notmatch "NOT_FOUND") {
        Write-Host "[Check] OK: tiago_moveit_config found at $result"
        exit 0
    }
} catch {}

# Fallback: check if workspace install has tiago_moveit_config
$tiagoShare = "C:\ros2_ws\install\tiago_moveit_config\share\tiago_moveit_config"
if ((Test-Path $wsSetup) -and (Test-Path $tiagoShare)) {
    Write-Host "[Check] OK: tiago_moveit_config built in workspace"
    Write-Host "[Check] Launch: call $wsSetup && ros2 launch tiago_moveit_config moveit_rviz.launch.py"
    exit 0
}
Write-Host "[Check] tiago_moveit_config not available."
Write-Host "[Check] Build requires Visual Studio (x64 Native Tools Command Prompt). See docs/tiago_moveit_setup.md"
Write-Host "[Check] Alternative: use Panda demo (ros2 launch moveit_resources_panda_moveit_config demo.launch.py) with --robot panda"
exit 1

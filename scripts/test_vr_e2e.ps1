param(
    [int]$TimeoutSec = 60,
    [string]$RosSetup = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\local_setup.bat",
    [string]$MoveGroupExe = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\lib\moveit_ros_move_group\move_group.EXE",
    [string]$PyExe = "C:\Users\max\Mambaforge\envs\ros2_humble\python.exe"
)

$ErrorActionPreference = "Continue"
$pfx = '[VR-E2E]'
$ScriptsDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $ScriptsDir
$RunStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogDir = Join-Path $RepoRoot ("logs\vr_e2e_test\" + $RunStamp)
[void](New-Item -ItemType Directory -Force -Path $LogDir)

$CheckScript = Join-Path $ScriptsDir "test_vr_e2e_checks.py"
$ServoYaml = Join-Path $ScriptsDir "tiago_servo_config.yaml"
$MoveGroupYaml = Join-Path $ScriptsDir "tiago_move_group_working.yaml"
$VRScript = Join-Path $ScriptsDir "vr_teleop_node.py"
$FJTProxy = Join-Path $ScriptsDir "ros2_fjt_proxy.py"

$allProcs = @()
$passed = 0
$failed = 0

function Write-Log { param([string]$m) ; Write-Host "$pfx $m" }

function Run-Check {
    param([string]$Name, [string]$CheckName, [string[]]$ExtraArgs, [switch]$NeedsROS)
    Write-Log "  Running: $Name"
    $stderrFile = Join-Path $LogDir "${CheckName}_stderr.tmp"
    try {
        if ($NeedsROS) {
            $pyCall = "`"$PyExe`" `"$CheckScript`" $CheckName $($ExtraArgs -join ' ')"
            $cmdLine = "cmd /c `"`"$RosSetup`" >NUL 2>&1 && $pyCall`""
            $output = Invoke-Expression $cmdLine 2>$stderrFile
        } else {
            $allArgs = @($CheckScript, $CheckName) + $ExtraArgs
            $output = & $PyExe @allArgs 2>$stderrFile
        }
    } catch {
        $output = @("result=FAIL detail=exception: $_")
    }
    $outputStr = ($output | Out-String)
    $isPass = $outputStr -match "result=PASS"
    $output | ForEach-Object { Write-Log "    $_" }
    if ($isPass) {
        Write-Log "  [PASS] $Name"
        $script:passed++
    } else {
        Write-Log "  [FAIL] $Name"
        $script:failed++
        if (Test-Path $stderrFile) {
            $errContent = (Get-Content $stderrFile -Raw -ErrorAction SilentlyContinue)
            if ($errContent) {
                $errContent.Split("`n") | Select-Object -Last 5 | ForEach-Object { Write-Log "    ERR: $_" }
            }
        }
    }
    return $isPass
}

function Cleanup {
    Write-Log "Cleaning up processes..."
    foreach ($p in $script:allProcs) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}

trap { Cleanup; break }

Write-Log "============================================"
Write-Log " VR Teleoperation E2E Validation Test"
Write-Log "============================================"
Write-Log ""

# -- Test 1: Prerequisites --
Write-Log "Test 1: Checking prerequisites..."
$prereqOk = $true
foreach ($f in @($ServoYaml, $MoveGroupYaml, $VRScript, $FJTProxy, $MoveGroupExe, $PyExe, $CheckScript)) {
    if (-not (Test-Path $f)) {
        Write-Log "  MISSING: $f"
        $prereqOk = $false
    }
}
$objectsDir = "C:\RoboLab_Data\data\object_sets"
$objCount = 0
if (Test-Path $objectsDir) {
    $objCount = (Get-ChildItem $objectsDir -Filter "*.usda").Count
}
if ($prereqOk) { Write-Log "  [PASS] All prerequisite files found"; $passed++ }
else { Write-Log "  [FAIL] Missing prerequisite files"; $failed++; Cleanup; exit 1 }
Write-Log "  Object assets: $objCount USD files"
if ($objCount -ge 15) { Write-Log "  [PASS] Object assets"; $passed++ }
else { Write-Log "  [FAIL] Need >= 15 object assets, found $objCount"; $failed++ }

# -- Test 2: ROS2 imports --
Write-Log ""
Write-Log "Test 2: ROS2 environment..."
Run-Check "rclpy_import" "rclpy_import"
Run-Check "msgs_import" "msgs_import"

# -- Test 3: Servo config --
Write-Log ""
Write-Log "Test 3: MoveIt Servo config..."
Run-Check "servo_config" "servo_config" @($ServoYaml)

# -- Test 4: Topic alignment --
Write-Log ""
Write-Log "Test 4: Topic alignment (VR node vs Servo)..."
Run-Check "topic_align" "topic_align" @($ServoYaml, $VRScript)

# -- Test 5: FJT proxy + /joint_states --
Write-Log ""
Write-Log "Test 5: FJT proxy and /joint_states..."
$fjtBat = Join-Path $LogDir "run_fjt.bat"
Set-Content $fjtBat "@echo off`r`ncall `"$RosSetup`"`r`n`"$PyExe`" `"$FJTProxy`""
$fjtProc = Start-Process -PassThru -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/c `"$fjtBat`"" `
    -RedirectStandardOutput (Join-Path $LogDir "fjt_proxy.stdout.log") `
    -RedirectStandardError  (Join-Path $LogDir "fjt_proxy.stderr.log")
$allProcs += $fjtProc
Write-Log "  FJT proxy PID=$($fjtProc.Id)"
Start-Sleep -Seconds 5
Run-Check "joint_states" "joint_states" -NeedsROS

# -- Test 6: MoveGroup --
Write-Log ""
Write-Log "Test 6: MoveGroup..."
$mgBat = Join-Path $LogDir "run_mg.bat"
Set-Content $mgBat "@echo off`r`ncall `"$RosSetup`"`r`n`"$MoveGroupExe`" --ros-args --params-file `"$MoveGroupYaml`""
$mgProc = Start-Process -PassThru -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/c `"$mgBat`"" `
    -RedirectStandardOutput (Join-Path $LogDir "move_group.stdout.log") `
    -RedirectStandardError  (Join-Path $LogDir "move_group.stderr.log")
$allProcs += $mgProc
Write-Log "  MoveGroup PID=$($mgProc.Id)"
Start-Sleep -Seconds 8
if (-not $mgProc.HasExited) { Write-Log "  [PASS] MoveGroup running"; $passed++ }
else { Write-Log "  [FAIL] MoveGroup exited early (code=$($mgProc.ExitCode))"; $failed++ }

# -- Test 7: VR teleop (mock) --
Write-Log ""
Write-Log "Test 7: VR teleop node (mock mode)..."
$vrBat = Join-Path $LogDir "run_vr.bat"
Set-Content $vrBat "@echo off`r`ncall `"$RosSetup`"`r`n`"$PyExe`" `"$VRScript`" --mock --rate 10"
$vrProc = Start-Process -PassThru -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/c `"$vrBat`"" `
    -RedirectStandardOutput (Join-Path $LogDir "vr_teleop.stdout.log") `
    -RedirectStandardError  (Join-Path $LogDir "vr_teleop.stderr.log")
$allProcs += $vrProc
Write-Log "  VR teleop PID=$($vrProc.Id)"
Start-Sleep -Seconds 4
if (-not $vrProc.HasExited) { Write-Log "  [PASS] VR teleop running (mock)"; $passed++ }
else { Write-Log "  [FAIL] VR teleop exited early (code=$($vrProc.ExitCode))"; $failed++ }

# -- Test 8: VR status topic --
Write-Log ""
Write-Log "Test 8: VR status topic..."
Run-Check "vr_status" "vr_status" -NeedsROS

# -- Test 9: Twist command --
Write-Log ""
Write-Log "Test 9: Simulated twist commands..."
Run-Check "twist_publish" "twist_publish" -NeedsROS

# -- Test 10: Intent round-trip --
Write-Log ""
Write-Log "Test 10: Intent topic round-trip..."
Run-Check "intent_roundtrip" "intent_roundtrip" -NeedsROS

# -- Cleanup --
Cleanup

# -- Summary --
Write-Log ""
Write-Log "============================================"
Write-Log " Summary: $passed passed, $failed failed"
Write-Log "============================================"
Write-Log ""
if ($failed -eq 0) {
    Write-Log "All VR E2E checks passed!"
    Write-Log "Next step: connect Vive Pro 2 via SteamVR and run:"
    Write-Log "  .\scripts\run_vr_teleop.ps1 -EnvUsd <scene.usd>"
} else {
    Write-Log "$failed check(s) failed. See details above."
    Write-Log "Note: MoveIt Servo requires the moveit_servo ROS2 package."
    Write-Log "      Full VR E2E requires Vive Pro 2 + SteamVR hardware."
}
Write-Log "Logs: $LogDir"

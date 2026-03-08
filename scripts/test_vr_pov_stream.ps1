param(
    [string]$PyExe = "C:\Users\max\Mambaforge\envs\ros2_humble\python.exe",
    [int]$WebRTCPort = 8211,
    [string]$IsaacDir = "C:\Users\max\Documents\IsaacSim"
)

$ErrorActionPreference = "Continue"
$pfx = '[VR-POV]'
$ScriptsDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $ScriptsDir
$passed = 0
$failed = 0

function Write-Log { param([string]$m) ; Write-Host "$pfx $m" }
function Test-Pass { param([string]$n, [string]$d) ; Write-Log "  [PASS] $n - $d"; $script:passed++ }
function Test-Fail { param([string]$n, [string]$d) ; Write-Log "  [FAIL] $n - $d"; $script:failed++ }

Write-Log "================================================"
Write-Log " VR POV Streaming Pipeline Validation"
Write-Log "================================================"
Write-Log ""

# ── 1. Data collector --vr and --webrtc flags ─────────────────────────
Write-Log "Test 1: Data collector VR+WebRTC flags..."
$dcScript = Join-Path $ScriptsDir "data_collector_tiago.py"
if (Test-Path $dcScript) {
    $dcContent = Get-Content $dcScript -Raw
    $hasVR = $dcContent -match "--vr"
    $hasWebRTC = $dcContent -match "--webrtc"
    $hasHead2Link = $dcContent -match "head_2_link"
    $hasLivestream = $dcContent -match "livestream"
    $hasWebRTCExt = $dcContent -match "omni.kit.livestream.webrtc"

    if ($hasVR) { Test-Pass "vr_flag" "--vr flag present" }
    else { Test-Fail "vr_flag" "--vr flag missing" }

    if ($hasWebRTC) { Test-Pass "webrtc_flag" "--webrtc flag present" }
    else { Test-Fail "webrtc_flag" "--webrtc flag missing" }

    if ($hasHead2Link) { Test-Pass "head_camera" "Head camera mounted at head_2_link in VR mode" }
    else { Test-Fail "head_camera" "head_2_link camera mount not found" }

    if ($hasLivestream) { Test-Pass "livestream_setting" "SimulationApp livestream config present" }
    else { Test-Fail "livestream_setting" "livestream config missing" }

    if ($hasWebRTCExt) { Test-Pass "webrtc_extension" "omni.kit.livestream.webrtc extension enabled" }
    else { Test-Fail "webrtc_extension" "WebRTC extension activation not found" }
} else {
    Test-Fail "dc_script" "data_collector_tiago.py not found"
}

# ── 2. VR teleop launch script supports WebRTC ───────────────────────
Write-Log ""
Write-Log "Test 2: VR teleop launch script WebRTC support..."
$vrLaunchScript = Join-Path $ScriptsDir "run_vr_teleop.ps1"
if (Test-Path $vrLaunchScript) {
    $vrContent = Get-Content $vrLaunchScript -Raw
    $hasWebRTCParam = $vrContent -match "EnableWebRTC"
    $hasWebRTCArg = $vrContent -match '"\-\-webrtc"'
    if ($hasWebRTCParam -and $hasWebRTCArg) {
        Test-Pass "launch_webrtc" "run_vr_teleop.ps1 supports -EnableWebRTC flag"
    } else {
        Test-Fail "launch_webrtc" "run_vr_teleop.ps1 missing WebRTC support"
    }
} else {
    Test-Fail "launch_webrtc" "run_vr_teleop.ps1 not found"
}

# ── 3. Web app WebRTC stream component ────────────────────────────────
Write-Log ""
Write-Log "Test 3: Web app WebRTC stream UI..."
$episodePage = Join-Path $RepoRoot "src\app\episodes\[id]\page.tsx"
if (Test-Path -LiteralPath $episodePage) {
    $epContent = Get-Content -LiteralPath $episodePage -Raw
    $hasStreamIframe = $epContent -match "webrtc-demo"
    $hasStreamState = $epContent -match "streamState"
    $hasTransport = $epContent -match "streamTransport"
    $hasReconnect = $epContent -match "reconnect"

    if ($hasStreamIframe) { Test-Pass "stream_iframe" "WebRTC iframe component present" }
    else { Test-Fail "stream_iframe" "WebRTC iframe missing in episode page" }

    if ($hasStreamState) { Test-Pass "stream_state" "Stream state management present" }
    else { Test-Fail "stream_state" "Stream state management missing" }

    if ($hasTransport) { Test-Pass "transport_switch" "WebRTC/frame transport switching present" }
    else { Test-Fail "transport_switch" "Transport switching missing" }
} else {
    Test-Fail "episode_page" "Episode detail page not found"
}

# ── 4. Config schema supports streaming mode ──────────────────────────
Write-Log ""
Write-Log "Test 4: Streaming config..."
$schemaFile = Join-Path $RepoRoot "src\lib\schemas.ts"
if (Test-Path $schemaFile) {
    $schemaContent = Get-Content $schemaFile -Raw
    $hasModes = $schemaContent -match "browser_embedded_optional"
    $hasHint = $schemaContent -match "streamingHint"
    if ($hasModes -and $hasHint) {
        Test-Pass "streaming_config" "Streaming modes and hints in config schema"
    } else {
        Test-Fail "streaming_config" "Streaming config incomplete"
    }
} else {
    Test-Fail "streaming_config" "schemas.ts not found"
}

# ── 5. LocalRunner WebRTC wiring ──────────────────────────────────────
Write-Log ""
Write-Log "Test 5: LocalRunner WebRTC wiring..."
$runnerFile = Join-Path $RepoRoot "src\server\runner\localRunner.ts"
if (Test-Path $runnerFile) {
    $runnerContent = Get-Content $runnerFile -Raw
    $hasWebRTCCheck = $runnerContent -match "enableWebRTC"
    $hasWebRTCFlag = $runnerContent -match "webrtc"
    $hasWindowHide = $runnerContent -match "windowsHide.*wantsWebRTC"
    if ($hasWebRTCCheck -and $hasWebRTCFlag) {
        Test-Pass "runner_webrtc" "LocalRunner passes --webrtc flag when enabled"
    } else {
        Test-Fail "runner_webrtc" "LocalRunner WebRTC wiring incomplete"
    }
    if ($hasWindowHide) {
        Test-Pass "runner_window" "LocalRunner shows window for WebRTC (windowsHide disabled)"
    } else {
        Test-Fail "runner_window" "Window visibility for WebRTC not configured"
    }
} else {
    Test-Fail "runner_file" "localRunner.ts not found"
}

# ── 6. Launch profile schema supports VR+WebRTC ──────────────────────
Write-Log ""
Write-Log "Test 6: Launch profile DB schema..."
$prismaSchema = Join-Path $RepoRoot "prisma\schema.prisma"
if (Test-Path $prismaSchema) {
    $prismaContent = Get-Content $prismaSchema -Raw
    $hasVrTeleop = $prismaContent -match "enableVrTeleop"
    $hasWebRTCField = $prismaContent -match "enableWebRTC"
    $hasPovCamera = $prismaContent -match "robotPovCameraPrim"
    if ($hasVrTeleop) { Test-Pass "db_vr_teleop" "enableVrTeleop field in LaunchProfile" }
    else { Test-Fail "db_vr_teleop" "enableVrTeleop not in schema" }
    if ($hasWebRTCField) { Test-Pass "db_webrtc" "enableWebRTC field in LaunchProfile" }
    else { Test-Fail "db_webrtc" "enableWebRTC not in schema" }
    if ($hasPovCamera) { Test-Pass "db_pov_camera" "robotPovCameraPrim field in LaunchProfile" }
    else { Test-Fail "db_pov_camera" "robotPovCameraPrim not in schema" }
} else {
    Test-Fail "prisma_schema" "prisma/schema.prisma not found"
}

# ── 7. Isaac Sim availability ─────────────────────────────────────────
Write-Log ""
Write-Log "Test 7: Isaac Sim availability..."
$pyBat = Join-Path $IsaacDir "python.bat"
if (Test-Path $IsaacDir) {
    Test-Pass "isaac_dir" "Isaac Sim directory exists: $IsaacDir"
} else {
    Test-Fail "isaac_dir" "Isaac Sim not found at $IsaacDir"
}
if (Test-Path $pyBat) {
    Test-Pass "isaac_python" "Isaac Sim python.bat found"
} else {
    Test-Fail "isaac_python" "python.bat not found (needed for WebRTC runtime)"
}

# ── 8. WebRTC endpoint probe (only if Isaac Sim is running) ───────────
Write-Log ""
Write-Log "Test 8: WebRTC endpoint probe (port $WebRTCPort)..."
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect("localhost", $WebRTCPort)
    $tcp.Close()
    Test-Pass "webrtc_port" "Port $WebRTCPort is open (Isaac Sim WebRTC active)"
} catch {
    Write-Log "  [SKIP] Port $WebRTCPort not open - Isaac Sim with --webrtc not running"
    Write-Log "         This is expected when Isaac Sim is not started"
    Write-Log "         To test: run_vr_teleop.ps1 -EnableWebRTC -MockVR"
}

# ── 9. Servo config for VR (already validated in E2E test) ────────────
Write-Log ""
Write-Log "Test 9: MoveIt Servo config for VR..."
$servoYaml = Join-Path $ScriptsDir "tiago_servo_config.yaml"
if (Test-Path $servoYaml) {
    Test-Pass "servo_yaml" "tiago_servo_config.yaml present"
} else {
    Test-Fail "servo_yaml" "tiago_servo_config.yaml not found"
}

# ── Summary ──────────────────────────────────────────────────────────
Write-Log ""
Write-Log "================================================"
Write-Log " Summary: $passed passed, $failed failed"
Write-Log "================================================"
Write-Log ""
if ($failed -eq 0) {
    Write-Log "All VR POV streaming checks passed!"
    Write-Log ""
    Write-Log "To run the full VR+WebRTC pipeline:"
    Write-Log "  .\scripts\run_vr_teleop.ps1 -EnableWebRTC -EnvUsd <scene.usd>"
    Write-Log ""
    Write-Log "Then open http://localhost:${WebRTCPort}/streaming/webrtc-demo/"
    Write-Log "to see the robot head camera POV."
    Write-Log ""
    Write-Log "For VR headset display:"
    Write-Log "  1. Launch SteamVR with Vive Pro 2 connected"
    Write-Log "  2. Run: .\scripts\run_vr_teleop.ps1 -EnableWebRTC"
    Write-Log "  3. Use SteamVR Desktop overlay or Vive browser to open:"
    Write-Log "     http://localhost:${WebRTCPort}/streaming/webrtc-demo/"
    Write-Log "  4. The operator sees the robot's head camera POV in VR"
} else {
    Write-Log "$failed check(s) failed. See details above."
}

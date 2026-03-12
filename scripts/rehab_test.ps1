param(
    [ValidateSet("stand", "arm", "gripper", "cube_grasp", "all")]
    [string]$Phase = "all",
    [int]$Duration = 30,
    [string]$TiagoUsd = "C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional_light.usd",
    [string]$EnvUsd = "C:\RoboLab_Data\scenes\Small_House_Interactive.usd",
    [string]$IsaacPython = "C:\Users\max\Documents\IsaacSim\python.bat",
    [string]$Ros2DllDir = "C:\Users\max\Mambaforge\envs\ros2_humble\Library\bin",
    [string]$Ros2SitePackages = "C:\Users\max\Mambaforge\envs\ros2_humble\Lib\site-packages"
)

$ErrorActionPreference = "Stop"
$pfx = "[Rehab]"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $PSScriptRoot "data_collector_tiago.py"
$RunStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunLogDir = Join-Path $RepoRoot ("logs\rehab\" + $RunStamp)
[void](New-Item -ItemType Directory -Force -Path $RunLogDir)

$phases = if ($Phase -eq "all") { @("stand", "arm", "gripper", "cube_grasp") } else { @($Phase) }

# Set up ROS2 environment (needed even for non-MoveIt runs).
$pathItems = ($env:Path -split ';' | Where-Object {
    $_ -and ($_ -notmatch 'Mambaforge\\envs\\base') -and ($_ -notmatch 'Miniconda')
})
$env:Path = ($Ros2DllDir + ';' + ($pathItems -join ';'))
$env:HOME = "C:\Users\max"
$env:ROS_DISTRO = "humble"
$env:RMW_IMPLEMENTATION = "rmw_fastrtps_cpp"
$env:PYTHONUNBUFFERED = "1"
$env:ROBOLAB_ROS2_BRIDGE_ORDER = "skip"
$env:FJT_PROXY_DIR = "C:\RoboLab_Data\fjt_proxy"

foreach ($p in $phases) {
    Write-Host ""
    Write-Host "$pfx ===== Phase: $p ($Duration sec) ====="
    $outLog = Join-Path $RunLogDir "$p.out.log"
    $errLog = Join-Path $RunLogDir "$p.err.log"
    $episodeDir = Join-Path $RunLogDir $p
    [void](New-Item -ItemType Directory -Force -Path $episodeDir)

    $collectorArgs = @(
        $ScriptPath,
        "--env", $EnvUsd,
        "--tiago-usd", $TiagoUsd,
        "--output_dir", $episodeDir,
        "--duration", $Duration,
        "--headless",
        "--require-real-tiago",
        "--ros2-dll-dir", $Ros2DllDir,
        "--ros2-site-packages", $Ros2SitePackages,
        "--task-label", "rehab_$p"
    )

    switch ($p) {
        "stand" {
            # No objects, no MoveIt, no cameras. Just stand still.
        }
        "arm" {
            # No objects. MoveIt proxy enabled so PD drives track targets.
            $collectorArgs += @("--moveit")
        }
        "gripper" {
            # No objects. MoveIt proxy enabled.
            $collectorArgs += @("--moveit")
        }
        "cube_grasp" {
            # Spawn a single object, MoveIt enabled.
            $collectorArgs += @(
                "--moveit",
                "--spawn-objects",
                "--objects-dir", "C:\RoboLab_Data\data\object_sets",
                "--single-object"
            )
        }
    }

    $argStr = ($collectorArgs | ForEach-Object { "`"$_`"" }) -join " "
    Write-Host "$pfx Running: $IsaacPython $argStr"

    $proc = Start-Process -FilePath $IsaacPython `
        -ArgumentList $argStr `
        -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog

    $timeout = $Duration + 120
    if (-not $proc.WaitForExit($timeout * 1000)) {
        Write-Host "$pfx WARN: $p timed out after $timeout sec, killing"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }

    $exitCode = $proc.ExitCode
    Write-Host "$pfx Phase $p finished (exit=$exitCode)"

    # Analyze output
    $content = Get-Content $outLog -ErrorAction SilentlyContinue
    if ($content) {
        $driftLines = $content | Select-String "base drift"
        $coordLines = $content | Select-String "COORD_MON"
        $jointLines = $content | Select-String "TRAJ_DIAG"
        $velLines   = $content | Select-String "VEL_DIAG"

        if ($driftLines) {
            Write-Host "$pfx   Base drift warnings: $($driftLines.Count)"
            $driftLines | Select-Object -Last 3 | ForEach-Object { Write-Host "$pfx     $_" }
        } else {
            Write-Host "$pfx   Base drift: NONE (good)"
        }

        if ($coordLines) {
            Write-Host "$pfx   COORD_MON entries: $($coordLines.Count)"
            Write-Host "$pfx   First:"
            $coordLines | Select-Object -First 1 | ForEach-Object { Write-Host "$pfx     $_" }
            Write-Host "$pfx   Last:"
            $coordLines | Select-Object -Last 1 | ForEach-Object { Write-Host "$pfx     $_" }
        }

        if ($jointLines) {
            Write-Host "$pfx   TRAJ_DIAG entries: $($jointLines.Count)"
            $jointLines | Select-Object -Last 2 | ForEach-Object { Write-Host "$pfx     $_" }
        }

        if ($velLines) {
            Write-Host "$pfx   VEL_DIAG entries: $($velLines.Count)"
            $velLines | Select-Object -Last 1 | ForEach-Object { Write-Host "$pfx     $_" }
        }
    } else {
        Write-Host "$pfx   WARN: output log is empty"
    }

    Write-Host "$pfx   Logs: out=$outLog err=$errLog"

    if ($exitCode -ne 0 -and $Phase -eq "all") {
        Write-Host "$pfx STOPPING: phase $p failed with exit=$exitCode"
        break
    }
}

Write-Host ""
Write-Host "$pfx All phases complete. Logs in: $RunLogDir"

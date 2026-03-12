param(
    [ValidateSet("stand", "arm", "gripper", "cube_grasp", "all")]
    [string]$Phase = "all",
    [int]$Duration = 40,
    [string]$TiagoUsd = "C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional_light.usd",
    [string]$EnvUsd = "C:\RoboLab_Data\scenes\Small_House_Interactive.usd"
)

$ErrorActionPreference = "Stop"
$pfx = "[RehabMoveIt]"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ExecSmoke = Join-Path $PSScriptRoot "run_tiago_moveit_execute_smoke.ps1"

if (-not (Test-Path $ExecSmoke)) {
    throw "Script not found: $ExecSmoke"
}

$phases = if ($Phase -eq "all") { @("stand", "arm", "gripper", "cube_grasp") } else { @($Phase) }

foreach ($p in $phases) {
    Write-Host ""
    Write-Host "$pfx ===== Phase: $p ($Duration sec) ====="
    
    $commonArgs = @(
        "-Duration", $Duration,
        "-TiagoUsd", $TiagoUsd,
        "-EnvUsd", $EnvUsd,
        "-MaxRetriesPerIntent", 0,
        "-RetryOnCodeMinus4", $false
    )
    
    switch ($p) {
        "stand" {
            # No intents, just start and stand
            $intentSeq = "go_home"
        }
        "arm" {
            # Safe arm-only poses: home -> workzone -> home (no objects, no gripper)
            $intentSeq = "go_home,approach_workzone,go_home"
        }
        "gripper" {
            # Test gripper mechanism (often implicitly tested in pick intents, 
            # or we just run a sequence that forces gripper use)
            $intentSeq = "plan_pick_sink"
        }
        "cube_grasp" {
            # Spawn a cube and try to pick it
            $commonArgs += @("-SpawnObjects", "-SingleObject")
            $intentSeq = "plan_pick_table"
        }
    }
    
    $commonArgs += @("-IntentSequence", $intentSeq)
    
    # Convert $commonArgs to a string suitable for -Command, preserving types
    # This requires careful handling of booleans and other types.
    # For simplicity, we'll join them as strings, which is usually sufficient for script parameters.
    # If true boolean passing is critical, a more complex serialization might be needed.
    $scriptArgsString = ($commonArgs | ForEach-Object {
        if ($_ -is [bool]) {
            if ($_ -eq $true) { "`$true" } else { "`$false" }
        } elseif ($_ -is [string] -and ($_.Contains(" ") -or $_.Contains(","))) {
            "'" + $_.Replace("'", "''") + "'" # Quote strings with spaces or commas
        } else {
            $_
        }
    }) -join ' '

    Write-Host "$pfx Running: powershell.exe -Command & `'$ExecSmoke`' $scriptArgsString"
    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList (@("-ExecutionPolicy", "Bypass", "-Command", "& `'$ExecSmoke`' $scriptArgsString")) -PassThru -Wait
    
    $exitCode = $proc.ExitCode
    Write-Host "$pfx Phase $p finished (exit=$exitCode)"
    
    if ($exitCode -ne 0 -and $Phase -eq "all") {
        Write-Host "$pfx STOPPING: phase $p failed with exit=$exitCode"
        break
    }
}

Write-Host ""
Write-Host "$pfx All phases complete."

import { Runner, DiagnosticReport, StartResult, StopResult, StatusSnapshot } from "./Runner";
import { acquireLock, releaseLock } from "../hostLock";
import { NodeSSH } from "node-ssh";

export class SshRunner implements Runner {

    private async connect(config: any): Promise<NodeSSH> {
        const ssh = new NodeSSH();
        // MVP: Assuming basic password auth or Agent auth. 
        // For production, these should be securely stored secrets or ssh keys.
        const hostPath = config.isaacHost.split('@');
        const username = hostPath.length > 1 ? hostPath[0] : 'max'; // Fallback to provided user
        const host = hostPath.length > 1 ? hostPath[1] : config.isaacHost;

        const connectionConfig: any = {
            host: host,
            port: config.isaacSshPort || 22,
            username: config.isaacUser || username,
        };

        if (config.isaacAuthMode === 'ssh_key' && config.sshKeyPath) {
            connectionConfig.privateKeyPath = config.sshKeyPath.replace('~', process.env.HOME || '');
        } else if (config.isaacAuthMode === 'password' && config.sshPassword) {
            connectionConfig.password = config.sshPassword;
        }

        // Fallback to agent if available
        if (process.env.SSH_AUTH_SOCK) {
            connectionConfig.agent = process.env.SSH_AUTH_SOCK;
        }

        await ssh.connect(connectionConfig);

        // Catch underlying socket errors that occur after execution is finished to avoid crashing the node process
        if (ssh.connection) {
            ssh.connection.on('error', (err: any) => {
                if (err.code !== 'ECONNRESET') {
                    console.error("[NodeSSH] Background connection error:", err.message);
                }
            });
        }

        return ssh;
    }

    async testConnection(config: any): Promise<DiagnosticReport> {
        const start = Date.now();
        let ssh: NodeSSH | null = null;
        try {
            ssh = await this.connect(config);
            const result = await ssh.execCommand('echo "SSH Connection Successful"');

            return {
                isaacHostReachable: true,
                sshReachable: result.code === 0,
                resolvedIp: config.isaacHost,
                latencyMs: Date.now() - start,
                errors: result.code !== 0 ? [result.stderr] : [],
                recommendations: result.code === 0 ? ["SSH connection verified."] : ["Check SSH credentials and network access."]
            };
        } catch (e: any) {
            return {
                isaacHostReachable: false,
                sshReachable: false,
                resolvedIp: config.isaacHost,
                latencyMs: Date.now() - start,
                errors: [e.message],
                recommendations: ["Ensure the remote host is powered on and accessible via SSH on port 22."]
            };
        } finally {
            if (ssh) ssh.dispose();
        }
    }

    async startEpisode(episode: any, config: any): Promise<StartResult> {
        const locked = await acquireLock(config.isaacHost, episode.id);
        if (!locked) {
            return { success: false, error: `Host ${config.isaacHost} is currently locked by another episode.` };
        }

        let ssh: NodeSSH | null = null;
        try {
            ssh = await this.connect(config);

            // 1. Path to Isaac Sim on remote
            // The SSH User might be varied ("m", "max"), but the installation path is now configurable
            const remoteIsaacDir = config.isaacInstallPath || `C:\\Users\\max\\Documents\\IsaacSim`;
            const remoteScriptPath = `${remoteIsaacDir}\\run_episode.py`;
            const localScriptPath = require('path').resolve(process.cwd(), 'scripts/run_episode.py');

            // 2. Upload the script
            try {
                await ssh.putFile(localScriptPath, remoteScriptPath);
            } catch (err: any) {
                console.error("[SshRunner] SFTP Upload failed:", err.message);
                throw new Error("Failed to upload run_episode.py to remote host.");
            }

            // 3. Prepare the command
            const remoteOutDir = config.defaultOutputDir || 'C:\\RoboLab_Data';
            const episodeOutDir = `${remoteOutDir}\\episodes\\${episode.id}`;
            const windowTitle = `RoboLab_Episode_${episode.id}`;

            // Create command to run python.bat
            const pyBat = `${remoteIsaacDir}\\python.bat`;

            // Allow override via LaunchProfile, otherwise fallback. If it's an empty string, fallback.
            let launchCmd = episode.launchProfile?.isaacLaunchTemplate;
            if (!launchCmd || launchCmd.trim() === "") {
                launchCmd = `"${pyBat}" "${remoteScriptPath}" --output_dir "${episodeOutDir}" --duration ${episode.durationSec || 60}`;
            }

            // Trigger a powershell Invoke-WmiMethod to run detached, forcing python to render unbuffered output
            // This is required for Windows targets because Start-Process fails to pipe stdout/stderr from complex .bat files correctly when fully detached
            const escapedLaunchCmd = launchCmd.replace(/"/g, '\\"');

            // Create a temporary batch file to encapsulate the exact launch command to bypass PowerShell string parsing hell over SSH
            const runBatPath = `${remoteOutDir}\\episodes\\${episode.id}_run.bat`;
            const batLines = `"@('@echo off', 'set PYTHONUNBUFFERED=1', 'title ${windowTitle}', '${escapedLaunchCmd}')"`;
            await ssh.execCommand(`powershell -Command "Set-Content -Path '${runBatPath}' -Value ${batLines} -Encoding Ascii"`);

            const psCmd = `powershell -Command "$proc = Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList 'cmd.exe /c ${runBatPath} > ${episodeOutDir}_stdout.log 2> ${episodeOutDir}_stderr.log'; $proc.ProcessId | Out-File -FilePath '${episodeOutDir}_pid.txt' -Encoding ascii"`;

            // Ensure output dir exists remotely
            await ssh.execCommand(`powershell -Command "New-Item -ItemType Directory -Force -Path '${remoteOutDir}\\episodes' -ErrorAction SilentlyContinue"`);

            const result = await ssh.execCommand(`cd /d "${remoteIsaacDir}" && ${psCmd}`);

            if (result.code !== 0 && result.code !== null) {
                await releaseLock(config.isaacHost, episode.id);
                return { success: false, error: `Launch failed: ${result.stderr}` };
            }

            return { success: true };
        } catch (e: any) {
            await releaseLock(config.isaacHost, episode.id);
            return { success: false, error: e.message };
        } finally {
            if (ssh) ssh.dispose();
        }
    }

    async stopEpisode(episode: any, config: any): Promise<StopResult> {
        let ssh: NodeSSH | null = null;
        try {
            ssh = await this.connect(config);
            const remoteOutDir = config.defaultOutputDir || 'C:\\RoboLab_Data';
            const episodeOutDir = `${remoteOutDir}\\episodes\\${episode.id}`;

            // Read the exact PID and kill the process tree
            const psCmd = `
                $pidFile = '${episodeOutDir}_pid.txt'
                if (Test-Path $pidFile) {
                    $procId = Get-Content $pidFile | ForEach-Object { [int]$_ }
                    if ($procId -gt 0) {
                        # taskkill /T kills the process tree (cmd.exe and the child python.exe)
                        taskkill /F /PID $procId /T
                    }
                } else {
                    Write-Host "No PID file found, falling back to window title."
                    taskkill /F /FI "WINDOWTITLE eq RoboLab_Episode_${episode.id}*" /T
                }
            `.trim().replace(/\n/g, ';');

            const result = await ssh.execCommand(`powershell -Command "${psCmd}"`);

            // Release lock regardless of kill success (it might have already died)
            await releaseLock(config.isaacHost, episode.id);

            return { success: true };
        } catch (e: any) {
            await releaseLock(config.isaacHost, episode.id);
            return { success: false, error: e.message };
        } finally {
            if (ssh) ssh.dispose();
        }
    }

    async getLiveStatus(episode: any, config: any): Promise<StatusSnapshot> {
        let ssh: NodeSSH | null = null;
        try {
            ssh = await this.connect(config);
            const remoteOutDir = config.defaultOutputDir || 'C:\\RoboLab_Data';
            const episodeOutDir = `${remoteOutDir}\\episodes\\${episode.id}`;

            // Read the PID from the saved file and check if it is running
            const psCmd = `
                $pidFile = '${episodeOutDir}_pid.txt'
                if (Test-Path $pidFile) {
                    $procId = Get-Content $pidFile | ForEach-Object { [int]$_ }
                    if ($procId -gt 0) {
                        $running = Get-Process -Id $procId -ErrorAction SilentlyContinue
                        if ($running) {
                            Write-Output "RUNNING"
                        } else {
                            Write-Output "COMPLETED"
                        }
                    } else {
                        Write-Output "COMPLETED"
                    }
                } else {
                    Write-Output "WAITING"
                }
            `.trim().replace(/\n/g, ';');

            const res = await ssh.execCommand(`powershell -Command "${psCmd}"`);
            const statusStr = res.stdout.trim();
            const isRunning = statusStr === "RUNNING" || statusStr === "WAITING"; // Treat waiting for pid file as running to avoid premature completion

            return {
                status: isRunning ? "running" : "completed",
                uptimeSec: Math.floor((Date.now() - new Date(episode.startedAt || Date.now()).getTime()) / 1000),
                cpuUsage: isRunning ? 15 : 0,  // Dummy for now, can be parsed from detailed wmic
                memoryUsage: isRunning ? 80 : 0
            };
        } catch (e: any) {
            // Silently fail on connection reset during polling to avoid blowing up the UI
            if (e.code !== 'ECONNRESET') {
                console.error("[SshRunner] getLiveStatus error:", e.message);
            }
            return {
                status: "running", // Assume it's still running if we just lost SSH momentarily
                uptimeSec: Math.floor((Date.now() - new Date(episode.startedAt || Date.now()).getTime()) / 1000),
                cpuUsage: 0,
                memoryUsage: 0
            };
        } finally {
            if (ssh) ssh.dispose();
        }
    }

    async getLiveLogs(episode: any, config: any, lines: number = 20): Promise<string[]> {
        let ssh: NodeSSH | null = null;
        try {
            ssh = await this.connect(config);
            // Replace backward slashes with forward slashes for Powershell string paths
            const episodeOutDir = episode.outputDir ? episode.outputDir.replace(/\\/g, '/') : `C:/RoboLab_Data/episodes/${episode.id}`;

            const cmd = `powershell -Command "if (Test-Path '${episodeOutDir}_stdout.log') { Get-Content -Path '${episodeOutDir}_stdout.log' -Tail ${lines} } else { echo 'Waiting for log file generation...' }"`;
            const res = await ssh.execCommand(cmd);

            // Split by newline and remove empty/whitespace lines
            return res.stdout.split('\n')
                .map(l => l.trim())
                .filter(l => l.length > 0);
        } catch (e: any) {
            console.error("[SshRunner] getLiveLogs error:", e.message);
            return ["[SshRunner] Failed to fetch live logs."];
        } finally {
            if (ssh) ssh.dispose();
        }
    }

    async syncData(episode: any, config: any): Promise<{ success: boolean; error?: string }> {
        let ssh: NodeSSH | null = null;
        try {
            ssh = await this.connect(config);
            const remoteOutDir = config.defaultOutputDir || 'C:\\RoboLab_Data';
            const episodeOutDir = `${remoteOutDir}\\episodes\\${episode.id}`;
            const localOutDir = require('path').resolve(process.cwd(), `public/episodes/${episode.id}`);

            require('fs').mkdirSync(localOutDir, { recursive: true });

            // Using powershell to list files, since node-ssh doesn't have a reliable sftp list for windows sometimes.
            // Alternatively, simply attempt to download known files.
            const filesToSync = [
                "telemetry.json",
                "camera_0.mp4"
            ];

            let syncedCount = 0;
            for (const file of filesToSync) {
                try {
                    await ssh.getFile(`${localOutDir}/${file}`, `${episodeOutDir}\\${file}`);
                    syncedCount++;
                } catch (err) {
                    console.log(`[SshRunner] Could not sync ${file} (might not exist yet)`);
                }
            }

            return { success: syncedCount > 0, error: syncedCount === 0 ? "No files found to sync." : undefined };

        } catch (e: any) {
            console.error("[SshRunner] syncData error:", e.message);
            return { success: false, error: e.message };
        } finally {
            if (ssh) ssh.dispose();
        }
    }
}

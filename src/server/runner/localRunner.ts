import { Runner, DiagnosticReport, StartResult, StopResult, StatusSnapshot } from "./Runner";
import { acquireLock, releaseLock } from "../hostLock";
import fs from "fs";
import path from "path";
import { execFile, spawn } from "child_process";

export class LocalRunner implements Runner {
    private resolveEnvironmentUsd(episode: any): string {
        const configured = (episode.launchProfile?.environmentUsd || episode.scene?.stageUsdPath || "").trim();
        if (configured && !configured.startsWith("/Isaac/")) {
            return configured;
        }

        const defaultHome = "C:\\RoboLab_Data\\scenes\\Small_House_Interactive.usd";
        const defaultOffice = "C:\\RoboLab_Data\\scenes\\Office_Interactive.usd";
        const sceneName = (episode.scene?.name || "").toLowerCase();
        const sceneType = (episode.scene?.type || "").toLowerCase();
        const prefersOffice = sceneName.includes("office") || sceneType === "office";
        const candidate = prefersOffice ? defaultOffice : defaultHome;

        if (fs.existsSync(candidate)) {
            return candidate;
        }
        return configured || candidate;
    }

    private buildEpisodePaths(config: any, episodeId: string) {
        const baseOutputDir = config.defaultOutputDir || "C:\\RoboLab_Data";
        const episodeOutDir = path.join(baseOutputDir, "episodes", episodeId);
        return {
            baseOutputDir,
            episodeOutDir,
            pidFile: `${episodeOutDir}_pid.txt`,
            stdoutLog: `${episodeOutDir}_stdout.log`,
            stderrLog: `${episodeOutDir}_stderr.log`,
        };
    }

    private execFileAsync(file: string, args: string[]): Promise<void> {
        return new Promise((resolve, reject) => {
            execFile(file, args, { windowsHide: true }, (error) => {
                if (error) {
                    reject(error);
                    return;
                }
                resolve();
            });
        });
    }

    private isPidRunning(pid: number): boolean {
        if (!Number.isInteger(pid) || pid <= 0) return false;
        try {
            process.kill(pid, 0);
            return true;
        } catch {
            return false;
        }
    }

    async testConnection(config: any): Promise<DiagnosticReport> {
        const isaacDir = config.isaacInstallPath || "C:\\Users\\max\\Documents\\IsaacSim";
        const pyBat = path.join(isaacDir, "python.bat");
        return {
            isaacHostReachable: fs.existsSync(isaacDir),
            sshReachable: null,
            resolvedIp: "localhost",
            latencyMs: 1,
            errors: fs.existsSync(pyBat) ? [] : [`Isaac Sim executable not found: ${pyBat}`],
            recommendations: fs.existsSync(pyBat)
                ? ["Local mode active. Isaac Sim launch script detected."]
                : ["Set Isaac Sim Install Path to a valid local folder containing python.bat."],
        };
    }

    async startEpisode(episode: any, config: any): Promise<StartResult> {
        const locked = await acquireLock(config.isaacHost, episode.id);
        if (!locked) {
            return { success: false, error: `Host ${config.isaacHost} is currently locked by another episode.` };
        }

        const { episodeOutDir, pidFile, stdoutLog, stderrLog } = this.buildEpisodePaths(config, episode.id);

        try {
            fs.mkdirSync(episodeOutDir, { recursive: true });

            const meta = {
                ...episode,
                startedAt: new Date(),
                frozenConfigSnapshot: config
            };
            fs.writeFileSync(path.join(episodeOutDir, "metadata.json"), JSON.stringify(meta, null, 2));

            const launchFromProfile = episode.launchProfile?.isaacLaunchTemplate?.trim();
            let detachedCommand = "";

            if (launchFromProfile) {
                detachedCommand = launchFromProfile;
                console.log(`[LocalRunner] Executing template: ${launchFromProfile}`);
            } else {
                const isaacDir = config.isaacInstallPath || "C:\\Users\\max\\Documents\\IsaacSim";
                const pyBat = path.join(isaacDir, "python.bat");
                const scriptName = episode.launchProfile?.scriptName || "data_collector_tiago.py";
                const scriptPath = path.resolve(process.cwd(), "scripts", scriptName);
                const duration = episode.durationSec || 60;
                const escapedOutputDir = episodeOutDir.replace(/'/g, "''");
                const escapedScriptPath = scriptPath.replace(/'/g, "''");
                const escapedPyBat = pyBat.replace(/'/g, "''");
                const envUsd = this.resolveEnvironmentUsd(episode);
                const escapedEnvUsd = envUsd.replace(/'/g, "''");
                let psCmd = `& '${escapedPyBat}' '${escapedScriptPath}' --env '${escapedEnvUsd}' --output_dir '${escapedOutputDir}' --duration ${duration} --headless`;

                if (!fs.existsSync(pyBat)) {
                    throw new Error(`Isaac Sim executable not found: ${pyBat}`);
                }
                if (!fs.existsSync(scriptPath)) {
                    throw new Error(`Episode script not found: ${scriptPath}`);
                }
                if (episode.launchProfile?.enableWebRTC) {
                    psCmd += " --webrtc";
                }
                if (episode.launchProfile?.enableVrTeleop) {
                    psCmd += " --vr";
                }
                if (episode.launchProfile?.enableMoveIt) {
                    psCmd += " --moveit";
                }
                if (episode.launchProfile?.robotPovCameraPrim) {
                    const escapedPov = String(episode.launchProfile.robotPovCameraPrim).replace(/'/g, "''");
                    psCmd += ` --robot_pov_camera_prim '${escapedPov}'`;
                }

                detachedCommand = `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "${psCmd}"`;
                console.log(`[LocalRunner] Executing: ${psCmd}`);
            }

            const cmdWithLogs = `${detachedCommand} 1> "${stdoutLog}" 2> "${stderrLog}"`;
            const child = spawn(cmdWithLogs, {
                detached: true,
                windowsHide: true,
                shell: true,
                stdio: "ignore",
            });
            child.unref();
            fs.writeFileSync(pidFile, String(child.pid), "utf8");
            return { success: true };
        } catch (e: any) {
            await releaseLock(config.isaacHost, episode.id);
            return { success: false, error: e.message };
        }
    }

    async stopEpisode(episode: any, config: any): Promise<StopResult> {
        const { episodeOutDir, pidFile } = this.buildEpisodePaths(config, episode.id);
        await releaseLock(config.isaacHost, episode.id);
        console.log(`[LocalRunner] Stopping local process for episode ${episode.id}`);

        try {
            if (fs.existsSync(pidFile)) {
                const rawPid = fs.readFileSync(pidFile, "utf8").trim();
                const pid = Number(rawPid);
                if (this.isPidRunning(pid)) {
                    await this.execFileAsync("taskkill", ["/F", "/T", "/PID", String(pid)]);
                }
            }

            const metaPath = path.join(episodeOutDir, "metadata.json");
            if (fs.existsSync(metaPath)) {
                const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
                meta.stoppedAt = new Date();
                fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
            }

        } catch (e) { }

        return { success: true };
    }

    async getLiveStatus(episode: any, config: any): Promise<StatusSnapshot> {
        const { pidFile } = this.buildEpisodePaths(config, episode.id);
        const uptimeSec = Math.floor((Date.now() - new Date(episode.startedAt || Date.now()).getTime()) / 1000);
        let isRunning = false;

        if (fs.existsSync(pidFile)) {
            const pid = Number(fs.readFileSync(pidFile, "utf8").trim());
            isRunning = this.isPidRunning(pid);
        }

        return {
            status: isRunning ? "running" : "completed",
            uptimeSec,
            cpuUsage: 0,
            memoryUsage: 0
        };
    }

    async getLiveLogs(episode: any, config: any, lines: number = 20): Promise<string[]> {
        const { stdoutLog } = this.buildEpisodePaths(config, episode.id);
        if (!fs.existsSync(stdoutLog)) {
            return ["Waiting for log file generation..."];
        }

        const content = fs.readFileSync(stdoutLog, "utf8");
        return content
            .split(/\r?\n/)
            .map((line) => line.trim())
            .filter((line) => line.length > 0)
            .slice(-lines);
    }

    async syncData(episode: any, config: any): Promise<{ success: boolean; error?: string }> {
        const { episodeOutDir } = this.buildEpisodePaths(config, episode.id);
        const localOutDir = path.resolve(process.cwd(), `public/episodes/${episode.id}`);
        try {
            fs.mkdirSync(localOutDir, { recursive: true });
            const filesToSync = [
                "metadata.json",
                "dataset.json",
                "dataset_manifest.json",
                "telemetry.json",
                "camera_0.mp4",
            ];

            let copied = 0;
            for (const fileName of filesToSync) {
                const source = path.join(episodeOutDir, fileName);
                const target = path.join(localOutDir, fileName);
                if (fs.existsSync(source)) {
                    fs.copyFileSync(source, target);
                    copied++;
                }
            }
            if (copied === 0) {
                return { success: false, error: "No files found to sync." };
            }
            return { success: true };
        } catch (e: any) {
            return { success: false, error: e.message };
        }
    }
}

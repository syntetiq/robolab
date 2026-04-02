import { Runner, DiagnosticReport, StartResult, StopResult, StatusSnapshot } from "./Runner";
import { acquireLock, releaseLock } from "../hostLock";
import fs from "fs";
import path from "path";
import { execFile, spawn } from "child_process";

export class LocalRunner implements Runner {
    private getLatestModifiedMs(targetPath: string): number {
        try {
            if (!fs.existsSync(targetPath)) return 0;
            const stat = fs.statSync(targetPath);
            if (!stat.isDirectory()) return stat.mtimeMs || 0;
            let latest = stat.mtimeMs || 0;
            const stack = [targetPath];
            while (stack.length > 0) {
                const current = stack.pop() as string;
                const entries = fs.readdirSync(current, { withFileTypes: true });
                for (const entry of entries) {
                    const full = path.join(current, entry.name);
                    try {
                        if (entry.isDirectory()) {
                            stack.push(full);
                            continue;
                        }
                        const childStat = fs.statSync(full);
                        if (childStat.mtimeMs > latest) latest = childStat.mtimeMs;
                    } catch {
                        // ignore per-file stat errors
                    }
                }
            }
            return latest;
        } catch {
            return 0;
        }
    }

    private resolveEnvironmentUsd(episode: any): string {
        // Respect scene selection from episode wizard first.
        const sceneUsd = (episode.scene?.stageUsdPath || "").trim();
        if (sceneUsd && !sceneUsd.startsWith("/Isaac/")) {
            return sceneUsd;
        }

        const profileUsd = (episode.launchProfile?.environmentUsd || "").trim();
        if (profileUsd && !profileUsd.startsWith("/Isaac/")) {
            return profileUsd;
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
        return sceneUsd || profileUsd || candidate;
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
            let psCmd = "";

            if (launchFromProfile) {
                detachedCommand = launchFromProfile;
                psCmd = launchFromProfile;
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
                const wantsWebRTC = !!episode.launchProfile?.enableWebRTC;
                const wantsGui = !!episode.launchProfile?.enableGuiMode;
                psCmd = `& '${escapedPyBat}' '${escapedScriptPath}' --env '${escapedEnvUsd}' --output_dir '${escapedOutputDir}' --duration ${duration}`;
                if (!wantsWebRTC && !wantsGui) {
                    psCmd += " --headless";
                }

                if (!fs.existsSync(pyBat)) {
                    throw new Error(`Isaac Sim executable not found: ${pyBat}`);
                }
                if (!fs.existsSync(scriptPath)) {
                    throw new Error(`Episode script not found: ${scriptPath}`);
                }
                if (wantsWebRTC) {
                    psCmd += " --webrtc";
                }
                if (wantsGui && !wantsWebRTC) {
                    psCmd += " --gui";
                }
                if (episode.launchProfile?.enableVrTeleop) {
                    psCmd += " --vr";
                }
                if (episode.launchProfile?.enableMoveIt) {
                    psCmd += " --moveit";
                    psCmd += " --mobile-base";
                }
                if (episode.objectSetId && episode.objectSet) {
                    psCmd += " --spawn-objects";
                    try {
                        const assetPaths: string[] = JSON.parse(episode.objectSet.assetPaths || "[]");
                        if (assetPaths.length > 0 && fs.existsSync(assetPaths[0])) {
                            const objectsDir = path.dirname(assetPaths[0]).replace(/'/g, "''");
                            psCmd += ` --objects-dir '${objectsDir}'`;
                        }
                    } catch {
                        // assetPaths not parseable or empty; fall back to default objects dir
                    }
                }
                if (episode.launchProfile?.robotPovCameraPrim) {
                    const escapedPov = String(episode.launchProfile.robotPovCameraPrim).replace(/'/g, "''");
                    psCmd += ` --robot_pov_camera_prim '${escapedPov}'`;
                }

                detachedCommand = `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "${psCmd}"`;
                console.log(`[LocalRunner] Executing: ${psCmd}`);
            }

            const wantsVisible = !!episode.launchProfile?.enableWebRTC || !!episode.launchProfile?.enableGuiMode;
            let child: ReturnType<typeof spawn>;
            if (wantsVisible) {
                const launcherScript = path.join(episodeOutDir, "_launch.ps1");
                fs.writeFileSync(launcherScript, psCmd, "utf8");
                const startCmd = `start "IsaacSim" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${launcherScript}"`;
                child = spawn(startCmd, {
                    detached: true,
                    shell: true,
                    stdio: "ignore",
                });
            } else {
                const cmdWithLogs = `${detachedCommand} 1> "${stdoutLog}" 2> "${stderrLog}"`;
                child = spawn(cmdWithLogs, {
                    detached: true,
                    windowsHide: true,
                    shell: true,
                    stdio: "ignore",
                });
            }
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
        const { pidFile, episodeOutDir, stdoutLog, stderrLog } = this.buildEpisodePaths(config, episode.id);
        const uptimeSec = Math.floor((Date.now() - new Date(episode.startedAt || Date.now()).getTime()) / 1000);
        let isRunning = false;

        if (fs.existsSync(pidFile)) {
            const pid = Number(fs.readFileSync(pidFile, "utf8").trim());
            isRunning = this.isPidRunning(pid);
        }

        if (!isRunning && (!!episode.launchProfile?.enableGuiMode || !!episode.launchProfile?.enableWebRTC || !!episode.launchProfile?.enableMoveIt)) {
            try {
                const { execSync } = require("child_process");
                const out = execSync('tasklist /FI "IMAGENAME eq kit.exe" /NH', { encoding: "utf8", timeout: 3000 });
                if (out.includes("kit.exe")) {
                    isRunning = true;
                }
            } catch {}
            if (!isRunning) {
                try {
                    const jsFile = path.join(config.defaultOutputDir || "C:\\RoboLab_Data", "fjt_proxy", "joint_state.json");
                    if (fs.existsSync(jsFile)) {
                        const age = Date.now() - fs.statSync(jsFile).mtimeMs;
                        if (age < 5000) {
                            isRunning = true;
                        }
                    }
                } catch {}
            }
        }

        if (isRunning) {
            const isGuiOrTeleop = !!episode.launchProfile?.enableGuiMode || !!episode.launchProfile?.enableMoveIt;
            if (!isGuiOrTeleop) {
                const now = Date.now();
                const startedMs = new Date(episode.startedAt || Date.now()).getTime();
                const durationSec = Math.max(1, Number(episode.durationSec || 60));
                const expectedEndMs = startedMs + durationSec * 1000;
                const hardGraceMs = 25_000;
                const staleThresholdMs = 10_000;

                const outputHeartbeat = this.getLatestModifiedMs(episodeOutDir);
                const stdoutHeartbeat = this.getLatestModifiedMs(stdoutLog);
                const stderrHeartbeat = this.getLatestModifiedMs(stderrLog);
                const heartbeat = Math.max(outputHeartbeat, stdoutHeartbeat, stderrHeartbeat, startedMs);
                const staleMs = now - heartbeat;
                const exceededExpectedWindow = now > (expectedEndMs + hardGraceMs);

                if (exceededExpectedWindow && staleMs > staleThresholdMs) {
                    isRunning = false;
                }
            }
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
                "grasp_events.json",
                "camera_0.mp4",
                "camera_1_wrist.mp4",
                "camera_2_external.mp4",
            ];
            const dirsToSync = [
                "replicator_data",
                "replicator_wrist",
                "replicator_external",
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
            for (const dirName of dirsToSync) {
                const sourceDir = path.join(episodeOutDir, dirName);
                if (fs.existsSync(sourceDir) && fs.statSync(sourceDir).isDirectory()) {
                    this.copyDirRecursive(sourceDir, path.join(localOutDir, dirName));
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

    private copyDirRecursive(src: string, dest: string) {
        fs.mkdirSync(dest, { recursive: true });
        for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
            const srcPath = path.join(src, entry.name);
            const destPath = path.join(dest, entry.name);
            if (entry.isDirectory()) {
                this.copyDirRecursive(srcPath, destPath);
            } else {
                fs.copyFileSync(srcPath, destPath);
            }
        }
    }
}

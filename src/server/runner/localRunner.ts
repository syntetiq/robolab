import { Runner, DiagnosticReport, StartResult, StopResult, StatusSnapshot } from "./Runner";
import { acquireLock, releaseLock } from "../hostLock";
import fs from "fs";
import path from "path";

export class LocalRunner implements Runner {
    async testConnection(config: any): Promise<DiagnosticReport> {
        return {
            isaacHostReachable: true, // Always reachable locally
            sshReachable: null,
            resolvedIp: "localhost",
            latencyMs: 1,
            errors: [],
            recommendations: ["Local mode active. No network connection needed."]
        };
    }

    async startEpisode(episode: any, config: any): Promise<StartResult> {
        const locked = await acquireLock(config.isaacHost, episode.id);
        if (!locked) {
            return { success: false, error: `Host ${config.isaacHost} is currently locked by another episode.` };
        }

        // MVP Stub: Create output dir and write metadata.json locally
        const outDir = config.defaultOutputDir ? `${config.defaultOutputDir}/episodes/${episode.id}` : `./data/episodes/${episode.id}`;

        try {
            if (!fs.existsSync(outDir)) {
                fs.mkdirSync(outDir, { recursive: true });
            }

            const meta = {
                ...episode,
                startedAt: new Date(),
                frozenConfigSnapshot: config
            };

            fs.writeFileSync(path.join(outDir, "metadata.json"), JSON.stringify(meta, null, 2));

            // Simulate launching...
            console.log(`[LocalRunner] Executing: ${episode.launchProfile?.isaacLaunchTemplate || "default isaac run"}`);
            return { success: true };
        } catch (e: any) {
            await releaseLock(config.isaacHost, episode.id);
            return { success: false, error: e.message };
        }
    }

    async stopEpisode(episode: any, config: any): Promise<StopResult> {
        await releaseLock(config.isaacHost, episode.id);
        console.log(`[LocalRunner] Executing: ${episode.launchProfile?.stopTemplate || "pkill -f isaac-sim"}`);

        // Finalize metadata...
        const outDir = config.defaultOutputDir ? `${config.defaultOutputDir}/episodes/${episode.id}` : `./data/episodes/${episode.id}`;
        try {
            if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

            const metaPath = path.join(outDir, "metadata.json");
            if (fs.existsSync(metaPath)) {
                const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
                meta.stoppedAt = new Date();
                fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));
            }

            // Feature: Simulate recording video generation for UI testing
            const dummyVideoPath = path.join(outDir, "camera_0.mp4");
            if (!fs.existsSync(dummyVideoPath)) {
                // Just writing a small empty text file named mp4 to test the list payload.
                // A real mp4 would be written by Isaac Sim properly. We write dummy bytes so the file exists.
                fs.writeFileSync(dummyVideoPath, "MOCK_VIDEO_DATA");
            }

        } catch (e) { }

        return { success: true };
    }

    async getLiveStatus(episode: any, config: any): Promise<StatusSnapshot> {
        const uptimeSec = Math.floor((Date.now() - new Date(episode.startedAt || Date.now()).getTime()) / 1000);
        const durationLimit = episode.durationSec || 60;

        return {
            status: uptimeSec >= durationLimit ? "completed" : "running",
            uptimeSec,
            cpuUsage: Math.floor(Math.random() * 20 + 10),
            memoryUsage: Math.floor(Math.random() * 40 + 40)
        };
    }

    async getLiveLogs(episode: any, config: any, lines: number = 20): Promise<string[]> {
        // ... (existing mock lines logic) ...
        return ["Local simulation doesn't stream real logs."];
    }

    async syncData(episode: any, config: any): Promise<{ success: boolean; error?: string }> {
        // For local runner, data is already local.
        return { success: true };
    }
}

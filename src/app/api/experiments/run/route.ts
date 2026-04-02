import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import fs from "fs";
import path from "path";
import { prisma } from "@/lib/prisma";

const SCRIPT_PATH = path.join(process.cwd(), "scripts", "run_task_config.ps1");

export async function POST(req: NextRequest) {
    try {
        const body = await req.json();
        const configPath: string = body.configPath;

        if (!configPath) {
            return NextResponse.json({ error: "configPath is required" }, { status: 400 });
        }

        const absConfig = path.isAbsolute(configPath)
            ? configPath
            : path.join(process.cwd(), configPath);

        if (!fs.existsSync(absConfig)) {
            return NextResponse.json({ error: `Config not found: ${configPath}` }, { status: 404 });
        }
        if (!fs.existsSync(SCRIPT_PATH)) {
            return NextResponse.json({ error: "run_task_config.ps1 not found" }, { status: 500 });
        }

        const config = await prisma.config.findFirst();
        const outputBase = config?.defaultOutputDir || "C:\\RoboLab_Data";
        const episodesDir = path.join(outputBase, "episodes");

        let configJson: any = {};
        try {
            configJson = JSON.parse(fs.readFileSync(absConfig, "utf-8"));
        } catch { /* ignore */ }

        const episodeName = configJson.episode_name || path.basename(configPath, ".json");
        const durationSec = configJson.simulation_duration_s || 120;
        const timestamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 15).replace(/(\d{8})(\d{6})/, "$1_$2");
        const runDir = path.join(episodesDir, `${episodeName}_${timestamp}`);

        const args = [
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPT_PATH,
            "-Config", absConfig,
            "-Output", episodesDir,
            "-Duration", String(durationSec),
        ];

        const child = spawn("powershell.exe", args, {
            detached: true,
            stdio: "ignore",
            cwd: process.cwd(),
        });
        child.unref();

        return NextResponse.json({
            ok: true,
            episodeName,
            pid: child.pid,
            expectedDir: runDir,
            durationSec,
        });
    } catch (error: any) {
        return NextResponse.json({ error: error.message || "Failed to launch experiment" }, { status: 500 });
    }
}

import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const TASKS_DIR = path.join(process.cwd(), "config", "tasks");

export async function GET() {
    try {
        if (!fs.existsSync(TASKS_DIR)) {
            return NextResponse.json([]);
        }
        const files = fs.readdirSync(TASKS_DIR).filter((f) => f.endsWith(".json")).sort();
        const experiments = files.map((file) => {
            try {
                const raw = JSON.parse(fs.readFileSync(path.join(TASKS_DIR, file), "utf-8"));
                return {
                    file,
                    configPath: `config/tasks/${file}`,
                    name: raw.episode_name || file.replace(".json", ""),
                    description: raw.description || "",
                    durationSec: raw.simulation_duration_s || 120,
                    robotModel: raw.robot?.model || "heavy",
                    taskCount: Array.isArray(raw.tasks) ? raw.tasks.length : 0,
                };
            } catch {
                return {
                    file,
                    configPath: `config/tasks/${file}`,
                    name: file.replace(".json", ""),
                    description: "Error reading config",
                    durationSec: 120,
                    robotModel: "heavy",
                    taskCount: 0,
                };
            }
        });
        return NextResponse.json(experiments);
    } catch (error) {
        return NextResponse.json({ error: "Failed to list experiments" }, { status: 500 });
    }
}

export async function POST(req: NextRequest) {
    try {
        const body = await req.json();
        if (!body.episode_name || typeof body.episode_name !== "string") {
            return NextResponse.json({ error: "episode_name is required" }, { status: 400 });
        }
        const safeName = body.episode_name
            .toLowerCase()
            .replace(/[^a-z0-9_]/g, "_")
            .replace(/_+/g, "_")
            .slice(0, 80);
        const fileName = `${safeName}.json`;
        if (!fs.existsSync(TASKS_DIR)) {
            fs.mkdirSync(TASKS_DIR, { recursive: true });
        }
        const absPath = path.join(TASKS_DIR, fileName);
        fs.writeFileSync(absPath, JSON.stringify(body, null, 2), "utf-8");
        return NextResponse.json({ file: fileName, configPath: `config/tasks/${fileName}` }, { status: 201 });
    } catch (error) {
        console.error("POST /api/experiments error:", error);
        return NextResponse.json({ error: "Failed to save task config" }, { status: 500 });
    }
}

export async function DELETE(req: NextRequest) {
    try {
        const { file } = await req.json();
        if (!file || typeof file !== "string") {
            return NextResponse.json({ error: "file is required" }, { status: 400 });
        }
        if (file.includes("..") || file.includes("/") || file.includes("\\")) {
            return NextResponse.json({ error: "Invalid file name" }, { status: 400 });
        }
        const absPath = path.join(TASKS_DIR, file);
        if (!fs.existsSync(absPath)) {
            return NextResponse.json({ error: "Config not found" }, { status: 404 });
        }
        fs.unlinkSync(absPath);
        return NextResponse.json({ ok: true });
    } catch (error) {
        return NextResponse.json({ error: "Failed to delete config" }, { status: 500 });
    }
}

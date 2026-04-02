import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { prisma } from "@/lib/prisma";

export async function GET() {
    try {
        const config = await prisma.config.findFirst();
        const outputBase = config?.defaultOutputDir || "C:\\RoboLab_Data";
        const episodesDir = path.join(outputBase, "episodes");

        if (!fs.existsSync(episodesDir)) {
            return NextResponse.json([]);
        }

        const entries = fs.readdirSync(episodesDir, { withFileTypes: true })
            .filter((d) => d.isDirectory());

        const runs = entries.map((entry) => {
            const dirPath = path.join(episodesDir, entry.name);
            const match = entry.name.match(/^(.+?)_(\d{8}_\d{6})$/);
            const experimentName = match ? match[1] : entry.name;
            const timestampRaw = match ? match[2] : null;

            let timestamp: string | null = null;
            if (timestampRaw) {
                const y = timestampRaw.slice(0, 4);
                const mo = timestampRaw.slice(4, 6);
                const d = timestampRaw.slice(6, 8);
                const h = timestampRaw.slice(9, 11);
                const mi = timestampRaw.slice(11, 13);
                const s = timestampRaw.slice(13, 15);
                timestamp = `${y}-${mo}-${d}T${h}:${mi}:${s}`;
            }

            let hasVideo = false;
            let hasHeavy = false;
            try {
                const sub = fs.readdirSync(dirPath);
                hasHeavy = sub.includes("heavy");
                const checkDir = hasHeavy ? path.join(dirPath, "heavy") : dirPath;
                if (fs.existsSync(checkDir)) {
                    const files = fs.readdirSync(checkDir);
                    hasVideo = files.some((f) => f.endsWith(".mp4") || f.endsWith(".avi"));
                }
            } catch { /* ignore */ }

            let stat: fs.Stats | null = null;
            try { stat = fs.statSync(dirPath); } catch { /* ignore */ }

            return {
                dir: entry.name,
                fullPath: dirPath,
                experimentName,
                timestamp,
                createdAt: stat?.birthtime?.toISOString() || stat?.mtime?.toISOString() || null,
                hasVideo,
                hasHeavy,
            };
        });

        runs.sort((a, b) => (b.createdAt || "").localeCompare(a.createdAt || ""));

        return NextResponse.json(runs);
    } catch (error) {
        return NextResponse.json({ error: "Failed to list runs" }, { status: 500 });
    }
}

function rmRecursive(dir: string) {
    fs.rmSync(dir, { recursive: true, force: true });
}

export async function DELETE(req: NextRequest) {
    try {
        const { dir } = await req.json();
        if (!dir || typeof dir !== "string") {
            return NextResponse.json({ error: "dir is required" }, { status: 400 });
        }
        if (dir.includes("..")) {
            return NextResponse.json({ error: "Invalid directory name" }, { status: 400 });
        }

        const config = await prisma.config.findFirst();
        const outputBase = config?.defaultOutputDir || "C:\\RoboLab_Data";
        const episodesDir = path.join(outputBase, "episodes");
        const absPath = path.join(episodesDir, dir);

        if (!absPath.startsWith(episodesDir)) {
            return NextResponse.json({ error: "Path traversal denied" }, { status: 400 });
        }
        if (!fs.existsSync(absPath)) {
            return NextResponse.json({ error: "Run directory not found" }, { status: 404 });
        }

        rmRecursive(absPath);
        return NextResponse.json({ ok: true });
    } catch (error) {
        return NextResponse.json({ error: "Failed to delete run" }, { status: 500 });
    }
}

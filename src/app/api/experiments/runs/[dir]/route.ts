import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { prisma } from "@/lib/prisma";

function safeJoin(base: string, ...parts: string[]): string {
    const res = path.join(base, ...parts);
    const normalized = path.normalize(res);
    if (!normalized.startsWith(path.normalize(base))) return base;
    return normalized;
}

function listFiles(dir: string, prefix = ""): { name: string; relPath: string; isDir: boolean; size?: number }[] {
    if (!fs.existsSync(dir)) return [];
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    return entries.map((e) => {
        const relPath = prefix ? `${prefix}/${e.name}` : e.name;
        const fullPath = path.join(dir, e.name);
        const stat = fs.statSync(fullPath);
        return {
            name: e.name,
            relPath,
            isDir: e.isDirectory(),
            size: e.isFile() ? stat.size : undefined,
        };
    });
}

export async function GET(
    _req: NextRequest,
    { params }: { params: Promise<{ dir: string }> }
) {
    try {
        const { dir } = await params;
        if (!dir || dir.includes("..")) {
            return NextResponse.json({ error: "Invalid directory" }, { status: 400 });
        }

        const config = await prisma.config.findFirst();
        const outputBase = config?.defaultOutputDir || "C:\\RoboLab_Data";
        const episodesDir = path.join(outputBase, "episodes");
        const absPath = path.join(episodesDir, dir);

        if (!absPath.startsWith(path.resolve(episodesDir))) {
            return NextResponse.json({ error: "Path traversal denied" }, { status: 400 });
        }
        if (!fs.existsSync(absPath) || !fs.statSync(absPath).isDirectory()) {
            return NextResponse.json({ error: "Run not found" }, { status: 404 });
        }

        const rootFiles = listFiles(absPath);
        const hasHeavy = rootFiles.some((f) => f.name === "heavy" && f.isDir);
        const contentDir = hasHeavy ? path.join(absPath, "heavy") : absPath;
        const contentFiles = listFiles(contentDir, hasHeavy ? "heavy" : "");

        const allFiles = hasHeavy ? [...rootFiles.filter((f) => f.name !== "heavy"), ...contentFiles] : rootFiles;

        const videos = allFiles.filter(
            (f) => !f.isDir && (f.name.endsWith(".mp4") || f.name.endsWith(".avi") || f.name.endsWith(".webm"))
        );
        const jsonFiles = allFiles.filter((f) => !f.isDir && f.name.endsWith(".json"));
        const otherFiles = allFiles.filter(
            (f) =>
                !f.isDir &&
                !f.name.endsWith(".mp4") &&
                !f.name.endsWith(".avi") &&
                !f.name.endsWith(".webm") &&
                !f.name.endsWith(".json")
        );

        const match = dir.match(/^(.+?)_(\d{8}_\d{6})$/);
        const experimentName = match ? match[1] : dir;
        let timestamp: string | null = null;
        if (match) {
            const t = match[2];
            timestamp = `${t.slice(0, 4)}-${t.slice(4, 6)}-${t.slice(6, 8)}T${t.slice(9, 11)}:${t.slice(11, 13)}:${t.slice(13, 15)}`;
        }

        let stat: fs.Stats | null = null;
        try { stat = fs.statSync(absPath); } catch { /* ignore */ }

        return NextResponse.json({
            dir,
            experimentName,
            timestamp,
            createdAt: stat?.birthtime?.toISOString() || stat?.mtime?.toISOString() || null,
            hasHeavy,
            videos,
            jsonFiles,
            otherFiles,
            allFiles,
        });
    } catch (error) {
        return NextResponse.json({ error: "Failed to load run" }, { status: 500 });
    }
}

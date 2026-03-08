import fs from "fs";
import path from "path";
import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

function findLatestRgbFrame(rootDir: string): string | null {
    if (!fs.existsSync(rootDir) || !fs.statSync(rootDir).isDirectory()) return null;
    const stack: string[] = [rootDir];
    let latestPath: string | null = null;
    let latestMtime = -1;

    while (stack.length > 0) {
        const current = stack.pop() as string;
        const entries = fs.readdirSync(current, { withFileTypes: true });
        for (const entry of entries) {
            const fullPath = path.join(current, entry.name);
            if (entry.isDirectory()) {
                stack.push(fullPath);
                continue;
            }
            if (!/^rgb_.*\.png$/i.test(entry.name)) continue;
            const stat = fs.statSync(fullPath);
            if (stat.mtimeMs > latestMtime) {
                latestMtime = stat.mtimeMs;
                latestPath = fullPath;
            }
        }
    }
    return latestPath;
}

export async function GET(
    _request: Request,
    { params }: { params: Promise<{ id: string }> },
) {
    try {
        const { id } = await params;
        const episode = await prisma.episode.findUnique({ where: { id } });
        if (!episode) {
            return NextResponse.json({ error: "Episode not found" }, { status: 404 });
        }
        if (!episode.outputDir) {
            return NextResponse.json({ error: "Episode output directory is not set" }, { status: 404 });
        }

        const outputDir = path.resolve(process.cwd(), episode.outputDir);
        const replicatorDir = path.join(outputDir, "replicator_data");
        const latestFrame = findLatestRgbFrame(replicatorDir);
        if (!latestFrame || !fs.existsSync(latestFrame)) {
            return NextResponse.json({ error: "No live frame available yet" }, { status: 404 });
        }

        const frameBytes = fs.readFileSync(latestFrame);
        return new Response(frameBytes, {
            headers: {
                "Content-Type": "image/png",
                "Cache-Control": "no-store, no-cache, must-revalidate",
            },
        });
    } catch (error) {
        console.error("GET /api/episodes/[id]/stream/frame error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

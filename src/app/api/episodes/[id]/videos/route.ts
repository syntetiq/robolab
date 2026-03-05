import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import fs from "fs";
import path from "path";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const episode = await prisma.episode.findUnique({ where: { id } });

        if (!episode) return NextResponse.json({ error: "Episode not found" }, { status: 404 });
        if (!episode.outputDir) return NextResponse.json([]); // No outputs yet

        // For remote runs, files are synced to public/episodes/[id]
        // For local runs, they might be in outputDir, but sync moves them here too or we can just serve them from public.
        // Let's check public/episodes/[id] first, then fallback to outputDir if it's local.
        const publicDir = path.resolve(process.cwd(), `public/episodes/${id}`);
        const localDir = path.resolve(process.cwd(), episode.outputDir || "");

        let dirToRead = "";
        if (fs.existsSync(publicDir) && fs.readdirSync(publicDir).length > 0) {
            dirToRead = publicDir;
        } else if (episode.outputDir && fs.existsSync(localDir)) {
            dirToRead = localDir;
        } else {
            return NextResponse.json([]);
        }

        const files = fs.readdirSync(dirToRead);
        // Find video and data files
        const relevantFiles = files.filter(f => f.endsWith('.mp4') || f.endsWith('.webm') || f.endsWith('.json'));

        return NextResponse.json(relevantFiles.map(name => ({
            name,
            url: dirToRead === publicDir
                ? `/episodes/${id}/${encodeURIComponent(name)}`
                : `/api/episodes/${id}/videos/${encodeURIComponent(name)}`
        })));

    } catch (error) {
        console.error("GET /api/episodes/[id]/videos error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

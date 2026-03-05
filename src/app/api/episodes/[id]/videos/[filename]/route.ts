import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import fs from "fs";
import path from "path";

export async function GET(request: Request, { params }: { params: Promise<{ id: string, filename: string }> }) {
    try {
        const { id, filename } = await params;
        const episode = await prisma.episode.findUnique({ where: { id } });

        if (!episode || !episode.outputDir) return NextResponse.json({ error: "Not found" }, { status: 404 });

        const dir = path.resolve(process.cwd(), episode.outputDir);
        const filePath = path.join(dir, decodeURIComponent(filename));

        if (!fs.existsSync(filePath)) {
            return NextResponse.json({ error: "File not found" }, { status: 404 });
        }

        // In a real production app we'd use streams indicating range requests for scrubbing
        // For MVP, we stream the whole file or let nextjs handle static serving if placed there
        const stat = fs.statSync(filePath);
        const stream = fs.createReadStream(filePath);

        let contentType = 'application/octet-stream';
        if (filename.endsWith('.mp4')) contentType = 'video/mp4';
        if (filename.endsWith('.webm')) contentType = 'video/webm';
        if (filename.endsWith('.json')) contentType = 'application/json';

        return new Response(stream as any, {
            headers: {
                'Content-Type': contentType,
                'Content-Length': stat.size.toString(),
            }
        });

    } catch (error) {
        console.error("GET Video file error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { listEpisodeArtifacts } from "@/server/artifacts";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const episode = await prisma.episode.findUnique({ where: { id } });

        if (!episode) return NextResponse.json({ error: "Episode not found" }, { status: 404 });
        const artifacts = listEpisodeArtifacts(id, episode.outputDir);
        return NextResponse.json(artifacts);

    } catch (error) {
        console.error("GET /api/episodes/[id]/videos error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

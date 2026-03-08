import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { listEpisodeArtifacts } from "@/server/artifacts";

export async function GET(req: NextRequest) {
    try {
        const { searchParams } = new URL(req.url);
        const page = Math.max(1, Number(searchParams.get("page") || "1"));
        const pageSize = Math.min(100, Math.max(1, Number(searchParams.get("pageSize") || "20")));
        const kindFilter = (searchParams.get("kind") || "").trim();
        const query = (searchParams.get("q") || "").trim().toLowerCase();

        const episodes = await prisma.episode.findMany({
            orderBy: { createdAt: "desc" },
            select: {
                id: true,
                outputDir: true,
                createdAt: true,
                status: true,
                tasks: true,
                scene: { select: { name: true } },
            },
        });

        const all = episodes.flatMap((episode) => {
            const artifacts = listEpisodeArtifacts(episode.id, episode.outputDir);
            return artifacts.map((artifact) => ({
                ...artifact,
                episodeStatus: episode.status,
                episodeCreatedAt: episode.createdAt.toISOString(),
                sceneName: episode.scene?.name || "",
                tasks: episode.tasks,
            }));
        });

        const filtered = all.filter((item) => {
            if (kindFilter && item.kind !== kindFilter) {
                return false;
            }
            if (!query) return true;
            const haystack = `${item.name} ${item.sceneName} ${item.tasks}`.toLowerCase();
            return haystack.includes(query);
        });

        const offset = (page - 1) * pageSize;
        const items = filtered.slice(offset, offset + pageSize);
        return NextResponse.json({
            page,
            pageSize,
            total: filtered.length,
            items,
        });
    } catch (error: any) {
        return NextResponse.json({ error: error.message || "Server error" }, { status: 500 });
    }
}

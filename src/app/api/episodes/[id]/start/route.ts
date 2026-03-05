import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getRunner } from "@/server/runner";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const config = await prisma.config.findFirst();
        if (!config) return NextResponse.json({ error: "Config not found" }, { status: 404 });

        const episode = await prisma.episode.findUnique({
            where: { id },
            include: { launchProfile: true }
        });
        if (!episode) return NextResponse.json({ error: "Episode not found" }, { status: 404 });

        const runnerMode = episode.launchProfile?.runnerMode || config.runnerMode;
        const runner = getRunner(runnerMode);

        const result = await runner.startEpisode(episode, config);
        if (!result.success) {
            return NextResponse.json({ error: result.error }, { status: 400 });
        }

        const outputDir = config.defaultOutputDir ? `${config.defaultOutputDir}/episodes/${id}/` : `./data/episodes/${id}/`;

        const updated = await prisma.episode.update({
            where: { id },
            data: {
                status: "running",
                startedAt: new Date(),
                outputDir
            }
        });

        return NextResponse.json(updated);
    } catch (error) {
        console.error(error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

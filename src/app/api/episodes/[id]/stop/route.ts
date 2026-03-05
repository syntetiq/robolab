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

        const result = await runner.stopEpisode(episode, config);
        if (!result.success) {
            console.warn(`Stop episode returned error: ${result.error}`);
        }

        const updated = await prisma.episode.update({
            where: { id },
            data: {
                status: "stopped",
                stoppedAt: new Date()
            }
        });

        return NextResponse.json(updated);
    } catch (error) {
        console.error(error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

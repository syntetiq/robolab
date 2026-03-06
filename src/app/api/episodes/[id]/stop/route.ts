import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getRunner } from "@/server/runner";
import { formatValidationSummary, validateEpisodeDataset } from "@/server/datasetValidation";

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

        const outputDir = episode.outputDir || `${config.defaultOutputDir}\\episodes\\${id}`;
        const validation = validateEpisodeDataset(outputDir);
        const summary = formatValidationSummary(validation);
        const status = validation.valid ? "stopped" : "failed";
        const notes = summary
            ? `${episode.notes || ""}${episode.notes ? "\n" : ""}[dataset-validation] ${summary}`
            : episode.notes;

        const updated = await prisma.episode.update({
            where: { id },
            data: {
                status,
                stoppedAt: new Date(),
                notes
            }
        });

        return NextResponse.json({ ...updated, datasetValidation: validation });
    } catch (error) {
        console.error(error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

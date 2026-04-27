import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getRunner } from "@/server/runner";
import { releaseLock } from "@/server/hostLock";
import { formatValidationSummary, validateEpisodeDataset } from "@/server/datasetValidation";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        let episode = await prisma.episode.findUnique({
            where: { id },
            include: { scene: true, objectSet: true, launchProfile: true }
        });
        if (!episode) return NextResponse.json({ error: "Not Found" }, { status: 404 });

        if (episode.status === "running") {
            const config = await prisma.config.findFirst();
            if (config) {
                const runner = getRunner(config.runnerMode);
                const liveStatus = await runner.getLiveStatus(episode, config);
                if (liveStatus.status !== "running") {
                    const outputDir = episode.outputDir || `${config.defaultOutputDir}\\episodes\\${id}`;
                    const validation = validateEpisodeDataset(outputDir);
                    const validationSummary = formatValidationSummary(validation);
                    const isGuiOrTeleop = !!episode.launchProfile?.enableGuiMode || !!episode.launchProfile?.enableMoveIt;
                    const nextStatus = validation.valid ? liveStatus.status
                        : isGuiOrTeleop ? (liveStatus.status || "stopped")
                        : "failed";
                    const nextNotes = validationSummary
                        ? `${episode.notes || ""}${episode.notes ? "\n" : ""}[dataset-validation] ${validationSummary}`
                        : episode.notes;

                    episode = await prisma.episode.update({
                        where: { id },
                        data: {
                            status: nextStatus,
                            stoppedAt: new Date(),
                            notes: nextNotes,
                        },
                        include: { scene: true, objectSet: true, launchProfile: true },
                    });
                    await releaseLock(config.isaacHost, id);
                }
            }
        }
        return NextResponse.json(episode);
    } catch (error) {
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const episode = await prisma.episode.findUnique({ where: { id } });
        if (!episode) return NextResponse.json({ error: "Not Found" }, { status: 404 });
        if (episode.status === "running" || episode.status === "stopping") {
            return NextResponse.json({ error: "Cannot delete a running episode. Stop it first." }, { status: 409 });
        }
        await prisma.episode.delete({ where: { id } });
        return NextResponse.json({ ok: true });
    } catch (error) {
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getRunner } from "@/server/runner";
import { formatValidationSummary, validateEpisodeDataset } from "@/server/datasetValidation";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const episode = await prisma.episode.findUnique({
            where: { id },
            include: { launchProfile: true }
        });

        if (!episode) return NextResponse.json({ error: "Episode not found" }, { status: 404 });

        // Only makes sense to sync if it ran
        if (episode.status === "draft" || episode.status === "failed") {
            return NextResponse.json({ error: "Cannot sync episode in current state" }, { status: 400 });
        }

        const config = await prisma.config.findFirst();
        if (!config) return NextResponse.json({ error: "No config found" }, { status: 500 });

        // Fallback to episode.runnerMode or SSH_RUNNER
        const runnerMode = episode.launchProfile?.runnerMode || config.runnerMode || "SSH_RUNNER";
        const runner = getRunner(runnerMode);
        const result = await runner.syncData(episode, config);

        if (result.success) {
            const outputDir = episode.outputDir || `${config.defaultOutputDir}\\episodes\\${id}`;
            const validation = validateEpisodeDataset(outputDir);
            if (!validation.valid) {
                return NextResponse.json(
                    {
                        success: false,
                        message: "Sync complete, but dataset validation failed.",
                        validation,
                        details: formatValidationSummary(validation),
                    },
                    { status: 422 }
                );
            }
            return NextResponse.json({ success: true, message: "Sync complete.", validation });
        } else {
            const isMissing = result.error?.includes("No files found");
            return NextResponse.json(
                { error: result.error || "Failed to sync Data." },
                { status: isMissing ? 404 : 500 }
            );
        }
    } catch (error) {
        console.error("POST /api/episodes/[id]/sync error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

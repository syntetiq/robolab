import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { formatValidationSummary, validateEpisodeDataset } from "@/server/datasetValidation";

export async function GET(
    _req: NextRequest,
    { params }: { params: Promise<{ id: string }> },
) {
    try {
        const { id } = await params;
        const episode = await prisma.episode.findUnique({ where: { id } });
        if (!episode) {
            return NextResponse.json({ error: "Episode not found" }, { status: 404 });
        }
        const config = await prisma.config.findUnique({ where: { id: 1 } });
        if (!config) {
            return NextResponse.json({ error: "Global config not found" }, { status: 500 });
        }

        const outputDir = episode.outputDir || `${config.defaultOutputDir}\\episodes\\${id}`;
        const validation = validateEpisodeDataset(outputDir);
        const summary = formatValidationSummary(validation);

        return NextResponse.json({
            ...validation,
            summary,
            outputDir,
            requiredOutputs: [
                "joint trajectories + velocities",
                "point cloud",
                "world poses",
                "video",
            ],
        });
    } catch (error: any) {
        return NextResponse.json({ error: error.message || "Server error" }, { status: 500 });
    }
}

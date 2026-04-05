import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
    try {
        const batches = await prisma.episodeBatch.findMany({
            include: {
                episodes: {
                    select: { id: true, status: true, batchIndex: true },
                    orderBy: { batchIndex: "asc" },
                },
            },
            orderBy: { createdAt: "desc" },
        });
        return NextResponse.json(batches);
    } catch (error) {
        console.error("GET /api/batches error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

export async function POST(request: NextRequest) {
    try {
        const body = await request.json();

        if (!body.name?.trim()) {
            return NextResponse.json({ error: "name is required" }, { status: 400 });
        }
        if (!body.sceneId?.trim()) {
            return NextResponse.json({ error: "sceneId is required" }, { status: 400 });
        }

        const totalEpisodes = Math.max(1, Math.min(100, parseInt(body.totalEpisodes, 10) || 1));
        const baseSeed = parseInt(body.baseSeed, 10) || 42;
        const durationSec = parseInt(body.durationSec, 10) || 60;

        const batch = await prisma.episodeBatch.create({
            data: {
                name: body.name.trim(),
                description: body.description || "",
                sceneId: body.sceneId.trim(),
                launchProfileId: body.launchProfileId || null,
                objectSetId: body.objectSetId || null,
                taskConfigPath: body.taskConfigPath || "",
                durationSec,
                totalEpisodes,
                baseSeed,
                variationConfig: body.variationConfig || "{}",
            },
        });

        // Pre-create all episodes for the batch
        const episodes = [];
        for (let i = 0; i < totalEpisodes; i++) {
            const episode = await prisma.episode.create({
                data: {
                    sceneId: body.sceneId.trim(),
                    objectSetId: body.objectSetId || null,
                    launchProfileId: body.launchProfileId || null,
                    batchId: batch.id,
                    batchIndex: i,
                    seed: baseSeed + i,
                    durationSec,
                    tasks: body.tasks || "[]",
                    sensors: body.sensors || "[]",
                    randomizationConfig: body.randomizationConfig || "{}",
                    status: "queued",
                    notes: `Batch "${batch.name}" episode ${i + 1}/${totalEpisodes}`,
                },
            });
            episodes.push(episode);
        }

        return NextResponse.json({ ...batch, episodes }, { status: 201 });
    } catch (error) {
        console.error("POST /api/batches error:", error);
        return NextResponse.json({ error: "Invalid data" }, { status: 400 });
    }
}

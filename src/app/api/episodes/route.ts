import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
    try {
        const episodes = await prisma.episode.findMany({
            include: { scene: true, objectSet: true, launchProfile: true },
            orderBy: { createdAt: "desc" },
        });
        return NextResponse.json(episodes);
    } catch (error) {
        console.error("GET /api/episodes error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

export async function POST(request: Request) {
    try {
        const body = await request.json();

        // Minimal validation
        if (!body.sceneId) return NextResponse.json({ error: "sceneId is required" }, { status: 400 });

        const episode = await prisma.episode.create({
            data: {
                sceneId: body.sceneId,
                objectSetId: body.objectSetId || null,
                launchProfileId: body.launchProfileId || null,
                tasks: body.tasks || "[]",
                sensors: body.sensors || "[]",
                randomizationConfig: body.randomizationConfig || "{}",
                seed: body.seed ? parseInt(body.seed, 10) : 42,
                durationSec: body.durationSec ? parseInt(body.durationSec, 10) : 60,
                notes: body.notes || "",
                status: "created"
            }
        });
        return NextResponse.json(episode, { status: 201 });
    } catch (error) {
        console.error("POST /api/episodes error:", error);
        return NextResponse.json({ error: "Invalid data" }, { status: 400 });
    }
}

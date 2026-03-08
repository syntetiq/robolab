import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { refreshOrchestrationState, startExecSmokeOrchestration } from "@/server/orchestration/execSmokeOrchestrator";
// API wrapper for deterministic local orchestration state.

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

        const outputRoot = config.defaultOutputDir || "C:\\RoboLab_Data";
        const state = refreshOrchestrationState(outputRoot, id);

        // Sync episode DB status so UI and batch scripts polling /api/episodes/{id} see correct status.
        const dbStatusMap: Record<string, string> = {
            running: "running",
            succeeded: "completed",
            failed: "failed",
        };
        const newDbStatus = dbStatusMap[state.status];
        if (newDbStatus && episode.status !== newDbStatus) {
            const updateData: Record<string, unknown> = { status: newDbStatus };
            if (newDbStatus === "running" && !episode.startedAt) {
                updateData.startedAt = state.startedAt ? new Date(state.startedAt) : new Date();
            }
            if (newDbStatus !== "running" && !episode.stoppedAt) {
                updateData.stoppedAt = state.finishedAt ? new Date(state.finishedAt) : new Date();
            }
            await prisma.episode.update({ where: { id }, data: updateData });
        }

        return NextResponse.json(state);
    } catch (error: any) {
        return NextResponse.json({ error: error.message || "Server error" }, { status: 500 });
    }
}

export async function POST(
    req: NextRequest,
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

        const body = await req.json().catch(() => ({} as any));
        const fullTaskDefault = [
            "approach_workzone",
            "plan_pick_sink",
            "plan_place",
            "plan_pick_fridge",
            "plan_place",
            "plan_pick_dishwasher",
            "plan_place",
            "open_close_fridge",
            "open_close_dishwasher",
            "go_home",
        ];
        const requestedSequence =
            Array.isArray(body.intentSequence) && body.intentSequence.length > 0
                ? body.intentSequence.map((x: any) => String(x || "").trim()).filter(Boolean)
                : (body.mode === "full_tasks" ? fullTaskDefault : []);
        const outputRoot = config.defaultOutputDir || "C:\\RoboLab_Data";
        const state = startExecSmokeOrchestration({
            outputRoot,
            episodeId: id,
            durationSec: Number(body.durationSec) || episode.durationSec || 30,
            requireRealTiago: body.requireRealTiago !== false,
            force: body.force === true,
            intent: typeof body.intent === "string" ? body.intent : "plan_pick_sink",
            intentSequence: requestedSequence,
            intentDelaySec: Number.isFinite(Number(body.intentDelaySec)) ? Number(body.intentDelaySec) : 0,
            intentResultTimeoutSec: Number.isFinite(Number(body.intentResultTimeoutSec)) ? Number(body.intentResultTimeoutSec) : 150,
            maxRetriesPerIntent: Number.isFinite(Number(body.maxRetriesPerIntent)) ? Number(body.maxRetriesPerIntent) : 4,
            preGoHomeBetweenStages: body.preGoHomeBetweenStages !== false,
            retryOnCodeMinus4: body.retryOnCodeMinus4 !== false,
            warmupGoHome: body.warmupGoHome !== false,
        });

        // Sync episode DB status with orchestration state.
        if (state.status === "running") {
            await prisma.episode.update({
                where: { id },
                data: { status: "running", startedAt: state.startedAt ? new Date(state.startedAt) : new Date() },
            });
        }

        return NextResponse.json(state);
    } catch (error: any) {
        return NextResponse.json({ error: error.message || "Server error" }, { status: 500 });
    }
}

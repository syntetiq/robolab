import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

const DEFAULT_SAFE_PROFILE_NAME = "Default Safe Live Teleop";

function normalizeOptionalId(value: unknown): string | null {
    if (typeof value !== "string") return null;
    const trimmed = value.trim();
    if (!trimmed || trimmed.toLowerCase() === "none" || trimmed.toLowerCase() === "null") return null;
    return trimmed;
}

async function resolveDefaultLaunchProfileId(): Promise<string> {
    const existing =
        await prisma.launchProfile.findFirst({
            where: {
                enabled: true,
                name: DEFAULT_SAFE_PROFILE_NAME,
            },
            select: { id: true },
        });

    if (existing?.id) return existing.id;

    const localWebRtc = await prisma.launchProfile.findFirst({
        where: {
            enabled: true,
            runnerMode: "LOCAL_RUNNER",
            scriptName: "data_collector_tiago.py",
            enableWebRTC: true,
        },
        select: { id: true },
    });

    if (localWebRtc?.id) return localWebRtc.id;

    const created = await prisma.launchProfile.create({
        data: {
            name: DEFAULT_SAFE_PROFILE_NAME,
            runnerMode: "LOCAL_RUNNER",
            scriptName: "data_collector_tiago.py",
            environmentUsd: "C:\\RoboLab_Data\\scenes\\Small_House_Interactive.usd",
            enableWebRTC: true,
            enableVrTeleop: false,
            enableMoveIt: false,
            robotPovCameraPrim: "/World/Tiago",
            ros2SetupCommand: "",
            isaacLaunchTemplate: "",
            rosbagLaunchTemplate: "",
            teleopLaunchTemplate: "",
            stopTemplate: "",
            environmentOverrides: "{}",
            enabled: true,
        },
        select: { id: true },
    });
    return created.id;
}

export async function GET(request: NextRequest) {
    try {
        const { searchParams } = new URL(request.url);
        const status = (searchParams.get("status") || "").trim();
        const sceneId = (searchParams.get("sceneId") || "").trim();
        const task = (searchParams.get("task") || "").trim();
        const dateFrom = (searchParams.get("dateFrom") || "").trim();
        const dateTo = (searchParams.get("dateTo") || "").trim();
        const query = (searchParams.get("q") || "").trim();

        const where: any = {};
        if (status) where.status = status;
        if (sceneId) where.sceneId = sceneId;
        if (dateFrom || dateTo) {
            where.createdAt = {};
            if (dateFrom) where.createdAt.gte = new Date(dateFrom);
            if (dateTo) where.createdAt.lte = new Date(dateTo);
        }

        const episodes = await prisma.episode.findMany({
            where,
            include: { scene: true, objectSet: true, launchProfile: true },
            orderBy: { createdAt: "desc" },
        });

        const filtered = episodes.filter((episode) => {
            if (task) {
                if (!String(episode.tasks || "").includes(task)) return false;
            }
            if (query) {
                const haystack = `${episode.id} ${episode.notes || ""} ${episode.scene?.name || ""} ${episode.tasks || ""}`.toLowerCase();
                if (!haystack.includes(query.toLowerCase())) return false;
            }
            return true;
        });

        return NextResponse.json(filtered);
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
        const sceneId = normalizeOptionalId(body.sceneId);
        if (!sceneId) return NextResponse.json({ error: "sceneId is required" }, { status: 400 });

        const objectSetId = normalizeOptionalId(body.objectSetId);
        const launchProfileId =
            normalizeOptionalId(body.launchProfileId) ||
            await resolveDefaultLaunchProfileId();

        // Accept either JSON-string (canonical) or array/object (auto-stringify for convenience)
        const toJsonString = (v: unknown, fallback: string): string => {
            if (v == null) return fallback;
            if (typeof v === "string") return v;
            try { return JSON.stringify(v); } catch { return fallback; }
        };

        const episode = await prisma.episode.create({
            data: {
                sceneId,
                objectSetId,
                launchProfileId,
                tasks: toJsonString(body.tasks, "[]"),
                sensors: toJsonString(body.sensors, "[]"),
                randomizationConfig: toJsonString(body.randomizationConfig, "{}"),
                seed: body.seed ? parseInt(body.seed, 10) : 42,
                durationSec: body.durationSec ? parseInt(body.durationSec, 10) : 60,
                notes: body.notes || "",
                status: "created"
            }
        });
        return NextResponse.json(episode, { status: 201 });
    } catch (error) {
        console.error("POST /api/episodes error:", error);
        const message = error instanceof Error ? error.message : "Invalid data";
        return NextResponse.json({ error: "Invalid data", details: message }, { status: 400 });
    }
}

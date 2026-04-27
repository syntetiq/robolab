import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import fs from "fs";
import path from "path";

function hasExperimentalTag(tagsRaw: string | null | undefined): boolean {
    if (!tagsRaw) return false;
    try {
        const tags = JSON.parse(tagsRaw);
        return Array.isArray(tags) && tags.some((t) => String(t).toLowerCase() === "experimental");
    } catch {
        return false;
    }
}

function parseTags(tagsRaw: string | null | undefined): string[] {
    if (!tagsRaw) return [];
    try {
        const tags = JSON.parse(tagsRaw);
        return Array.isArray(tags) ? tags.map((t) => String(t).toLowerCase()) : [];
    } catch {
        return [];
    }
}

function wildcardMatch(value: string, pattern: string): boolean {
    const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".");
    return new RegExp(`^${escaped}$`, "i").test(value);
}

export async function GET(request: Request) {
    try {
        const url = new URL(request.url);
        const includeExperimentalByQuery = url.searchParams.get("includeExperimental") === "1";
        const includeExperimentalByEnv = process.env.ROBOLAB_ENABLE_EXPERIMENTAL_SCENES === "1";
        let includeExperimentalByConfig = false;
        let requireFitValidatedForExperimental = true;
        let allowedExperimentalScenePatterns: string[] = [];
        try {
            const rolloutPath = path.resolve(process.cwd(), "config", "scene_rollout.json");
            if (fs.existsSync(rolloutPath)) {
                const rollout = JSON.parse(fs.readFileSync(rolloutPath, "utf8"));
                includeExperimentalByConfig = rollout?.enableExperimentalScenes === true;
                requireFitValidatedForExperimental = rollout?.requireFitValidatedForExperimental !== false;
                if (Array.isArray(rollout?.allowedExperimentalScenePatterns)) {
                    allowedExperimentalScenePatterns = rollout.allowedExperimentalScenePatterns.map((v: any) => String(v));
                }
            }
        } catch {
            includeExperimentalByConfig = false;
        }
        const includeExperimental =
            includeExperimentalByQuery || includeExperimentalByEnv || includeExperimentalByConfig;

        const scenes = await prisma.scene.findMany({
            where: includeExperimental ? {} : { enabled: true },
            orderBy: { createdAt: "desc" },
        });
        const filtered = includeExperimental
            ? scenes.filter((scene) => {
                const tags = parseTags(scene.tags);
                const isExperimental = tags.includes("experimental");
                if (!scene.enabled) return false;
                if (!isExperimental) return true;
                if (requireFitValidatedForExperimental && !tags.includes("fit-validated")) return false;
                if (allowedExperimentalScenePatterns.length > 0) {
                    const match = allowedExperimentalScenePatterns.some((pattern) =>
                        wildcardMatch(scene.name || "", pattern) || wildcardMatch(scene.stageUsdPath || "", pattern),
                    );
                    if (!match) return false;
                }
                return true;
            })
            : scenes.filter((scene) => scene.enabled && !hasExperimentalTag(scene.tags));
        return NextResponse.json(filtered);
    } catch (error) {
        console.error("GET /api/scenes error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

export async function POST(request: Request) {
    try {
        const body = await request.json();
        const scene = await prisma.scene.create({ data: body });
        return NextResponse.json(scene, { status: 201 });
    } catch (error) {
        console.error("POST /api/scenes error:", error);
        return NextResponse.json({ error: "Invalid data" }, { status: 400 });
    }
}

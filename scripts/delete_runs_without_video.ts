/**
 * Delete all experiment runs that have no video (mp4/avi) in their output.
 * Run: npx tsx scripts/delete_runs_without_video.ts
 */

import fs from "fs";
import path from "path";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

async function main() {
    const config = await prisma.config.findFirst();
    const outputBase = config?.defaultOutputDir || "C:\\RoboLab_Data";
    const episodesDir = path.join(outputBase, "episodes");

    if (!fs.existsSync(episodesDir)) {
        console.log("No episodes directory found:", episodesDir);
        return;
    }

    const entries = fs.readdirSync(episodesDir, { withFileTypes: true }).filter((d) => d.isDirectory());
    const toDelete: string[] = [];

    for (const entry of entries) {
        const dirPath = path.join(episodesDir, entry.name);
        let hasVideo = false;
        try {
            const sub = fs.readdirSync(dirPath);
            const hasHeavy = sub.includes("heavy");
            const checkDir = hasHeavy ? path.join(dirPath, "heavy") : dirPath;
            if (fs.existsSync(checkDir)) {
                const files = fs.readdirSync(checkDir);
                hasVideo = files.some((f) => f.endsWith(".mp4") || f.endsWith(".avi"));
            }
        } catch { /* ignore */ }

        if (!hasVideo) {
            toDelete.push(dirPath);
        }
    }

    if (toDelete.length === 0) {
        console.log("No runs without video found.");
        return;
    }

    console.log(`Deleting ${toDelete.length} run(s) without video:`);
    for (const p of toDelete) {
        console.log("  -", path.basename(p));
        fs.rmSync(p, { recursive: true, force: true });
    }
    console.log("Done.");
}

main()
    .catch((e) => {
        console.error(e);
        process.exit(1);
    })
    .finally(() => prisma.$disconnect());

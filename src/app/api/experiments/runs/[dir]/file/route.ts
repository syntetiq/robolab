import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { prisma } from "@/lib/prisma";

const VIDEO_EXT = [".mp4", ".avi", ".webm"];
const JSON_EXT = ".json";

export async function GET(
    req: NextRequest,
    { params }: { params: Promise<{ dir: string }> }
) {
    try {
        const { dir } = await params;
        const filePath = req.nextUrl.searchParams.get("path");

        if (!dir || dir.includes("..")) {
            return NextResponse.json({ error: "Invalid directory" }, { status: 400 });
        }
        if (!filePath || filePath.includes("..") || path.isAbsolute(filePath)) {
            return NextResponse.json({ error: "Invalid file path" }, { status: 400 });
        }

        const config = await prisma.config.findFirst();
        const outputBase = config?.defaultOutputDir || "C:\\RoboLab_Data";
        const episodesDir = path.join(outputBase, "episodes");
        const absDir = path.join(episodesDir, dir);
        const absPath = path.join(absDir, filePath);
        const realPath = path.resolve(absPath);
        const realDir = path.resolve(absDir);
        if (!realPath.startsWith(realDir + path.sep) && realPath !== realDir) {
            return NextResponse.json({ error: "Path traversal denied" }, { status: 400 });
        }
        if (!fs.existsSync(absPath) || !fs.statSync(absPath).isFile()) {
            return NextResponse.json({ error: "File not found" }, { status: 404 });
        }

        const ext = path.extname(absPath).toLowerCase();
        const buf = fs.readFileSync(absPath);

        if (ext === JSON_EXT) {
            return new NextResponse(buf, {
                headers: { "Content-Type": "application/json" },
            });
        }
        if (VIDEO_EXT.includes(ext)) {
            return new NextResponse(buf, {
                headers: {
                    "Content-Type": ext === ".mp4" ? "video/mp4" : ext === ".webm" ? "video/webm" : "video/x-msvideo",
                    "Content-Length": String(buf.length),
                    "Accept-Ranges": "bytes",
                },
            });
        }

        return new NextResponse(buf, {
            headers: { "Content-Type": "application/octet-stream" },
        });
    } catch (error) {
        return NextResponse.json({ error: "Failed to serve file" }, { status: 500 });
    }
}

import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const episode = await prisma.episode.findUnique({
            where: { id },
            include: { scene: true, objectSet: true, launchProfile: true }
        });
        if (!episode) return NextResponse.json({ error: "Not Found" }, { status: 404 });
        return NextResponse.json(episode);
    } catch (error) {
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

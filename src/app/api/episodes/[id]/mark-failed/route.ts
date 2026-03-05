import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;

        const episode = await prisma.episode.update({
            where: { id },
            data: {
                status: "failed",
                stoppedAt: new Date()
            }
        });
        return NextResponse.json(episode);
    } catch (error) {
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

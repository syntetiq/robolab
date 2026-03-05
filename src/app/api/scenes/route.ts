import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
    try {
        const scenes = await prisma.scene.findMany({
            orderBy: { createdAt: "desc" },
        });
        return NextResponse.json(scenes);
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

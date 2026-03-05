import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
    try {
        const objectSets = await prisma.objectSet.findMany({
            orderBy: { createdAt: "desc" },
        });
        return NextResponse.json(objectSets);
    } catch (error) {
        console.error("GET /api/object-sets error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

export async function POST(request: Request) {
    try {
        const body = await request.json();
        const objectSet = await prisma.objectSet.create({ data: body });
        return NextResponse.json(objectSet, { status: 201 });
    } catch (error) {
        console.error("POST /api/object-sets error:", error);
        return NextResponse.json({ error: "Invalid data" }, { status: 400 });
    }
}

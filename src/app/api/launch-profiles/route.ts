import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
    try {
        const profiles = await prisma.launchProfile.findMany();
        return NextResponse.json(profiles);
    } catch (error) {
        console.error("GET /api/launch-profiles error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

export async function POST(request: Request) {
    try {
        const body = await request.json();
        const profile = await prisma.launchProfile.create({ data: body });
        return NextResponse.json(profile, { status: 201 });
    } catch (error) {
        console.error("POST /api/launch-profiles error:", error);
        return NextResponse.json({ error: "Invalid data" }, { status: 400 });
    }
}

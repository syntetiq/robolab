import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { configSchema } from "@/lib/schemas";

export async function GET() {
    try {
        const config = await prisma.config.findFirst();
        if (!config) {
            return NextResponse.json({ error: "Config not found" }, { status: 404 });
        }
        return NextResponse.json(config);
    } catch (error) {
        console.error("GET /api/config error:", error);
        return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
    }
}

export async function PUT(request: Request) {
    try {
        const body = await request.json();
        const validatedData = configSchema.parse(body);

        const updatedConfig = await prisma.config.update({
            where: { id: 1 },
            data: validatedData,
        });

    } catch (error) {
        console.error("PUT /api/config error:", error);
        return NextResponse.json({ error: "Invalid data or Server Error", details: (error as any).message || error }, { status: 400 });
    }
}

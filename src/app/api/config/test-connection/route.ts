import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getRunner } from "@/server/runner";

export async function POST() {
    try {
        const config = await prisma.config.findFirst();
        if (!config) return NextResponse.json({ error: "Config not found" }, { status: 404 });

        const runner = getRunner(config.runnerMode);
        const report = await runner.testConnection(config);

        return NextResponse.json(report);
    } catch (error) {
        console.error("POST /api/config/test-connection error:", error);
        return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
    }
}

import { NextResponse } from "next/server";
import { startBatch } from "@/server/batchExecutor";

export async function POST(
    _request: Request,
    { params }: { params: Promise<{ id: string }> },
) {
    try {
        const { id } = await params;
        const result = await startBatch(id);
        if (!result.success) {
            return NextResponse.json({ error: result.error }, { status: 400 });
        }
        return NextResponse.json({ success: true });
    } catch (error) {
        console.error("POST /api/batches/[id]/start error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(
    _request: Request,
    { params }: { params: Promise<{ id: string }> },
) {
    try {
        const { id } = await params;
        const batch = await prisma.episodeBatch.findUnique({
            where: { id },
            include: {
                episodes: {
                    select: {
                        id: true,
                        status: true,
                        batchIndex: true,
                        startedAt: true,
                        stoppedAt: true,
                        seed: true,
                        notes: true,
                    },
                    orderBy: { batchIndex: "asc" },
                },
            },
        });
        if (!batch) {
            return NextResponse.json({ error: "Batch not found" }, { status: 404 });
        }
        return NextResponse.json(batch);
    } catch (error) {
        console.error("GET /api/batches/[id] error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

export async function DELETE(
    _request: Request,
    { params }: { params: Promise<{ id: string }> },
) {
    try {
        const { id } = await params;
        const batch = await prisma.episodeBatch.findUnique({ where: { id } });
        if (!batch) {
            return NextResponse.json({ error: "Batch not found" }, { status: 404 });
        }
        if (batch.status === "running") {
            return NextResponse.json(
                { error: "Cannot delete a running batch. Pause it first." },
                { status: 400 },
            );
        }

        // Delete child episodes that haven't started
        await prisma.episode.deleteMany({
            where: { batchId: id, status: { in: ["created", "queued"] } },
        });

        // Unlink remaining episodes (keep completed/failed ones)
        await prisma.episode.updateMany({
            where: { batchId: id },
            data: { batchId: null, batchIndex: null },
        });

        await prisma.episodeBatch.delete({ where: { id } });
        return NextResponse.json({ success: true });
    } catch (error) {
        console.error("DELETE /api/batches/[id] error:", error);
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

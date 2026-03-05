import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const scene = await prisma.scene.findUnique({ where: { id } });
        if (!scene) return NextResponse.json({ error: "Not Found" }, { status: 404 });
        return NextResponse.json(scene);
    } catch (error) {
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const body = await request.json();
        const updated = await prisma.scene.update({
            where: { id },
            data: body,
        });
        return NextResponse.json(updated);
    } catch (error) {
        return NextResponse.json({ error: "Invalid data" }, { status: 400 });
    }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        await prisma.scene.delete({ where: { id } });
        return new NextResponse(null, { status: 204 });
    } catch (error) {
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

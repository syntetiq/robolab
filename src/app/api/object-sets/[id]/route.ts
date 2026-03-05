import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const objectSet = await prisma.objectSet.findUnique({ where: { id } });
        if (!objectSet) return NextResponse.json({ error: "Not Found" }, { status: 404 });
        return NextResponse.json(objectSet);
    } catch (error) {
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const body = await request.json();
        const updated = await prisma.objectSet.update({
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
        await prisma.objectSet.delete({ where: { id } });
        return new NextResponse(null, { status: 204 });
    } catch (error) {
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

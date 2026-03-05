import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const profile = await prisma.launchProfile.findUnique({ where: { id } });
        if (!profile) return NextResponse.json({ error: "Not Found" }, { status: 404 });
        return NextResponse.json(profile);
    } catch (error) {
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
    try {
        const { id } = await params;
        const body = await request.json();
        const updated = await prisma.launchProfile.update({
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
        await prisma.launchProfile.delete({ where: { id } });
        return new NextResponse(null, { status: 204 });
    } catch (error) {
        return NextResponse.json({ error: "Server Error" }, { status: 500 });
    }
}

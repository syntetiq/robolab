import { NextRequest, NextResponse } from "next/server";

export async function POST(
    req: NextRequest,
    { params }: { params: Promise<{ id: string }> },
) {
    const { id } = await params;
    try {
        const body = await req.json();
        const frames = Array.isArray(body.frames) ? body.frames : [];
        if (frames.length === 0) {
            return NextResponse.json({ error: "frames array is required" }, { status: 400 });
        }

        const responses: any[] = [];
        for (const frame of frames) {
            const res = await fetch(`${new URL(req.url).origin}/api/episodes/${id}/teleop`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    source: "mock_vr_replay",
                    replayFrame: frame,
                    deadmanActive: true,
                }),
            });
            const payload = await res.json().catch(() => ({}));
            responses.push({
                ok: res.ok,
                status: res.status,
                payload,
            });
            if (!res.ok) {
                break;
            }
        }

        return NextResponse.json({
            sent: responses.length,
            responses,
        });
    } catch (error: any) {
        return NextResponse.json({ error: error.message || "Server error" }, { status: 500 });
    }
}

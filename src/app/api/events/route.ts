import { NextRequest } from "next/server";
import { prisma } from "@/lib/prisma";
import { getRunner } from "@/server/runner";
import { releaseLock } from "@/server/hostLock";
import { formatValidationSummary, validateEpisodeDataset } from "@/server/datasetValidation";

export async function GET(req: NextRequest) {
    const { searchParams } = new URL(req.url);
    const episodeId = searchParams.get("episodeId");

    const responseStream = new TransformStream();
    const writer = responseStream.writable.getWriter();
    const encoder = new TextEncoder();

    let isClosed = false;

    const sendEvent = async (event: string, data: any) => {
        if (isClosed) return;
        try {
            await writer.write(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
        } catch {
            isClosed = true;
        }
    };

    // Keep track of the last seen log to avoid duplicate streaming
    let lastLogHash = "";

    const intervalId = setInterval(async () => {
        if (isClosed) return clearInterval(intervalId);

        if (episodeId) {
            try {
                const ep = await prisma.episode.findUnique({ where: { id: episodeId } });
                const config = await prisma.config.findFirst();

                if (ep && config) {
                    const runner = getRunner(config.runnerMode);

                    // Always try to fetch actual remote status
                    const liveStatus = await runner.getLiveStatus(ep, config);

                    // If DB is running but remote process stopped, transition state
                    if (ep.status === "running" && liveStatus.status !== "running") {
                        const outputDir = ep.outputDir || `${config.defaultOutputDir}\\episodes\\${episodeId}`;
                        const validation = validateEpisodeDataset(outputDir);
                        const validationSummary = formatValidationSummary(validation);
                        const nextStatus = validation.valid ? liveStatus.status : "failed";
                        const nextNotes = validationSummary
                            ? `${ep.notes || ""}${ep.notes ? "\n" : ""}[dataset-validation] ${validationSummary}`
                            : ep.notes;

                        await prisma.episode.update({
                            where: { id: episodeId },
                            data: {
                                status: nextStatus,
                                stoppedAt: new Date(),
                                notes: nextNotes,
                            }
                        });

                        // Release lock so the host can be used by the next episode
                        await releaseLock(config.isaacHost, episodeId);

                        await sendEvent("episode.status", { status: nextStatus });
                    } else {
                        await sendEvent("episode.status", { status: ep.status });
                    }

                    // System Health
                    await sendEvent("system.health", {
                        cpu: liveStatus.cpuUsage,
                        memory: liveStatus.memoryUsage
                    });

                    if (ep.status === "running") {
                        // Stream actual remote logs
                        const logs = await runner.getLiveLogs(ep, config, 1);
                        if (logs.length > 0) {
                            const newLine = logs[logs.length - 1];
                            if (newLine !== lastLogHash) {
                                await sendEvent("episode.log", { message: newLine });
                                lastLogHash = newLine;
                            }
                        }
                    }
                }
            } catch (e) {
                // Ignore errors to keep stream alive
                console.error("SSE Poll error:", e);
            }
        } else {
            // Default random health if no episode
            await sendEvent("system.health", {
                cpu: Math.floor(Math.random() * 20 + 5),
                memory: Math.floor(Math.random() * 10 + 40)
            });
        }
    }, 3000);

    req.signal.addEventListener("abort", () => {
        isClosed = true;
        clearInterval(intervalId);
        writer.close().catch(() => { });
    });

    return new Response(responseStream.readable, {
        headers: {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    });
}

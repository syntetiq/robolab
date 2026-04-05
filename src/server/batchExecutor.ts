import { prisma } from "@/lib/prisma";
import { getRunner } from "@/server/runner";

// In-memory tracking of active batch executions
const activeBatches = new Map<string, { polling: NodeJS.Timeout }>();

/**
 * Start executing a batch — launches the first queued episode and
 * sets up polling to auto-advance through the remaining episodes.
 */
export async function startBatch(batchId: string): Promise<{ success: boolean; error?: string }> {
    if (activeBatches.has(batchId)) {
        return { success: false, error: "Batch is already running." };
    }

    const batch = await prisma.episodeBatch.findUnique({
        where: { id: batchId },
        include: {
            episodes: {
                orderBy: { batchIndex: "asc" },
                include: { launchProfile: true, scene: true },
            },
        },
    });

    if (!batch) return { success: false, error: "Batch not found." };
    if (batch.episodes.length === 0) return { success: false, error: "Batch has no episodes." };

    await prisma.episodeBatch.update({
        where: { id: batchId },
        data: { status: "running" },
    });

    // Launch first queued episode
    const startResult = await launchNextEpisode(batchId);
    if (!startResult.success) {
        await prisma.episodeBatch.update({
            where: { id: batchId },
            data: { status: "failed" },
        });
        return startResult;
    }

    // Poll every 10 seconds to check if current episode finished
    const polling = setInterval(() => advanceBatch(batchId), 10_000);
    activeBatches.set(batchId, { polling });

    return { success: true };
}

/**
 * Pause a running batch — stops polling but does NOT stop the current episode.
 */
export async function pauseBatch(batchId: string): Promise<{ success: boolean; error?: string }> {
    const entry = activeBatches.get(batchId);
    if (entry) {
        clearInterval(entry.polling);
        activeBatches.delete(batchId);
    }

    await prisma.episodeBatch.update({
        where: { id: batchId },
        data: { status: "paused" },
    });

    return { success: true };
}

/**
 * Resume a paused batch — re-enters the polling loop.
 */
export async function resumeBatch(batchId: string): Promise<{ success: boolean; error?: string }> {
    const batch = await prisma.episodeBatch.findUnique({ where: { id: batchId } });
    if (!batch) return { success: false, error: "Batch not found." };
    if (batch.status !== "paused") return { success: false, error: "Batch is not paused." };

    await prisma.episodeBatch.update({
        where: { id: batchId },
        data: { status: "running" },
    });

    // Check if there's a running episode; if not, launch next
    const running = await prisma.episode.findFirst({
        where: { batchId, status: "running" },
    });
    if (!running) {
        await launchNextEpisode(batchId);
    }

    const polling = setInterval(() => advanceBatch(batchId), 10_000);
    activeBatches.set(batchId, { polling });

    return { success: true };
}

/**
 * Find the next queued episode in the batch and start it.
 */
async function launchNextEpisode(batchId: string): Promise<{ success: boolean; error?: string }> {
    const config = await prisma.config.findFirst();
    if (!config) return { success: false, error: "Config not found." };

    const nextEpisode = await prisma.episode.findFirst({
        where: { batchId, status: "queued" },
        orderBy: { batchIndex: "asc" },
        include: { launchProfile: true, scene: true },
    });

    if (!nextEpisode) {
        return { success: false, error: "No queued episodes remaining." };
    }

    const runnerMode = nextEpisode.launchProfile?.runnerMode || config.runnerMode;
    const runner = getRunner(runnerMode);

    const result = await runner.startEpisode(nextEpisode, config);
    if (!result.success) {
        await prisma.episode.update({
            where: { id: nextEpisode.id },
            data: { status: "failed", notes: `${nextEpisode.notes}\nLaunch failed: ${result.error}` },
        });
        await updateBatchCounters(batchId);
        return { success: false, error: result.error };
    }

    const outputDir = config.defaultOutputDir
        ? `${config.defaultOutputDir}/episodes/${nextEpisode.id}/`
        : `./data/episodes/${nextEpisode.id}/`;

    await prisma.episode.update({
        where: { id: nextEpisode.id },
        data: {
            status: "running",
            startedAt: new Date(),
            outputDir,
        },
    });

    await prisma.episodeBatch.update({
        where: { id: batchId },
        data: { currentIndex: nextEpisode.batchIndex ?? 0 },
    });

    console.log(`[BatchExecutor] Started episode ${nextEpisode.batchIndex! + 1} (${nextEpisode.id}) for batch ${batchId}`);
    return { success: true };
}

/**
 * Check the status of the currently running episode.
 * If it's done, update counters and launch the next one.
 */
async function advanceBatch(batchId: string) {
    try {
        const batch = await prisma.episodeBatch.findUnique({ where: { id: batchId } });
        if (!batch || batch.status !== "running") {
            stopPolling(batchId);
            return;
        }

        const config = await prisma.config.findFirst();
        if (!config) return;

        const runningEpisode = await prisma.episode.findFirst({
            where: { batchId, status: "running" },
            include: { launchProfile: true, scene: true },
        });

        if (!runningEpisode) {
            // No running episode — either it completed or failed externally
            await updateBatchCounters(batchId);
            const remaining = await prisma.episode.count({
                where: { batchId, status: "queued" },
            });

            if (remaining === 0) {
                await prisma.episodeBatch.update({
                    where: { id: batchId },
                    data: { status: "completed" },
                });
                stopPolling(batchId);
                console.log(`[BatchExecutor] Batch ${batchId} completed.`);
                return;
            }

            // Launch next
            const result = await launchNextEpisode(batchId);
            if (!result.success) {
                // Skip this episode, try next on the next poll
                console.error(`[BatchExecutor] Failed to launch next episode: ${result.error}`);
            }
            return;
        }

        // Check if the running episode has actually finished
        const runnerMode = runningEpisode.launchProfile?.runnerMode || config.runnerMode;
        const runner = getRunner(runnerMode);
        const status = await runner.getLiveStatus(runningEpisode, config);

        if (status.status === "completed") {
            // Stop the episode gracefully
            await runner.stopEpisode(runningEpisode, config);
            await prisma.episode.update({
                where: { id: runningEpisode.id },
                data: { status: "completed", stoppedAt: new Date() },
            });
            await updateBatchCounters(batchId);

            console.log(`[BatchExecutor] Episode ${runningEpisode.batchIndex! + 1} completed.`);

            // Check remaining
            const remaining = await prisma.episode.count({
                where: { batchId, status: "queued" },
            });

            if (remaining === 0) {
                await prisma.episodeBatch.update({
                    where: { id: batchId },
                    data: { status: "completed" },
                });
                stopPolling(batchId);
                console.log(`[BatchExecutor] Batch ${batchId} fully completed.`);
                return;
            }

            // Small delay before launching next to let resources settle
            setTimeout(() => launchNextEpisode(batchId), 3_000);
        }
    } catch (error) {
        console.error(`[BatchExecutor] advanceBatch error for ${batchId}:`, error);
    }
}

async function updateBatchCounters(batchId: string) {
    const completed = await prisma.episode.count({ where: { batchId, status: "completed" } });
    const failed = await prisma.episode.count({ where: { batchId, status: "failed" } });
    await prisma.episodeBatch.update({
        where: { id: batchId },
        data: { completedCount: completed, failedCount: failed },
    });
}

function stopPolling(batchId: string) {
    const entry = activeBatches.get(batchId);
    if (entry) {
        clearInterval(entry.polling);
        activeBatches.delete(batchId);
    }
}

export function getActiveBatchIds(): string[] {
    return Array.from(activeBatches.keys());
}

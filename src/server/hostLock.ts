import { prisma } from "@/lib/prisma";

export async function acquireLock(host: string, episodeId: string): Promise<boolean> {
    try {
        const existing = await prisma.hostLock.findUnique({ where: { host } });
        if (existing) {
            if (existing.episodeId === episodeId) return true;
            return false; // Locked by someone else
        }

        await prisma.hostLock.create({
            data: {
                host,
                episodeId,
                lockType: "interactive_session"
            }
        });
        return true;
    } catch (error) {
        console.error("Lock acquisition error:", error);
        return false; // Safely fail on concurrency
    }
}

export async function releaseLock(host: string, episodeId: string): Promise<void> {
    try {
        await prisma.hostLock.deleteMany({
            where: {
                host,
                episodeId
            }
        });
    } catch (error) {
        console.error("Lock release error:", error);
    }
}

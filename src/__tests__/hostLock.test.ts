import { describe, it, expect, vi, beforeEach } from 'vitest';
import { acquireLock, releaseLock } from '../server/hostLock';
import { prisma } from '../lib/prisma';

// Mock Prisma
vi.mock('../lib/prisma', () => {
    return {
        prisma: {
            hostLock: {
                findUnique: vi.fn(),
                create: vi.fn(),
                deleteMany: vi.fn(),
            }
        }
    };
});

describe('HostLock', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('acquires lock when host is free', async () => {
        (prisma.hostLock.findUnique as any).mockResolvedValue(null);
        (prisma.hostLock.create as any).mockResolvedValue({ id: '1', host: 'test-host', episodeId: 'ep-1' });

        const result = await acquireLock('test-host', 'ep-1');
        expect(result).toBe(true);
        expect(prisma.hostLock.create).toHaveBeenCalledWith({
            data: { host: 'test-host', episodeId: 'ep-1', lockType: 'interactive_session' }
        });
    });

    it('fails to acquire lock when host is locked by another episode', async () => {
        (prisma.hostLock.findUnique as any).mockResolvedValue({ id: '1', host: 'test-host', episodeId: 'ep-other' });

        const result = await acquireLock('test-host', 'ep-1');
        expect(result).toBe(false);
        expect(prisma.hostLock.create).not.toHaveBeenCalled();
    });

    it('succeeds to acquire lock when host is locked by same episode (idempotent)', async () => {
        (prisma.hostLock.findUnique as any).mockResolvedValue({ id: '1', host: 'test-host', episodeId: 'ep-1' });

        const result = await acquireLock('test-host', 'ep-1');
        expect(result).toBe(true);
        expect(prisma.hostLock.create).not.toHaveBeenCalled();
    });

    it('releases lock', async () => {
        (prisma.hostLock.deleteMany as any).mockResolvedValue({ count: 1 });

        await releaseLock('test-host', 'ep-1');
        expect(prisma.hostLock.deleteMany).toHaveBeenCalledWith({
            where: { host: 'test-host', episodeId: 'ep-1' }
        });
    });
});

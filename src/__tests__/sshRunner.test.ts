import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SshRunner } from '../server/runner/sshRunner';
import * as hostLock from '../server/hostLock';
import { NodeSSH } from 'node-ssh';

// Auto-mock the module
vi.mock('node-ssh');
vi.mock('../server/hostLock', () => ({
    acquireLock: vi.fn(),
    releaseLock: vi.fn()
}));

describe('SshRunner', () => {
    let runner: SshRunner;
    let mockConnect: any;
    let mockExecCommand: any;
    let mockPutFile: any;

    beforeEach(() => {
        vi.clearAllMocks();
        runner = new SshRunner();

        mockConnect = vi.fn();
        mockExecCommand = vi.fn();
        mockPutFile = vi.fn();

        // Attach mocks to the prototype so "new NodeSSH()" gets them
        NodeSSH.prototype.connect = mockConnect;
        NodeSSH.prototype.execCommand = mockExecCommand;
        NodeSSH.prototype.putFile = mockPutFile;
        NodeSSH.prototype.dispose = vi.fn();
        (NodeSSH.prototype as any).connection = { on: vi.fn() };
    });

    it('testConnection returns success when ping command works', async () => {
        mockConnect.mockResolvedValueOnce(undefined);
        mockExecCommand.mockResolvedValueOnce({ code: 0, stdout: 'SSH Connection Successful', stderr: '' });

        const config = { isaacHost: 'test@192.168.1.5', isaacAuthMode: 'password' };
        const result = await runner.testConnection(config);

        expect(result.isaacHostReachable).toBe(true);
        expect(result.sshReachable).toBe(true);
        expect(mockConnect).toHaveBeenCalled();
        expect(mockExecCommand).toHaveBeenCalledWith('echo "SSH Connection Successful"');
    });

    it('testConnection returns failure when connection throws', async () => {
        mockConnect.mockRejectedValueOnce(new Error('Connection timeout'));

        const config = { isaacHost: 'test@192.168.1.5' };
        const result = await runner.testConnection(config);

        expect(result.isaacHostReachable).toBe(false);
        expect(result.sshReachable).toBe(false);
        expect(result.errors).toContain('Connection timeout');
    });

    it('startEpisode acquires lock and uploads script', async () => {
        vi.mocked(hostLock.acquireLock).mockResolvedValueOnce(true);
        mockConnect.mockResolvedValueOnce(undefined);
        mockPutFile.mockResolvedValueOnce(undefined);
        mockExecCommand.mockResolvedValueOnce({ code: 0, stdout: '', stderr: '' });
        mockExecCommand.mockResolvedValueOnce({ code: 0, stdout: '', stderr: '' });
        mockExecCommand.mockResolvedValueOnce({ code: 0, stdout: '', stderr: '' });

        const episode = { id: 'ep-123' };
        const config = { isaacHost: 'test@192.168.1.5' };

        const result = await runner.startEpisode(episode, config);

        expect(hostLock.acquireLock).toHaveBeenCalledWith('test@192.168.1.5', 'ep-123');
        expect(mockPutFile).toHaveBeenCalled();

        // We now expect 3 commands: New-Item (dir), Set-Content (bat file), and Invoke-WmiMethod (execution)
        expect(mockExecCommand).toHaveBeenCalledTimes(3);

        // Regression protection: Verify that WMI is used instead of Start-Process to prevent Windows detached process crashes
        // and that we use a .bat array string to preserve newlines over SSH
        const calls = mockExecCommand.mock.calls.map((call: any[]) => call[0]);

        expect(calls.some((cmd: string) => cmd.includes('Set-Content') && cmd.includes("'@echo off', 'set PYTHONUNBUFFERED=1'"))).toBe(true);
        expect(calls.some((cmd: string) => cmd.includes('Invoke-WmiMethod -Class Win32_Process'))).toBe(true);
        expect(calls.some((cmd: string) => cmd.includes('Start-Process'))).toBe(false);

        expect(result.success).toBe(true);
    });

    it('startEpisode fails if host is already locked', async () => {
        vi.mocked(hostLock.acquireLock).mockResolvedValueOnce(false);

        const episode = { id: 'ep-123' };
        const config = { isaacHost: 'test@192.168.1.5' };

        const result = await runner.startEpisode(episode, config);

        expect(hostLock.acquireLock).toHaveBeenCalledWith('test@192.168.1.5', 'ep-123');
        expect(mockConnect).not.toHaveBeenCalled();
        expect(result.success).toBe(false);
        expect(result.error).toContain('is currently locked');
    });
});

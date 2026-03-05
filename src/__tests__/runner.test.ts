import { describe, it, expect } from 'vitest';
import { getRunner } from '../server/runner';
import { LocalRunner } from '../server/runner/localRunner';
import { SshRunner } from '../server/runner/sshRunner';
import { AgentRunner } from '../server/runner/agentRunner';

describe('Runner Factory', () => {
    it('returns LocalRunner', () => {
        expect(getRunner('LOCAL_RUNNER')).toBeInstanceOf(LocalRunner);
    });

    it('returns SshRunner', () => {
        expect(getRunner('SSH_RUNNER')).toBeInstanceOf(SshRunner);
        expect(getRunner('unknown')).toBeInstanceOf(SshRunner); // default
    });

    it('returns AgentRunner', () => {
        expect(getRunner('AGENT_RUNNER')).toBeInstanceOf(AgentRunner);
    });
});

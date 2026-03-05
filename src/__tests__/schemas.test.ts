import { describe, it, expect } from 'vitest';
import { configSchema } from '../lib/schemas';

describe('Config Validation Schema', () => {
    it('validates a complete valid config', () => {
        const validData = {
            appName: "RoboLab",
            isaacHost: "192.168.0.21",
            isaacSessionMode: "launch_new",
            runnerMode: "SSH_RUNNER",
            isaacSshPort: 22,
            isaacUser: "operator",
            isaacAuthMode: "password",
            sshKeyPath: "",
            rosDomainId: "77",
            rosNamespace: "/tiago",
            rmwImplementation: "rmw_cyclonedds_cpp",
            defaultOutputDir: "./data",
            streamingMode: "external_webrtc_client",
            defaultRecordTopics: "[]",
            futurePlaceholders: "{}"
        };

        const result = configSchema.safeParse(validData);
        expect(result.success).toBe(true);
    });

    it('fails on invalid IP format (loose check, but requires string)', () => {
        const invalidData = {
            isaacHost: 1234, // not a string
        };

        const result = configSchema.safeParse(invalidData);
        expect(result.success).toBe(false);
    });
});

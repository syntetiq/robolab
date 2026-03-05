import { z } from "zod";

export const configSchema = z.object({
    appName: z.string().min(1, "App Name is required"),
    isaacHost: z.string().min(1, "Isaac Host is required"),
    isaacSessionMode: z.enum(["launch_new", "attach_to_running"]),
    runnerMode: z.enum(["LOCAL_RUNNER", "SSH_RUNNER", "AGENT_RUNNER"]),
    isaacSshPort: z.coerce.number().int().min(1).max(65535),
    isaacUser: z.string().min(1, "Isaac User is required"),
    isaacAuthMode: z.enum(["password", "ssh_key"]),
    sshKeyPath: z.string().optional().default(""),
    sshPassword: z.string().optional().default(""),
    isaacInstallPath: z.string().min(1, "Install Path is required").default("C:\\Users\\max\\Documents\\IsaacSim"),
    rosDomainId: z.coerce.number().int().min(0),
    rosNamespace: z.string(),
    rmwImplementation: z.string(),
    cycloneDdsConfigPath: z.string().optional().default(""),
    defaultOutputDir: z.string().min(1, "Default Output Dir is required"),
    streamingMode: z.enum(["none", "external_webrtc_client", "browser_embedded_optional"]),
    streamingHint: z.string().optional().default(""),
    defaultRecordTopics: z.string(), // json string representation
    futurePlaceholders: z.string(), // json string representation
});

export type ConfigFormData = z.infer<typeof configSchema>;

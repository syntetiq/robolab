import { Runner } from "./Runner";
import { LocalRunner } from "./localRunner";
import { SshRunner } from "./sshRunner";
import { AgentRunner } from "./agentRunner";

export function getRunner(runnerMode: string): Runner {
    switch (runnerMode) {
        case "LOCAL_RUNNER": return new LocalRunner();
        case "SSH_RUNNER": return new SshRunner();
        case "AGENT_RUNNER": return new AgentRunner();
        default: return new SshRunner();
    }
}

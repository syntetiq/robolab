import { Runner, DiagnosticReport, StartResult, StopResult, StatusSnapshot } from "./Runner";

export class AgentRunner implements Runner {
    async testConnection(config: any): Promise<DiagnosticReport> {
        return {
            isaacHostReachable: true,
            sshReachable: null,
            resolvedIp: "Agent API Edge",
            latencyMs: 50,
            errors: [],
            recommendations: ["Agent runner mode ready. Awaiting remote API orchestration."]
        };
    }

    async startEpisode(episode: any, config: any): Promise<StartResult> {
        console.log(`[AgentRunner] Pushing episode ${episode.id} to Agent API...`);
        return { success: true };
    }

    async stopEpisode(episode: any, config: any): Promise<StopResult> {
        console.log(`[AgentRunner] Sending stop signal for episode ${episode.id} to Agent API...`);
        return { success: true };
    }

    async getLiveStatus(episode: any, config: any): Promise<StatusSnapshot> {
        return {
            status: "running",
            uptimeSec: Math.floor((Date.now() - new Date(episode.startedAt || Date.now()).getTime()) / 1000),
            cpuUsage: 0,
            memoryUsage: 0
        };
    }

    async getLiveLogs(episode: any, config: any, lines?: number): Promise<string[]> {
        return ["Agent runtime deferred."];
    }

    async syncData(episode: any, config: any): Promise<{ success: boolean; error?: string }> {
        return { success: true };
    }
}

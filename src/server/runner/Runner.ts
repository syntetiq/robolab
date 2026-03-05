export interface DiagnosticReport {
    isaacHostReachable: boolean;
    sshReachable: boolean | null;
    resolvedIp: string;
    latencyMs: number;
    errors: string[];
    recommendations: string[];
}

export interface StartResult {
    success: boolean;
    error?: string;
}

export interface StopResult {
    success: boolean;
    error?: string;
}

export interface StatusSnapshot {
    status: string;
    uptimeSec: number;
    cpuUsage: number;
    memoryUsage: number;
}

export interface Runner {
    /** Test connection based on config */
    testConnection(config: any): Promise<DiagnosticReport>;

    /** Attempt to start the Isaac Sim episode. Returns success or error. */
    startEpisode(episode: any, config: any): Promise<StartResult>;

    /** Attempt to stop the Isaac Sim episode via OS-level signals */
    stopEpisode(episode: any, config: any): Promise<StopResult>;

    /** Fast poll for status (running vs completed) and basic metrics */
    getLiveStatus(episode: any, config: any): Promise<StatusSnapshot>;

    /** Fetch the latest N lines of stdout from the simulation log */
    getLiveLogs(episode: any, config: any, lines?: number): Promise<string[]>;

    /** Synchronize artifacts (video, telemetry data) from remote to local storage */
    syncData(episode: any, config: any): Promise<{ success: boolean; error?: string }>;
}

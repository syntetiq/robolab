export type TeleopInputSource = "keyboard_mouse" | "mock_vr_replay" | "vive_openxr" | "ui_button";

export interface MockReplayFrame {
    linearX?: number;
    angularZ?: number;
    action?: string;
}

export interface ResolveInputArgs {
    source?: string;
    command?: string;
    replayFrame?: MockReplayFrame;
}

export interface ResolvedTeleopCommand {
    source: TeleopInputSource;
    command: string;
}

const SUPPORTED_SOURCES: TeleopInputSource[] = ["keyboard_mouse", "mock_vr_replay", "vive_openxr", "ui_button"];

function normalizeSource(source?: string): TeleopInputSource {
    if (!source) return "keyboard_mouse";
    return SUPPORTED_SOURCES.includes(source as TeleopInputSource)
        ? (source as TeleopInputSource)
        : "keyboard_mouse";
}

function resolveFromMockReplay(replayFrame?: MockReplayFrame, fallbackCommand?: string): string {
    if (replayFrame?.action) {
        return replayFrame.action;
    }
    const linear = replayFrame?.linearX ?? 0;
    const angular = replayFrame?.angularZ ?? 0;
    const absLinear = Math.abs(linear);
    const absAngular = Math.abs(angular);
    const threshold = 0.05;

    if (absLinear < threshold && absAngular < threshold) {
        return "stop_motion";
    }
    if (absLinear >= absAngular) {
        return linear >= 0 ? "move_forward" : "move_backward";
    }
    return angular >= 0 ? "move_left" : "move_right";
}

export function resolveTeleopInput(args: ResolveInputArgs): ResolvedTeleopCommand {
    const source = normalizeSource(args.source);
    if (source === "mock_vr_replay") {
        return {
            source,
            command: resolveFromMockReplay(args.replayFrame, args.command),
        };
    }

    return {
        source,
        command: args.command || "",
    };
}

export function getSupportedTeleopSources(): TeleopInputSource[] {
    return [...SUPPORTED_SOURCES];
}

import fs from "fs";
import path from "path";
import { execSync } from "child_process";

export type OrchestrationStage = "idle" | "starting" | "ready" | "intent_sent" | "result_received" | "failed";
export type OrchestrationStatus = "idle" | "running" | "succeeded" | "failed";

export interface OrchestrationState {
    episodeId: string;
    status: OrchestrationStatus;
    stage: OrchestrationStage;
    ready: boolean;
    intentSent: boolean;
    resultReceived: boolean;
    failedReason: string;
    pid: number | null;
    logPath: string;
    startedAt: string | null;
    finishedAt: string | null;
    updatedAt: string;
}

function nowIso(): string {
    return new Date().toISOString();
}

/**
 * Keep only the N most recently created episode data directories.
 * Removes both the data folder and the corresponding orchestration files.
 */
export function pruneOldEpisodes(outputRoot: string, keepCount = 20): void {
    const episodesDir = path.join(outputRoot, "episodes");
    if (!fs.existsSync(episodesDir)) return;
    try {
        const dirs = fs
            .readdirSync(episodesDir, { withFileTypes: true })
            .filter((d) => d.isDirectory() && fs.existsSync(path.join(episodesDir, d.name, "dataset.json")))
            .map((d) => {
                const full = path.join(episodesDir, d.name);
                const stat = fs.statSync(full);
                return { name: d.name, full, birthtime: stat.birthtimeMs };
            })
            .sort((a, b) => b.birthtime - a.birthtime);

        const toDelete = dirs.slice(keepCount);
        for (const ep of toDelete) {
            try {
                fs.rmSync(ep.full, { recursive: true, force: true });
                // Remove orchestration metadata files
                for (const suffix of ["_orchestration.log", "_orchestration_state.json", "_orchestration_wrapper.ps1"]) {
                    const f = path.join(episodesDir, ep.name + suffix);
                    if (fs.existsSync(f)) fs.unlinkSync(f);
                }
            } catch {
                // Ignore individual delete errors
            }
        }
    } catch {
        // Non-fatal: pruning failure must not block the run
    }
}

function isPidRunning(pid: number | null): boolean {
    if (!pid || !Number.isInteger(pid) || pid <= 0) {
        return false;
    }
    try {
        const out = execSync(`powershell -NoProfile -Command "if (Get-Process -Id ${pid} -ErrorAction SilentlyContinue) { '1' } else { '0' }"`, {
            encoding: "utf8",
            stdio: ["ignore", "pipe", "ignore"],
        }).trim();
        return out === "1";
    } catch {
        return false;
    }
}

function readLogText(logPath: string): string {
    const raw = fs.readFileSync(logPath);
    // Logs can contain mixed UTF-16 + UTF-8 fragments; normalize to searchable plain text.
    return raw
        .toString("utf8")
        .replace(/\u0000/g, "")
        .replace(/^\uFEFF/, "");
}

function parseLogForState(state: OrchestrationState): OrchestrationState {
    const startedMs = state.startedAt ? new Date(state.startedAt).getTime() : Date.now();
    const elapsedMs = Date.now() - startedMs;
    if (!fs.existsSync(state.logPath)) {
        if (state.status === "running" && elapsedMs > 5000) {
            return {
                ...state,
                status: "failed",
                stage: "failed",
                failedReason: "Orchestration log file was not created by runner process.",
                finishedAt: state.finishedAt || nowIso(),
                updatedAt: nowIso(),
            };
        }
        return state;
    }
    const content = readLogText(state.logPath);
    const readyMatched = /move_group ready: matched|Bridge: subscribe .+ -> action \/move_action/i.test(content);
    const intentMatched = /\[ExecSmokeJob\]|ros2_pub_string|Intent delay/i.test(content);
    const resultSuccessMatched = /\[ExecSmoke\] Bridge result:\s*MoveGroup goal succeeded/i.test(content);
    const resultFailedMatch = content.match(/\[ExecSmoke\] Bridge did not report success:\s*(.+)/i);
    const smokeFailedMatch = content.match(/\[ExecSmoke\] Smoke failed with exit code\s*(-?\d+)/i);
    const timeoutMatch = content.match(/Timeout waiting for MoveGroup result in bridge log/i);
    const wrapperExceptionMatch = content.match(/\[OrchWrapper\] Exception:\s*(.+)/i);

    const updated: OrchestrationState = {
        ...state,
        ready: state.ready || readyMatched,
        intentSent: state.intentSent || intentMatched,
        resultReceived: state.resultReceived || resultSuccessMatched || !!resultFailedMatch || !!timeoutMatch,
        updatedAt: nowIso(),
    };

    if (updated.status === "running" && updated.ready) {
        updated.stage = "ready";
    }
    if (updated.status === "running" && updated.intentSent) {
        updated.stage = "intent_sent";
    }

    if (resultSuccessMatched) {
        updated.status = "succeeded";
        updated.stage = "result_received";
        updated.resultReceived = true;
        updated.finishedAt = updated.finishedAt || nowIso();
        updated.failedReason = "";
    } else if (resultFailedMatch || smokeFailedMatch || timeoutMatch || wrapperExceptionMatch) {
        updated.status = "failed";
        updated.stage = "failed";
        updated.finishedAt = updated.finishedAt || nowIso();
        updated.failedReason =
            (resultFailedMatch?.[1] || "").trim() ||
            (smokeFailedMatch ? `Smoke failed with exit code ${smokeFailedMatch[1]}` : "") ||
            (wrapperExceptionMatch?.[1] || "").trim() ||
            (timeoutMatch ? "Timeout waiting for MoveGroup result." : "Orchestration failed.");
    }

    if (updated.status === "running" && !isPidRunning(updated.pid)) {
        if (updated.resultReceived) {
            updated.status = "succeeded";
            updated.stage = "result_received";
            updated.finishedAt = updated.finishedAt || nowIso();
        } else {
            updated.status = "failed";
            updated.stage = "failed";
            updated.finishedAt = updated.finishedAt || nowIso();
            updated.failedReason = updated.failedReason || "Orchestration process exited before result.";
        }
    }

    return updated;
}

function getStatePath(outputRoot: string, episodeId: string): string {
    return path.join(outputRoot, "episodes", `${episodeId}_orchestration_state.json`);
}

function ensureParent(filePath: string): void {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function psSingleQuote(value: string): string {
    return value.replace(/'/g, "''");
}

export function readOrchestrationState(outputRoot: string, episodeId: string): OrchestrationState {
    const statePath = getStatePath(outputRoot, episodeId);
    if (!fs.existsSync(statePath)) {
        return {
            episodeId,
            status: "idle",
            stage: "idle",
            ready: false,
            intentSent: false,
            resultReceived: false,
            failedReason: "",
            pid: null,
            logPath: "",
            startedAt: null,
            finishedAt: null,
            updatedAt: nowIso(),
        };
    }
    try {
        const raw = JSON.parse(fs.readFileSync(statePath, "utf8")) as OrchestrationState;
        return parseLogForState(raw);
    } catch {
        return {
            episodeId,
            status: "failed",
            stage: "failed",
            ready: false,
            intentSent: false,
            resultReceived: false,
            failedReason: "Failed to parse orchestration state file.",
            pid: null,
            logPath: "",
            startedAt: null,
            finishedAt: nowIso(),
            updatedAt: nowIso(),
        };
    }
}

function writeOrchestrationState(outputRoot: string, episodeId: string, state: OrchestrationState): void {
    const statePath = getStatePath(outputRoot, episodeId);
    ensureParent(statePath);
    fs.writeFileSync(statePath, JSON.stringify({ ...state, updatedAt: nowIso() }, null, 2), "utf8");
}

export function startExecSmokeOrchestration(args: {
    outputRoot: string;
    episodeId: string;
    durationSec: number;
    requireRealTiago: boolean;
    force?: boolean;
    intent?: string;
    intentSequence?: string[];
    intentDelaySec?: number;
    intentResultTimeoutSec?: number;
    maxRetriesPerIntent?: number;
    preGoHomeBetweenStages?: boolean;
    retryOnCodeMinus4?: boolean;
    warmupGoHome?: boolean;
}): OrchestrationState {
    // Prune old episodes before starting a new run to avoid filling the disk.
    pruneOldEpisodes(args.outputRoot, 60);

    const existing = readOrchestrationState(args.outputRoot, args.episodeId);
    // Allow force-restart: if already running but caller wants to restart, kill the old process.
    if (existing.status === "running" && existing.pid && isPidRunning(existing.pid)) {
        if (!args.force) {
            return existing;
        }
        // Force restart: terminate the old orchestration process.
        try {
            execSync(`taskkill /PID ${existing.pid} /T /F`, { stdio: "ignore" });
        } catch {
            // ignore
        }
    }

    const scriptPath = path.join(process.cwd(), "scripts", "run_tiago_moveit_execute_smoke.ps1");
    if (!fs.existsSync(scriptPath)) {
        const failed: OrchestrationState = {
            ...existing,
            status: "failed",
            stage: "failed",
            failedReason: `Missing script: ${scriptPath}`,
            finishedAt: nowIso(),
            updatedAt: nowIso(),
        };
        writeOrchestrationState(args.outputRoot, args.episodeId, failed);
        return failed;
    }

    const logsDir = path.join(args.outputRoot, "episodes");
    fs.mkdirSync(logsDir, { recursive: true });
    const logPath = path.join(logsDir, `${args.episodeId}_orchestration.log`);
    const intent = args.intent || "plan_pick_sink";
    const delay = Math.max(0, args.intentDelaySec ?? 0);
    // In execution mode, each intent needs: planning (~5s) + FJT execution (~5s) + margin.
    // Default result timeout = 150 s to accommodate planning + real trajectory execution.
    const resultTimeout = Math.max(30, args.intentResultTimeoutSec ?? 150);
    const duration = Math.max(10, args.durationSec);
    // Default to 4 retries – covers probabilistic OMPL failures.
    const maxRetriesPerIntent = Math.max(0, args.maxRetriesPerIntent ?? 4);
    const preGoHomeBetweenStages = args.preGoHomeBetweenStages !== false;
    const retryOnCodeMinus4 = args.retryOnCodeMinus4 !== false;
    // Warm-up go_home enabled by default for physics/controller stabilization.
    const warmupGoHome = args.warmupGoHome !== false;
    const intentSequence = (args.intentSequence || [])
        .map((x) => String(x || "").trim())
        .filter(Boolean);
    const escapedIntentSequence = psSingleQuote(intentSequence.join(","));
    const escapedScript = psSingleQuote(scriptPath);
    const escapedIntent = psSingleQuote(intent);
    const escapedLogPath = psSingleQuote(logPath);
    const wrapperPath = path.join(logsDir, `${args.episodeId}_orchestration_wrapper.ps1`);
    const escapedWrapperPath = psSingleQuote(wrapperPath);
    const wrapper = [
        "$ErrorActionPreference = 'Continue'",
        "try {",
        `  & '${escapedScript}' -Duration ${duration} -Intent '${escapedIntent}' -IntentDelaySec ${delay} -IntentResultTimeoutSec ${resultTimeout} -MaxRetriesPerIntent ${maxRetriesPerIntent} -PreGoHomeBetweenStages:$${preGoHomeBetweenStages ? "true" : "false"} -RetryOnCodeMinus4:$${retryOnCodeMinus4 ? "true" : "false"} -WarmupGoHome:$${warmupGoHome ? "true" : "false"}${intentSequence.length > 0 ? ` -IntentSequence '${escapedIntentSequence}'` : ""}${args.requireRealTiago ? " -RequireRealTiago" : ""} *>> '${escapedLogPath}'`,
        "  if ($LASTEXITCODE -ne $null) { exit $LASTEXITCODE }",
        "  exit 0",
        "} catch {",
        `  ('[OrchWrapper] Exception: ' + $_.Exception.Message) | Out-File -FilePath '${escapedLogPath}' -Append -Encoding utf8`,
        "  exit 1",
        "}",
    ].join("\r\n");
    fs.writeFileSync(wrapperPath, wrapper, "utf8");
    // Truncate the orchestration log for this run so stale results from previous
    // runs of the same episode don't confuse parseLogForState.
    try {
        fs.writeFileSync(logPath, "", "utf8");
    } catch {
        // Non-fatal: log append will still work.
    }

    const launcher = [
        "$ErrorActionPreference='Stop'",
        `$p = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File','${escapedWrapperPath}') -WindowStyle Hidden -PassThru`,
        "$p.Id",
    ].join("; ");
    const pidText = execSync(`powershell -NoProfile -ExecutionPolicy Bypass -Command "${launcher}"`, {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
    }).trim();
    const launchedPid = Number(pidText.split(/\r?\n/).pop() || "0");

    const next: OrchestrationState = {
        episodeId: args.episodeId,
        status: "running",
        stage: "starting",
        ready: false,
        intentSent: false,
        resultReceived: false,
        failedReason: "",
        pid: Number.isFinite(launchedPid) && launchedPid > 0 ? launchedPid : null,
        logPath,
        startedAt: nowIso(),
        finishedAt: null,
        updatedAt: nowIso(),
    };
    writeOrchestrationState(args.outputRoot, args.episodeId, next);
    return next;
}

export function refreshOrchestrationState(outputRoot: string, episodeId: string): OrchestrationState {
    const current = readOrchestrationState(outputRoot, episodeId);
    writeOrchestrationState(outputRoot, episodeId, current);
    return current;
}

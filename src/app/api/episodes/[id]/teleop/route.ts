import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { NodeSSH } from "node-ssh";
import { exec, spawn } from "child_process";
import { promisify } from "util";
import fs from "fs";
import path from "path";
import os from "os";

const execAsync = promisify(exec);

const SUPPORTED_COMMANDS = new Set([
    "move_forward",
    "move_backward",
    "move_left",
    "move_right",
    "grasp_mug",
    "go_home",
    "start_vr_session",
    "stop_vr_session",
    "start_moveit_session",
    "stop_moveit_session",
    "moveit_plan_pick",
    "moveit_plan_place",
    "moveit_plan_pick_sink",
    "moveit_plan_pick_fridge",
    "moveit_go_home",
]);

function mapCommandToLogLine(command: string): string {
    switch (command) {
        case "move_forward": return "[Teleop] move_forward requested.";
        case "move_backward": return "[Teleop] move_backward requested.";
        case "move_left": return "[Teleop] move_left requested.";
        case "move_right": return "[Teleop] move_right requested.";
        case "grasp_mug": return "[Teleop] grasp_mug requested.";
        case "go_home": return "[Teleop] go_home requested.";
        case "start_vr_session": return "[Teleop] start_vr_session requested.";
        case "stop_vr_session": return "[Teleop] stop_vr_session requested.";
        case "start_moveit_session": return "[Teleop] start_moveit_session requested.";
        case "stop_moveit_session": return "[Teleop] stop_moveit_session requested.";
        case "moveit_plan_pick": return "[Teleop] moveit_plan_pick requested.";
        case "moveit_plan_place": return "[Teleop] moveit_plan_place requested.";
        case "moveit_plan_pick_sink": return "[Teleop] moveit_plan_pick_sink requested.";
        case "moveit_plan_pick_fridge": return "[Teleop] moveit_plan_pick_fridge requested.";
        case "moveit_go_home": return "[Teleop] moveit_go_home requested.";
        default: return `[Teleop] ${command} requested.`;
    }
}

function templateWithTokens(template: string, params: Record<string, string>): string {
    let resolved = template;
    for (const [k, v] of Object.entries(params)) {
        resolved = resolved.split(`{${k}}`).join(v);
    }
    return resolved;
}

async function appendLogLocal(logPath: string, line: string) {
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, `${line}\n`, "utf8");
}

function getPaths(outputRoot: string, episodeId: string) {
    const base = path.join(outputRoot, "episodes");
    return {
        state: path.join(base, `${episodeId}_teleop_state.json`),
        vrPid: path.join(base, `${episodeId}_vr.pid`),
        moveitPid: path.join(base, `${episodeId}_moveit.pid`),
    };
}

function readState(statePath: string) {
    if (!fs.existsSync(statePath)) {
        return {
            vrSessionActive: false,
            moveitSessionActive: false,
            ros2Available: null,
            moveitAvailable: null,
            bridgeMode: "unknown",
            lastCommand: "",
            updatedAt: new Date().toISOString(),
            lastError: "",
        };
    }
    try {
        return JSON.parse(fs.readFileSync(statePath, "utf8"));
    } catch {
        return {
            vrSessionActive: false,
            moveitSessionActive: false,
            ros2Available: null,
            moveitAvailable: null,
            bridgeMode: "unknown",
            lastCommand: "",
            updatedAt: new Date().toISOString(),
            lastError: "Failed to parse teleop state.",
        };
    }
}

function writeState(statePath: string, state: any) {
    fs.writeFileSync(statePath, JSON.stringify({
        ...state,
        updatedAt: new Date().toISOString(),
    }, null, 2));
}

function startDetached(command: string): number {
    const child = spawn(command, {
        shell: true,
        detached: true,
        windowsHide: true,
        stdio: "ignore",
    });
    child.unref();
    return child.pid || -1;
}

async function stopPid(pid: number) {
    if (!Number.isInteger(pid) || pid <= 0) return;
    await execAsync(`taskkill /F /T /PID ${pid}`);
}

function resolveCondaPython(): string {
    const home = os.homedir();
    const candidates = [
        path.join(home, "Mambaforge", "envs", "ros2_humble", "python.exe"),
        path.join(home, "mambaforge", "envs", "ros2_humble", "python.exe"),
    ];
    for (const p of candidates) {
        if (fs.existsSync(p)) return p;
    }
    return "";
}

function resolveRos2ScriptInvoker() {
    const home = os.homedir();
    const candidates = [
        {
            python: path.join(home, "Mambaforge", "envs", "ros2_humble", "python.exe"),
            script: path.join(home, "Mambaforge", "envs", "ros2_humble", "Library", "bin", "ros2-script.py"),
        },
        {
            python: path.join(home, "mambaforge", "envs", "ros2_humble", "python.exe"),
            script: path.join(home, "mambaforge", "envs", "ros2_humble", "Library", "bin", "ros2-script.py"),
        },
    ];
    for (const c of candidates) {
        if (fs.existsSync(c.python) && fs.existsSync(c.script)) {
            return `"${c.python}" "${c.script}"`;
        }
    }
    return "";
}

function wrapWithSetup(command: string, setupCommand?: string) {
    const setup = (setupCommand || "").trim();
    if (!setup) return command;
    const escaped = `${setup} && ${command}`.replace(/"/g, '\\"');
    return `cmd.exe /d /s /c "${escaped}"`;
}

async function probeLocalRos2(setupCommand?: string): Promise<{ ros2Available: boolean; moveitAvailable: boolean; ros2Invoker: string }> {
    let ros2Invoker = "ros2";
    const whereRos2 = wrapWithSetup("where ros2", setupCommand);
    let commandAvailable = true;
    try {
        await execAsync(whereRos2, { timeout: 3000 });
    } catch {
        commandAvailable = false;
    }

    if (!commandAvailable) {
        const scriptInvoker = resolveRos2ScriptInvoker();
        if (!scriptInvoker) {
            return { ros2Available: false, moveitAvailable: false, ros2Invoker: "" };
        }
        ros2Invoker = scriptInvoker;
    }

    const actionList = wrapWithSetup(`${ros2Invoker} action list`, setupCommand);
    try {
        const { stdout } = await execAsync(actionList, { timeout: 5000 });
        const hasMoveIt = stdout.includes("/move_action") || stdout.includes("/move_group");
        return { ros2Available: true, moveitAvailable: hasMoveIt, ros2Invoker };
    } catch {
        return { ros2Available: true, moveitAvailable: false, ros2Invoker };
    }
}

function normalizeNamespace(ns: string) {
    const trimmed = (ns || "/tiago").trim();
    if (!trimmed) return "/tiago";
    return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

async function execMoveitIntentPub(
    intentValue: string,
    rosNamespace: string,
    _ros2Invoker: string,
    ros2SetupCommand: string,
): Promise<void> {
    const ns = normalizeNamespace(rosNamespace);
    const topic = `${ns}/moveit/intent`;
    const py = resolveCondaPython();
    const scriptPath = path.join(process.cwd(), "scripts", "ros2_pub_string.py");
    if (!py || !fs.existsSync(scriptPath)) {
        throw new Error("Conda python or ros2_pub_string.py not found");
    }
    const cmd = `${py} ${scriptPath} ${topic} ${intentValue}`;
    await execAsync(wrapWithSetup(cmd, ros2SetupCommand), { timeout: 10000 });
}

function buildDefaultRos2Command(command: string, rosNamespace: string, ros2Invoker: string): string {
    const ns = normalizeNamespace(rosNamespace);
    const cmdVel = `${ns}/cmd_vel`;
    const teleopIntent = `${ns}/teleop/intent`;
    const moveitIntent = `${ns}/moveit/intent`;
    const ros2 = ros2Invoker || "ros2";

    switch (command) {
        case "move_forward":
            return `${ros2} topic pub -1 ${teleopIntent} std_msgs/msg/String {data:move_forward}`;
        case "move_backward":
            return `${ros2} topic pub -1 ${teleopIntent} std_msgs/msg/String {data:move_backward}`;
        case "move_left":
            return `${ros2} topic pub -1 ${teleopIntent} std_msgs/msg/String {data:move_left}`;
        case "move_right":
            return `${ros2} topic pub -1 ${teleopIntent} std_msgs/msg/String {data:move_right}`;
        case "grasp_mug":
            return `${ros2} topic pub -1 ${teleopIntent} std_msgs/msg/String {data:grasp_mug}`;
        case "go_home":
            return `${ros2} topic pub -1 ${teleopIntent} std_msgs/msg/String {data:go_home}`;
        case "moveit_plan_pick":
        case "moveit_plan_place":
        case "moveit_plan_pick_sink":
        case "moveit_plan_pick_fridge":
        case "moveit_go_home":
            return ""; // handled via execMoveitIntentPub (Python script)
        default:
            return "";
    }
}

export async function GET(
    _req: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    try {
        const { id } = await params;
        const episode = await prisma.episode.findUnique({
            where: { id },
            include: { launchProfile: true },
        });
        if (!episode) return NextResponse.json({ error: "Episode not found" }, { status: 404 });
        const config = await prisma.config.findUnique({ where: { id: 1 } });
        if (!config) return NextResponse.json({ error: "Global config not found" }, { status: 500 });

        const outputRoot = config.defaultOutputDir || "C:\\RoboLab_Data";
        const { state: statePath } = getPaths(outputRoot, episode.id);
        const state = readState(statePath);
        const profileSetup = (episode.launchProfile?.ros2SetupCommand || "").trim();
        const globalSetup = (config.ros2SetupCommand || "").trim();
        const activeSetupCommand = profileSetup || globalSetup;
        const setupSource = profileSetup ? "launch_profile" : globalSetup ? "global_config" : "none";
        return NextResponse.json({
            ...state,
            vrEnabled: !!episode.launchProfile?.enableVrTeleop,
            moveitEnabled: !!episode.launchProfile?.enableMoveIt,
            runnerMode: config.runnerMode,
            activeRos2SetupCommand: activeSetupCommand,
            ros2SetupSource: setupSource,
        });
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 });
    }
}

export async function POST(
    req: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    try {
        const { id } = await params;
        const episode = await prisma.episode.findUnique({
            where: { id },
            include: { launchProfile: true, scene: true }
        });
        if (!episode) return NextResponse.json({ error: "Episode not found" }, { status: 404 });

        const body = await req.json();
        const command = String(body.command || "");

        if (!command || !SUPPORTED_COMMANDS.has(command)) {
            return NextResponse.json({ error: "Unknown or missing command" }, { status: 400 });
        }

        const config = await prisma.config.findUnique({ where: { id: 1 } });
        if (!config) {
            return NextResponse.json({ error: "Global config not found" }, { status: 500 });
        }

        const outputRoot = config.defaultOutputDir || "C:\\RoboLab_Data";
        const episodeOutDir = episode.outputDir || `${outputRoot}\\episodes\\${episode.id}`;
        const logPath = `${outputRoot}\\episodes\\${episode.id}_teleop.log`;
        const sceneUsd = episode.scene?.stageUsdPath || "";

        const ros2SetupCommand = (episode.launchProfile?.ros2SetupCommand || config.ros2SetupCommand || "").trim();
        const tokenMap = {
            EPISODE_ID: episode.id,
            OUTPUT_DIR: episodeOutDir,
            SCENE_USD: sceneUsd,
            ACTION: command,
            ROS2_SETUP: ros2SetupCommand,
        };

        const teleopTemplate = (episode.launchProfile?.teleopLaunchTemplate || "").trim();
        const outputPaths = getPaths(outputRoot, episode.id);
        const state = readState(outputPaths.state);
        const launchFromTemplate = (
            command === "start_vr_session" ||
            command === "stop_vr_session" ||
            command === "start_moveit_session" ||
            command === "stop_moveit_session"
        ) && teleopTemplate;
        const templateRequired = (
            command === "start_vr_session" ||
            command === "stop_vr_session" ||
            command === "start_moveit_session" ||
            command === "stop_moveit_session"
        );
        if (templateRequired && !teleopTemplate) {
            state.lastError = "teleopLaunchTemplate is required for VR/MoveIt session commands.";
            state.lastCommand = command;
            writeState(outputPaths.state, state);
            return NextResponse.json(
                { error: "teleopLaunchTemplate is required for this command." },
                { status: 400 }
            );
        }

        const resolvedTemplateCommand = launchFromTemplate
            ? templateWithTokens(teleopTemplate, tokenMap)
            : "";

        const logLine = mapCommandToLogLine(command);

        if (config.runnerMode === "LOCAL_RUNNER") {
            await appendLogLocal(logPath, logLine);
            const ros2Probe = await probeLocalRos2(ros2SetupCommand);
            state.ros2Available = ros2Probe.ros2Available;
            state.moveitAvailable = ros2Probe.moveitAvailable;
            if (command === "start_vr_session" && resolvedTemplateCommand) {
                const pid = startDetached(resolvedTemplateCommand);
                fs.writeFileSync(outputPaths.vrPid, String(pid), "utf8");
                state.vrSessionActive = true;
                state.bridgeMode = "template_session";
            } else if (command === "stop_vr_session") {
                if (fs.existsSync(outputPaths.vrPid)) {
                    const pid = Number(fs.readFileSync(outputPaths.vrPid, "utf8").trim());
                    try { await stopPid(pid); } catch {}
                }
                state.vrSessionActive = false;
                state.bridgeMode = "template_session";
            } else if (command === "start_moveit_session" && resolvedTemplateCommand) {
                const pid = startDetached(resolvedTemplateCommand);
                fs.writeFileSync(outputPaths.moveitPid, String(pid), "utf8");
                state.moveitSessionActive = true;
                state.bridgeMode = "template_session";
            } else if (command === "stop_moveit_session") {
                if (fs.existsSync(outputPaths.moveitPid)) {
                    const pid = Number(fs.readFileSync(outputPaths.moveitPid, "utf8").trim());
                    try { await stopPid(pid); } catch {}
                }
                state.moveitSessionActive = false;
                state.bridgeMode = "template_session";
            } else if (resolvedTemplateCommand) {
                await execAsync(resolvedTemplateCommand);
                state.bridgeMode = "template_command";
            } else {
                const moveitIntentMap: Record<string, string> = {
                    moveit_plan_pick: "plan_pick",
                    moveit_plan_place: "plan_place",
                    moveit_plan_pick_sink: "plan_pick_sink",
                    moveit_plan_pick_fridge: "plan_pick_fridge",
                    moveit_go_home: "go_home",
                };
                const moveitIntentValue = moveitIntentMap[command] ?? null;
                const isMoveitIntent = !!moveitIntentValue;

                if (isMoveitIntent && moveitIntentValue && ros2Probe.ros2Available) {
                    try {
                        await execMoveitIntentPub(
                            moveitIntentValue,
                            config.rosNamespace,
                            ros2Probe.ros2Invoker,
                            ros2SetupCommand,
                        );
                        state.bridgeMode = "ros2_default";
                    } catch (err: any) {
                        state.bridgeMode = "ros2_failed";
                        state.lastError = err?.message || "ROS2 moveit intent pub failed.";
                        await appendLogLocal(logPath, `[Teleop] ROS2 moveit intent failed for ${command}: ${state.lastError}`);
                    }
                } else {
                    const defaultCommand = buildDefaultRos2Command(command, config.rosNamespace, ros2Probe.ros2Invoker);
                    if (defaultCommand) {
                        if (ros2Probe.ros2Available) {
                            try {
                                await execAsync(wrapWithSetup(defaultCommand, ros2SetupCommand), { timeout: 10000 });
                                state.bridgeMode = "ros2_default";
                            } catch (err: any) {
                                state.bridgeMode = "ros2_failed";
                                state.lastError = err?.message || "ROS2 command execution failed.";
                                await appendLogLocal(logPath, `[Teleop] ROS2 command failed for ${command}: ${state.lastError}`);
                            }
                        } else {
                            state.bridgeMode = "mock_fallback";
                            await appendLogLocal(logPath, `[Teleop] ROS2 not available, fallback for ${command}.`);
                        }
                    }
                }
            }
            state.lastCommand = command;
            if (state.bridgeMode !== "ros2_failed") {
                state.lastError = "";
            }
            writeState(outputPaths.state, state);
            return NextResponse.json({
                success: true,
                command,
                mode: "LOCAL_RUNNER",
                templateExecuted: !!resolvedTemplateCommand,
                teleopState: state,
            });
        }

        const ssh = new NodeSSH();
        const hostPath = config.isaacHost.split("@");
        const username = hostPath.length > 1 ? hostPath[0] : "max";
        const host = hostPath.length > 1 ? hostPath[1] : config.isaacHost;
        const connectOptions: any = {
            host,
            port: config.isaacSshPort,
            username: config.isaacUser || username,
        };
        if (config.isaacAuthMode === "ssh_key" && config.sshKeyPath) {
            connectOptions.privateKeyPath = config.sshKeyPath;
        } else if (config.sshPassword) {
            connectOptions.password = config.sshPassword;
        }
        await ssh.connect(connectOptions);

        const escapedLine = logLine.replace(/"/g, '\\"');
        const escapedLog = logPath.replace(/\\/g, "\\\\");
        const appendLogCommand = `powershell -Command "Add-Content -Path \\"${escapedLog}\\" -Value \\"${escapedLine}\\""`;
        const resultLog = await ssh.execCommand(appendLogCommand);
        if (resultLog.code !== 0) {
            ssh.dispose();
            return NextResponse.json({ error: "Failed to append teleop log on remote host" }, { status: 500 });
        }

        let resultTemplate = { code: 0, stderr: "" };
        if (resolvedTemplateCommand) {
            resultTemplate = await ssh.execCommand(resolvedTemplateCommand);
            state.bridgeMode = "template_command";
        } else {
            const defaultCommand = buildDefaultRos2Command(command, config.rosNamespace, "ros2");
            if (defaultCommand) {
                resultTemplate = await ssh.execCommand(wrapWithSetup(defaultCommand, ros2SetupCommand));
                state.bridgeMode = resultTemplate.code === 0 ? "ros2_default" : "ros2_failed";
            }
        }
        ssh.dispose();

        if (resultTemplate.code !== 0) {
            console.error("[Teleop Error]", resultTemplate.stderr);
            state.lastError = resultTemplate.stderr || "Failed to dispatch command.";
            state.lastCommand = command;
            writeState(outputPaths.state, state);
            return NextResponse.json({ error: "Failed to dispatch command to host" }, { status: 500 });
        }

        if (command === "start_vr_session") state.vrSessionActive = true;
        if (command === "stop_vr_session") state.vrSessionActive = false;
        if (command === "start_moveit_session") state.moveitSessionActive = true;
        if (command === "stop_moveit_session") state.moveitSessionActive = false;
        state.lastCommand = command;
        state.lastError = "";
        writeState(outputPaths.state, state);

        return NextResponse.json({
            success: true,
            command,
            mode: "SSH_RUNNER",
            templateExecuted: !!resolvedTemplateCommand,
            teleopState: state,
        });
    } catch (e: any) {
        console.error("[Teleop] Error processing command:", e.message);
        return NextResponse.json({ error: e.message }, { status: 500 });
    }
}

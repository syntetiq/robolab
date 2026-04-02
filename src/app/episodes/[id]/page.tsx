"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Play, Square, CheckCircle, XCircle, Download, Info, RefreshCcw, HelpCircle } from "lucide-react";
import { format } from "date-fns";
import { Progress } from "@/components/ui/progress";
import { HelpTooltip } from "@/components/HelpTooltip";
import { VideoPlayerCard } from "@/components/episodes/VideoPlayerCard";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from "@/components/ui/dialog";

/* ─── help content for modal tooltips ─── */
const HELP = {
    baseMovement: {
        title: "Base Movement",
        body: "Drives the robot's mobile base in its local body frame. Forward = where the robot is facing. Works without MoveIt Session — commands go directly to Isaac Sim velocity controller.",
    },
    emergencyStop: {
        title: "Emergency Stop",
        body: "Immediately sends zero velocity to the mobile base and cancels any in-progress arm trajectory. Works without MoveIt Session for the base; arm stop requires an active MoveIt Session.",
    },
    moveitSession: {
        title: "MoveIt Session",
        body: "Starts/stops the MoveIt stack (bridge + proxy + move_group). Required for ALL arm, gripper, wrist, and macro commands. Base movement and Emergency Stop work without it.",
    },
    gripper: {
        title: "Gripper Control",
        body: "Opens or closes the robot's parallel-jaw gripper. Requires an active MoveIt Session. Open = fingers apart, Close = fingers together with grip force.",
    },
    armIncremental: {
        title: "Arm Incremental Control",
        body: "Moves individual arm joints by small steps (0.10–0.15 rad per click). Requires an active MoveIt Session. Torso raises/lowers the robot's torso lift. Wrist rotates the end-effector around its axis.",
    },
    wrist90: {
        title: "Wrist 90° Rotation",
        body: "Rotates the wrist (arm_7_joint) by exactly 90° (π/2 rad) in one step. Useful for reorienting the gripper. Requires an active MoveIt Session. Clamped to joint limits.",
    },
    armMacros: {
        title: "Arm Macros",
        body: "Predefined multi-step arm poses. Each macro moves through intermediate waypoints for smooth motion. Requires an active MoveIt Session.\n\n• Extend Fwd — arm straight forward\n• Extend Low — arm forward and down\n• Raise High — arm raised above\n• Home — tucked resting pose\n• Pre-Grasp — ready-to-grasp pose\n• Grasp Pose — final grasp position",
    },
    moveitActions: {
        title: "MoveIt Planning Actions",
        body: "High-level pick/place actions using MoveIt motion planning. Requires an active MoveIt Session. Plan Pick/Place use IK-based planning to reach target objects.",
    },
};

export default function EpisodeDetailPage() {
    const params = useParams();
    const id = params.id as string;

    const [episode, setEpisode] = useState<any>(null);
    const [config, setConfig] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [videos, setVideos] = useState<any[]>([]);
    const [teleopStatus, setTeleopStatus] = useState<any>(null);
    const [validation, setValidation] = useState<any>(null);
    const [streamState, setStreamState] = useState<"offline" | "connecting" | "live" | "reconnecting">("offline");
    const [streamLayout, setStreamLayout] = useState<"fit" | "fill">("fit");
    const [streamRefreshToken, setStreamRefreshToken] = useState(0);
    const [streamTransport, setStreamTransport] = useState<"webrtc" | "frame_fallback">("webrtc");
    const [frameTick, setFrameTick] = useState(0);
    const [deadmanPressed, setDeadmanPressed] = useState(false);
    const [pressedDirections, setPressedDirections] = useState<Record<string, boolean>>({});
    const teleopLoopRef = useRef<NodeJS.Timeout | null>(null);
    const [elapsedSec, setElapsedSec] = useState(0);

    const [confirmAction, setConfirmAction] = useState<string | null>(null);
    const [alertMessage, setAlertMessage] = useState<string | null>(null);
    const [helpDialog, setHelpDialog] = useState<{ title: string; body: string } | null>(null);

    const deadmanKey = "shift";
    const repeatMs = 140;

    const streamHintUrl =
        typeof config?.streamingHint === "string" && /^https?:\/\//i.test(config.streamingHint.trim())
            ? config.streamingHint.trim()
            : config?.isaacHost
                ? `http://${config.isaacHost}:8211/streaming/webrtc-demo/`
                : "";

    const fetchEpisodeAndConfig = async () => {
        try {
            const [epRes, cfgRes, vidRes] = await Promise.all([
                fetch(`/api/episodes/${id}`),
                fetch("/api/config"),
                fetch(`/api/episodes/${id}/videos`)
            ]);
            setEpisode(await epRes.json());
            setConfig(await cfgRes.json());
            const vids = await vidRes.json();
            if (Array.isArray(vids)) setVideos(vids);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchEpisodeAndConfig();
        const evtSource = new EventSource(`/api/events?episodeId=${id}`);
        evtSource.addEventListener("episode.status", (e) => {
            const data = JSON.parse(e.data);
            if (data.status) setEpisode((prev: any) => ({ ...prev, status: data.status }));
        });
        return () => evtSource.close();
    }, [id]);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        const pull = async () => {
            try {
                const [teleopRes, valRes] = await Promise.all([
                    fetch(`/api/episodes/${id}/teleop`),
                    fetch(`/api/episodes/${id}/validation`),
                ]);
                if (teleopRes.ok) setTeleopStatus(await teleopRes.json());
                if (valRes.ok) setValidation(await valRes.json());
            } catch { /* ignore */ }
        };
        pull();
        interval = setInterval(pull, 3000);
        return () => clearInterval(interval);
    }, [id]);

    useEffect(() => {
        const running = episode?.status === "running";
        if (!running) { setStreamState("offline"); setStreamTransport("webrtc"); return; }
        setStreamState((prev) => (prev === "live" ? prev : "connecting"));
        const timeout = setTimeout(() => setStreamState((prev) => (prev === "live" ? prev : "reconnecting")), 7000);
        return () => clearTimeout(timeout);
    }, [episode?.status, streamRefreshToken]);

    useEffect(() => { if (streamState === "reconnecting") setStreamTransport("frame_fallback"); }, [streamState]);

    useEffect(() => {
        if (episode?.status !== "running" || streamTransport !== "frame_fallback") return;
        const timer = setInterval(() => setFrameTick((v) => v + 1), 700);
        return () => clearInterval(timer);
    }, [episode?.status, streamTransport]);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        const isCurrentlyRunning = episode?.status === "running" || episode?.status === "stopping";
        const startTime = episode?.startedAt || episode?.createdAt;
        if (isCurrentlyRunning && startTime) {
            interval = setInterval(() => {
                setElapsedSec(Math.floor((Date.now() - new Date(startTime).getTime()) / 1000));
            }, 1000);
        } else { setElapsedSec(0); }
        return () => { if (interval) clearInterval(interval); };
    }, [episode?.status, episode?.startedAt, episode?.createdAt]);

    /* ─── keyboard teleop (WASD + deadman) ─── */
    useEffect(() => {
        if (episode?.status !== "running") { setPressedDirections({}); setDeadmanPressed(false); return; }
        const keyToCommand: Record<string, string> = { w: "move_forward", a: "move_left", s: "move_backward", d: "move_right" };
        const onKeyDown = (e: KeyboardEvent) => {
            const k = e.key.toLowerCase();
            if (k === deadmanKey) { setDeadmanPressed(true); return; }
            const cmd = keyToCommand[k];
            if (cmd) setPressedDirections((p) => ({ ...p, [cmd]: true }));
        };
        const onKeyUp = (e: KeyboardEvent) => {
            const k = e.key.toLowerCase();
            if (k === deadmanKey) { setDeadmanPressed(false); execCmd("stop_motion", { source: "keyboard_mouse", deadmanActive: true }); return; }
            const cmd = keyToCommand[k];
            if (cmd) setPressedDirections((p) => ({ ...p, [cmd]: false }));
        };
        const onBlur = () => { setDeadmanPressed(false); setPressedDirections({}); execCmd("stop_motion", { source: "keyboard_mouse", deadmanActive: true }); };
        window.addEventListener("keydown", onKeyDown);
        window.addEventListener("keyup", onKeyUp);
        window.addEventListener("blur", onBlur);
        return () => { window.removeEventListener("keydown", onKeyDown); window.removeEventListener("keyup", onKeyUp); window.removeEventListener("blur", onBlur); };
    }, [episode?.status]);

    useEffect(() => {
        if (teleopLoopRef.current) { clearInterval(teleopLoopRef.current); teleopLoopRef.current = null; }
        if (episode?.status !== "running" || !deadmanPressed) return;
        const active = Object.entries(pressedDirections).find(([, v]) => v)?.[0];
        if (!active) return;
        teleopLoopRef.current = setInterval(() => execCmd(active, { source: "keyboard_mouse", deadmanActive: true }), repeatMs);
        return () => { if (teleopLoopRef.current) { clearInterval(teleopLoopRef.current); teleopLoopRef.current = null; } };
    }, [pressedDirections, deadmanPressed, episode?.status]);

    /* ─── actions ─── */
    const IMMEDIATE_ACTIONS = [
        "move_forward", "move_backward", "move_left", "move_right", "rotate_left", "rotate_right", "stop_motion",
        "grasp_mug", "go_home", "start_vr_session", "stop_vr_session",
        "start_moveit_session", "stop_moveit_session",
        "moveit_plan_pick", "moveit_plan_place", "moveit_plan_pick_sink", "moveit_plan_pick_fridge", "moveit_go_home",
        "open_gripper", "close_gripper", "torso_up", "torso_down",
        "arm_up", "arm_down", "arm_forward", "arm_back",
        "wrist_cw", "wrist_ccw", "wrist_90_cw", "wrist_90_ccw",
        "moveit_approach_workzone", "moveit_open_close_fridge", "moveit_open_close_dishwasher",
        "arm_extend", "arm_extend_low", "arm_raise_high", "arm_home", "pre_grasp", "grasp_pose",
    ];

    const handleAction = (action: string) => {
        if (IMMEDIATE_ACTIONS.includes(action)) { execCmd(action); return; }
        setConfirmAction(action);
    };

    const execCmd = async (action: string, opts?: { source?: string; deadmanActive?: boolean; replayFrame?: any }) => {
        try {
            const res = await fetch(`/api/episodes/${id}/teleop`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ command: action, source: opts?.source || "ui_button", deadmanActive: opts?.deadmanActive ?? false, replayFrame: opts?.replayFrame }),
            });
            if (!res.ok) { const d = await res.json().catch(() => ({})); setAlertMessage(d.error || `Command ${action} failed.`); }
        } catch { setAlertMessage("Failed to send teleop command."); }
    };

    const executeAction = async () => {
        if (!confirmAction) return;
        const action = confirmAction;
        setConfirmAction(null);
        try {
            const res = await fetch(`/api/episodes/${id}/${action}`, { method: "POST" });
            if (!res.ok) { const d = await res.json().catch(() => ({})); setAlertMessage(d.error || `Action failed with status ${res.status}`); return; }
            setTimeout(() => fetchEpisodeAndConfig(), 500);
        } catch { setAlertMessage("Failed to perform action due to a network error."); }
    };

    const downloadMetadata = () => {
        const a = document.createElement("a");
        a.href = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(episode, null, 2));
        a.download = `episode-${id}-metadata.json`;
        document.body.appendChild(a); a.click(); a.remove();
    };

    const getStatusBadge = (status: string) => {
        const map: Record<string, JSX.Element> = {
            created: <Badge variant="secondary">Created</Badge>,
            running: <Badge className="bg-blue-600">Running</Badge>,
            stopping: <Badge className="bg-orange-500">Stopping</Badge>,
            stopped: <Badge variant="outline">Stopped</Badge>,
            completed: <Badge className="bg-green-600">Completed</Badge>,
            failed: <Badge variant="destructive">Failed</Badge>,
        };
        return map[status] || <Badge variant="outline">{status}</Badge>;
    };

    /* ─── helper: section header with ? button ─── */
    const SectionHead = ({ label, help }: { label: string; help?: { title: string; body: string } }) => (
        <div className="flex items-center gap-1.5 mb-1.5">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{label}</span>
            {help && (
                <button type="button" onClick={() => setHelpDialog(help)} className="text-muted-foreground hover:text-foreground">
                    <HelpCircle className="w-3.5 h-3.5" />
                </button>
            )}
        </div>
    );

    /* ─── helper: teleop button ─── */
    const TBtn = ({ cmd, label, variant = "outline", className = "", disabled = false }: { cmd: string; label: string; variant?: "outline" | "secondary" | "destructive" | "default"; className?: string; disabled?: boolean }) => (
        <Button onClick={() => handleAction(cmd)} variant={variant} size="sm" className={`w-full text-xs h-8 ${className}`} disabled={disabled}>{label}</Button>
    );

    if (loading) return <div className="p-8 text-center">Loading...</div>;
    if (!episode) return <div className="p-8 text-center text-red-500">Episode not found</div>;

    const isRunning = episode.status === "running";
    const canStart = ["created", "stopped", "failed"].includes(episode.status);
    const isCurrentlyRunning = episode?.status === "running" || episode?.status === "stopping";
    const hasMoveIt = !!episode?.launchProfile?.enableMoveIt;
    const hasTeleop = !!episode?.launchProfile?.enableGuiMode || hasMoveIt || !!episode?.launchProfile?.enableWebRTC || !!episode?.launchProfile?.enableVrTeleop;
    const moveitActive = !!teleopStatus?.moveitSessionActive;

    return (
        <div className="p-8 max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-5 gap-6">

            {/* ─── LEFT COLUMN ─── */}
            <div className="lg:col-span-2 space-y-4">
                {/* Actions */}
                <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-sm">Actions</CardTitle></CardHeader>
                    <CardContent className="space-y-3">
                        <div className="flex items-center justify-between">
                            <span className="text-sm font-medium">Status</span>
                            {getStatusBadge(episode.status)}
                        </div>
                        {canStart && (
                            <Button onClick={() => handleAction("start")} variant="secondary" className="w-full h-11 text-base !bg-blue-600 !text-white hover:!bg-blue-700 font-bold">
                                <Play className="w-5 h-5 mr-2" /> Start Episode
                            </Button>
                        )}
                        <div className="grid grid-cols-2 gap-2">
                            <Button onClick={() => handleAction("stop")} disabled={!isRunning && episode.status !== "stopping"} variant="destructive" className="w-full">
                                <Square className="w-4 h-4 mr-1" /> Stop
                            </Button>
                            <Button onClick={() => handleAction("mark-completed")} disabled={isCurrentlyRunning} variant="outline" className="w-full text-green-600">
                                <CheckCircle className="w-4 h-4 mr-1" /> Complete
                            </Button>
                            <Button onClick={() => handleAction("mark-failed")} disabled={isCurrentlyRunning} variant="outline" className="w-full text-red-600">
                                <XCircle className="w-4 h-4 mr-1" /> Failed
                            </Button>
                            <Button onClick={downloadMetadata} variant="secondary" className="w-full">
                                <Download className="w-4 h-4 mr-1" /> Metadata
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                {/* Progress */}
                {isCurrentlyRunning && (
                    <Card className="border-blue-200">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm flex items-center justify-between">
                                <span>Progress</span>
                                <span className="font-mono text-xs">{Math.min(elapsedSec, episode.durationSec)}s / {episode.durationSec}s</span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <Progress value={Math.min((elapsedSec / episode.durationSec) * 100, 100)} className="h-2" />
                        </CardContent>
                    </Card>
                )}

                {/* Episode Details */}
                <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-sm">Episode Details</CardTitle></CardHeader>
                    <CardContent className="text-sm space-y-1.5">
                        <div className="flex justify-between"><span className="text-muted-foreground">ID:</span><span className="font-mono text-xs truncate max-w-[150px]" title={episode.id}>{episode.id}</span></div>
                        <div className="flex items-center justify-between"><span className="flex items-center text-muted-foreground">Scene <HelpTooltip content="The loaded USD stage environment." />:</span><span className="font-medium">{episode.scene?.name}</span></div>
                        <div className="flex items-center justify-between"><span className="flex items-center text-muted-foreground">Object Set <HelpTooltip content="The collection of items spawned into the environment." />:</span><span>{episode.objectSet?.name || "None"}</span></div>
                        <div className="flex items-center justify-between"><span className="flex items-center text-muted-foreground">Seed <HelpTooltip content="RNG seed for determinism." />:</span><span>{episode.seed}</span></div>
                        <div className="flex items-center justify-between"><span className="flex items-center text-muted-foreground">Output Dir <HelpTooltip content="Where logs/videos will be saved." />:</span><span className="font-mono text-xs truncate max-w-[120px]" title={episode.outputDir || "Pending"}>{episode.outputDir || "Pending"}</span></div>
                    </CardContent>
                </Card>

                {/* ─── Teleop Control Panel ─── */}
                {hasTeleop && (
                    <Card className="border-purple-200 dark:border-purple-900">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm flex items-center text-purple-700 dark:text-purple-400">
                                <Info className="w-4 h-4 mr-2" /> Teleop Control
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3">

                            {/* Base Movement */}
                            <SectionHead label="Base Movement" help={HELP.baseMovement} />
                            <div className="grid grid-cols-3 gap-1.5">
                                <TBtn cmd="rotate_left" label="↺ Rot L" />
                                <TBtn cmd="move_forward" label="↑ Forward" variant="secondary" className="!bg-purple-600 !text-white hover:!bg-purple-700" />
                                <TBtn cmd="rotate_right" label="↻ Rot R" />
                                <TBtn cmd="move_left" label="← Left" />
                                <TBtn cmd="move_backward" label="↓ Back" />
                                <TBtn cmd="move_right" label="→ Right" />
                            </div>
                            <TBtn cmd="stop_motion" label="Emergency Stop" variant="destructive" className="mt-1" />
                            <p className="text-[10px] text-muted-foreground">Keyboard: hold Shift + WASD. Release Shift = stop.</p>

                            {/* MoveIt Session */}
                            {hasMoveIt && (
                                <>
                                    <div className="border-t pt-3 mt-3" />
                                    <SectionHead label="MoveIt Session" help={HELP.moveitSession} />
                                    <div className="grid grid-cols-2 gap-1.5">
                                        <TBtn cmd="start_moveit_session" label="Start MoveIt" variant="secondary" disabled={moveitActive} />
                                        <TBtn cmd="stop_moveit_session" label="Stop MoveIt" disabled={!moveitActive} />
                                    </div>
                                    {moveitActive && <p className="text-[10px] text-green-600 font-medium">MoveIt session active</p>}
                                    {!moveitActive && <p className="text-[10px] text-amber-600">Start MoveIt to enable arm/gripper controls below</p>}
                                </>
                            )}

                            {/* Gripper */}
                            {hasMoveIt && (
                                <>
                                    <div className="border-t pt-3 mt-1" />
                                    <SectionHead label="Gripper" help={HELP.gripper} />
                                    <div className="grid grid-cols-2 gap-1.5">
                                        <TBtn cmd="open_gripper" label="Open" className="border-green-400 text-green-600 hover:bg-green-50" />
                                        <TBtn cmd="close_gripper" label="Close" className="border-red-400 text-red-600 hover:bg-red-50" />
                                    </div>
                                </>
                            )}

                            {/* Arm Incremental */}
                            {hasMoveIt && (
                                <>
                                    <div className="border-t pt-3 mt-1" />
                                    <SectionHead label="Arm (incremental)" help={HELP.armIncremental} />
                                    <div className="grid grid-cols-3 gap-1.5">
                                        <TBtn cmd="arm_forward" label="Arm Fwd" />
                                        <TBtn cmd="torso_up" label="Torso ↑" />
                                        <TBtn cmd="arm_up" label="Arm ↑" />
                                        <TBtn cmd="arm_back" label="Arm Back" />
                                        <TBtn cmd="torso_down" label="Torso ↓" />
                                        <TBtn cmd="arm_down" label="Arm ↓" />
                                        <TBtn cmd="wrist_cw" label="Wrist ↻" />
                                        <TBtn cmd="moveit_approach_workzone" label="Workzone" variant="secondary" />
                                        <TBtn cmd="wrist_ccw" label="Wrist ↺" />
                                    </div>
                                </>
                            )}

                            {/* Wrist 90° */}
                            {hasMoveIt && (
                                <>
                                    <SectionHead label="Wrist 90°" help={HELP.wrist90} />
                                    <div className="grid grid-cols-2 gap-1.5">
                                        <TBtn cmd="wrist_90_cw" label="90° ↻" variant="secondary" />
                                        <TBtn cmd="wrist_90_ccw" label="90° ↺" variant="secondary" />
                                    </div>
                                </>
                            )}

                            {/* Arm Macros */}
                            {hasMoveIt && (
                                <>
                                    <div className="border-t pt-3 mt-1" />
                                    <SectionHead label="Arm Macros" help={HELP.armMacros} />
                                    <div className="grid grid-cols-3 gap-1.5">
                                        <TBtn cmd="arm_extend" label="Extend Fwd" variant="secondary" />
                                        <TBtn cmd="arm_extend_low" label="Extend Low" variant="secondary" />
                                        <TBtn cmd="arm_raise_high" label="Raise High" variant="secondary" />
                                        <TBtn cmd="arm_home" label="Home" />
                                        <TBtn cmd="pre_grasp" label="Pre-Grasp" variant="secondary" />
                                        <TBtn cmd="grasp_pose" label="Grasp Pose" variant="secondary" />
                                    </div>
                                </>
                            )}

                            {/* MoveIt Planning Actions */}
                            {hasMoveIt && (
                                <>
                                    <div className="border-t pt-3 mt-1" />
                                    <SectionHead label="MoveIt Actions" help={HELP.moveitActions} />
                                    <div className="grid grid-cols-2 gap-1.5">
                                        <TBtn cmd="moveit_plan_pick" label="Plan Pick" variant="secondary" />
                                        <TBtn cmd="moveit_plan_place" label="Plan Place" variant="secondary" />
                                        <TBtn cmd="moveit_plan_pick_sink" label="Pick Sink" variant="secondary" />
                                        <TBtn cmd="moveit_plan_pick_fridge" label="Pick Fridge" variant="secondary" />
                                        <TBtn cmd="moveit_go_home" label="MoveIt Home" />
                                    </div>
                                </>
                            )}

                            {/* Status footer */}
                            {(teleopStatus?.vrEnabled || teleopStatus?.moveitEnabled) && (
                                <div className="border-t pt-2 mt-2 text-[10px] text-muted-foreground space-y-0.5">
                                    <div>MoveIt: {moveitActive ? <span className="text-green-600 font-medium">active</span> : "inactive"} | ROS2: {teleopStatus?.ros2Available ? "ok" : "—"}</div>
                                    {teleopStatus?.lastCommand && <div>Last: {teleopStatus.lastCommand}</div>}
                                    {teleopStatus?.lastError && <div className="text-red-500">Error: {teleopStatus.lastError}</div>}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                )}
            </div>

            {/* ─── RIGHT COLUMN ─── */}
            <div className="lg:col-span-3 space-y-6">
                {/* WebRTC Stream */}
                {config?.streamingMode === "browser_embedded_optional" && (
                    <Card className="h-[400px] flex flex-col overflow-hidden">
                        <CardHeader className="pb-2 space-y-2">
                            <CardTitle className="flex items-center text-sm justify-between">
                                <span>Live Stream</span>
                                <span className="text-xs font-normal">State: {streamState}</span>
                            </CardTitle>
                            <div className="flex gap-2">
                                <Button size="sm" variant="outline" onClick={() => setStreamLayout((p) => (p === "fit" ? "fill" : "fit"))}>Layout: {streamLayout}</Button>
                                <Button size="sm" variant="outline" onClick={() => { setStreamTransport("webrtc"); setStreamRefreshToken((p) => p + 1); }}><RefreshCcw className="w-4 h-4 mr-1" /> Reconnect</Button>
                                <Button size="sm" variant="outline" onClick={() => setStreamTransport((p) => (p === "webrtc" ? "frame_fallback" : "webrtc"))}>Transport: {streamTransport === "webrtc" ? "WebRTC" : "Frame"}</Button>
                                {config?.isaacHost && <Button size="sm" variant="outline" asChild><a href={streamHintUrl} target="_blank" rel="noreferrer">Open tab</a></Button>}
                            </div>
                        </CardHeader>
                        <CardContent className="flex-1 p-0 bg-black">
                            {isRunning ? (
                                streamTransport === "webrtc" ? (
                                    <iframe key={streamRefreshToken} src={streamHintUrl} className={`w-full h-full border-0 ${streamLayout === "fill" ? "object-cover" : "object-contain"}`} sandbox="allow-scripts allow-same-origin" title="Isaac WebRTC Stream" onLoad={() => setStreamState((p) => (p === "offline" ? "offline" : "connecting"))} onError={() => { setStreamState("reconnecting"); setStreamTransport("frame_fallback"); }} />
                                ) : (
                                    <img src={`/api/episodes/${id}/stream/frame?refresh=${streamRefreshToken}&tick=${frameTick}`} alt="Live frame stream" className={`w-full h-full ${streamLayout === "fill" ? "object-cover" : "object-contain"}`} onLoad={() => setStreamState("live")} onError={() => setStreamState("reconnecting")} />
                                )
                            ) : (
                                <div className="h-full w-full flex items-center justify-center text-muted-foreground text-sm">Start episode to connect stream.</div>
                            )}
                        </CardContent>
                    </Card>
                )}

                <VideoPlayerCard videos={videos} />

                {/* Dataset Validation */}
                <Card>
                    <CardHeader className="pb-2"><CardTitle className="text-sm">Dataset Validation</CardTitle></CardHeader>
                    <CardContent className="text-xs space-y-1">
                        <div>valid: {String(!!validation?.valid)}</div>
                        <div>required outputs: {(validation?.requiredOutputs || []).join(", ") || "n/a"}</div>
                        {(validation?.missingFiles || []).length > 0 && <div className="text-red-500">missing: {validation.missingFiles.join(", ")}</div>}
                        {(validation?.issues || []).length > 0 && <div className="text-red-500">issues: {validation.issues.join(" | ")}</div>}
                        {validation?.summary && <div>summary: {validation.summary}</div>}
                    </CardContent>
                </Card>

                {/* Real Data Analysis */}
                {episode.status === "completed" && (
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between">
                            <CardTitle className="text-sm">Real Data Analysis</CardTitle>
                            <Button size="sm" onClick={() => handleAction("sync")} disabled={loading}><Download className="w-4 h-4 mr-2" /> Sync Data</Button>
                        </CardHeader>
                        <CardContent>
                            <div className="text-xs text-muted-foreground mb-4">Click 'Sync Data' to fetch artifact files from the remote simulation host.</div>
                            {videos.filter(v => v.name.endsWith('.json')).length > 0 ? (
                                videos.filter(v => v.name.endsWith('.json')).map(file => (
                                    <Button key={file.name} variant="outline" size="sm" asChild className="w-full mb-2">
                                        <a href={file.downloadUrl || file.playUrl} download={file.name}><Download className="w-4 h-4 mr-2" /> Download {file.name}</a>
                                    </Button>
                                ))
                            ) : (
                                <Button variant="outline" size="sm" className="w-full" disabled><Download className="w-4 h-4 mr-2" /> No Data Files Found</Button>
                            )}
                        </CardContent>
                    </Card>
                )}

                {/* Tasks & Sensors */}
                <Card>
                    <CardHeader><CardTitle className="text-sm">Recording Sensors</CardTitle></CardHeader>
                    <CardContent>
                        <div className="flex flex-wrap gap-2">
                            {(() => { try { const s = JSON.parse(episode.sensors); return s.length === 0 ? <span className="text-muted-foreground text-sm">No sensors specified</span> : s.map((x: string) => <Badge key={x} variant="outline">{x}</Badge>); } catch { return <span>Error parsing sensors</span>; } })()}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* ─── Dialogs ─── */}
            <AlertDialog open={!!confirmAction} onOpenChange={(o) => !o && setConfirmAction(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Confirm Action</AlertDialogTitle>
                        <AlertDialogDescription>Are you sure you want to {confirmAction} this episode?</AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={executeAction}>Continue</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            <AlertDialog open={!!alertMessage} onOpenChange={(o) => !o && setAlertMessage(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Error</AlertDialogTitle>
                        <AlertDialogDescription className="text-red-500 font-medium whitespace-pre-wrap">{alertMessage}</AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogAction onClick={() => setAlertMessage(null)}>OK</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            <Dialog open={!!helpDialog} onOpenChange={(o) => !o && setHelpDialog(null)}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>{helpDialog?.title}</DialogTitle>
                        <DialogDescription className="whitespace-pre-line pt-2">{helpDialog?.body}</DialogDescription>
                    </DialogHeader>
                    <DialogFooter showCloseButton />
                </DialogContent>
            </Dialog>
        </div>
    );
}

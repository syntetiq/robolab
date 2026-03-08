"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Play, Square, CheckCircle, XCircle, Terminal, Download, Info, RefreshCcw } from "lucide-react";
import { format } from "date-fns";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { HelpTooltip } from "@/components/HelpTooltip";
import { VideoPlayerCard } from "@/components/episodes/VideoPlayerCard";
import { Input } from "@/components/ui/input";
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

export default function EpisodeDetailPage() {
    const params = useParams();
    const id = params.id as string;

    const [episode, setEpisode] = useState<any>(null);
    const [config, setConfig] = useState<any>(null);
    const [logs, setLogs] = useState<string[]>([]);
    const [loading, setLoading] = useState(true);
    const [videos, setVideos] = useState<any[]>([]);
    const [teleopStatus, setTeleopStatus] = useState<any>(null);
    const [orchestrationStatus, setOrchestrationStatus] = useState<any>(null);
    const [validation, setValidation] = useState<any>(null);
    const [teleopProfile, setTeleopProfile] = useState<any>({
        name: "default",
        repeatMs: 140,
        deadmanKey: "Shift",
    });
    const [streamState, setStreamState] = useState<"offline" | "connecting" | "live" | "reconnecting">("offline");
    const [streamLayout, setStreamLayout] = useState<"fit" | "fill">("fit");
    const [streamRefreshToken, setStreamRefreshToken] = useState(0);
    const [streamTransport, setStreamTransport] = useState<"webrtc" | "frame_fallback">("webrtc");
    const [frameTick, setFrameTick] = useState(0);
    const [deadmanPressed, setDeadmanPressed] = useState(false);
    const [pressedDirections, setPressedDirections] = useState<Record<string, boolean>>({});
    const scrollRef = useRef<HTMLDivElement>(null);
    const teleopLoopRef = useRef<NodeJS.Timeout | null>(null);
    const [elapsedSec, setElapsedSec] = useState(0);

    const [confirmAction, setConfirmAction] = useState<string | null>(null);
    const [alertMessage, setAlertMessage] = useState<string | null>(null);
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

        // Setup SSE
        const evtSource = new EventSource(`/api/events?episodeId=${id}`);
        evtSource.addEventListener("episode.status", (e) => {
            const data = JSON.parse(e.data);
            if (data.status) {
                setEpisode((prev: any) => ({ ...prev, status: data.status }));
            }
        });
        evtSource.addEventListener("episode.log", (e) => {
            const data = JSON.parse(e.data);
            if (data.message) {
                setLogs(prev => [...prev, data.message]);
                setTimeout(() => {
                    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
                }, 100);
            }
        });

        return () => evtSource.close();
    }, [id]);

    useEffect(() => {
        try {
            const raw = localStorage.getItem("robolab.teleopProfile");
            if (raw) {
                const parsed = JSON.parse(raw);
                setTeleopProfile((prev: any) => ({ ...prev, ...parsed }));
            }
        } catch {
            // ignore
        }
    }, []);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        const pullTeleopStatus = async () => {
            try {
                const [teleopRes, orchRes, valRes] = await Promise.all([
                    fetch(`/api/episodes/${id}/teleop`),
                    fetch(`/api/episodes/${id}/orchestration`),
                    fetch(`/api/episodes/${id}/validation`),
                ]);
                if (teleopRes.ok) setTeleopStatus(await teleopRes.json());
                if (orchRes.ok) setOrchestrationStatus(await orchRes.json());
                if (valRes.ok) setValidation(await valRes.json());
            } catch {
                // ignore transient polling errors
            }
        };
        pullTeleopStatus();
        interval = setInterval(pullTeleopStatus, 3000);
        return () => clearInterval(interval);
    }, [id]);

    useEffect(() => {
        const running = episode?.status === "running";
        if (!running) {
            setStreamState("offline");
            setStreamTransport("webrtc");
            return;
        }
        setStreamState((prev) => (prev === "live" ? prev : "connecting"));
        const timeout = setTimeout(() => {
            // iframe load events are unreliable for WebRTC readiness; hard-fallback
            // to frame transport if we don't have explicit frame/live confirmation.
            setStreamState((prev) => (prev === "live" ? prev : "reconnecting"));
        }, 7000);
        return () => clearTimeout(timeout);
    }, [episode?.status, streamRefreshToken]);

    useEffect(() => {
        if (streamState === "reconnecting") {
            setStreamTransport("frame_fallback");
        }
    }, [streamState]);

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
                const start = new Date(startTime).getTime();
                const now = new Date().getTime();
                setElapsedSec(Math.floor((now - start) / 1000));
            }, 1000);
        } else {
            setElapsedSec(0);
        }
        return () => {
            if (interval) clearInterval(interval);
        };
    }, [episode?.status, episode?.startedAt, episode?.createdAt]);

    useEffect(() => {
        if (episode?.status !== "running") {
            setPressedDirections({});
            setDeadmanPressed(false);
            return;
        }

        const keyToCommand: Record<string, string> = {
            w: "move_forward",
            a: "move_left",
            s: "move_backward",
            d: "move_right",
        };
        const deadmanKey = String(teleopProfile.deadmanKey || "Shift").toLowerCase();

        const onKeyDown = (event: KeyboardEvent) => {
            const key = event.key.toLowerCase();
            if (key === deadmanKey) {
                setDeadmanPressed(true);
                return;
            }
            const cmd = keyToCommand[key];
            if (cmd) {
                setPressedDirections((prev) => ({ ...prev, [cmd]: true }));
            }
        };
        const onKeyUp = (event: KeyboardEvent) => {
            const key = event.key.toLowerCase();
            if (key === deadmanKey) {
                setDeadmanPressed(false);
                executeImmediateAction("stop_motion", { source: "keyboard_mouse", deadmanActive: true });
                return;
            }
            const cmd = keyToCommand[key];
            if (cmd) {
                setPressedDirections((prev) => ({ ...prev, [cmd]: false }));
            }
        };
        const onBlur = () => {
            setDeadmanPressed(false);
            setPressedDirections({});
            executeImmediateAction("stop_motion", { source: "keyboard_mouse", deadmanActive: true });
        };

        window.addEventListener("keydown", onKeyDown);
        window.addEventListener("keyup", onKeyUp);
        window.addEventListener("blur", onBlur);
        return () => {
            window.removeEventListener("keydown", onKeyDown);
            window.removeEventListener("keyup", onKeyUp);
            window.removeEventListener("blur", onBlur);
        };
    }, [episode?.status, teleopProfile.deadmanKey]);

    useEffect(() => {
        if (teleopLoopRef.current) {
            clearInterval(teleopLoopRef.current);
            teleopLoopRef.current = null;
        }
        if (episode?.status !== "running" || !deadmanPressed) return;

        const active = Object.entries(pressedDirections).find(([, isPressed]) => isPressed)?.[0];
        if (!active) return;
        const repeatMs = Math.max(60, Number(teleopProfile.repeatMs || 140));
        teleopLoopRef.current = setInterval(() => {
            executeImmediateAction(active, { source: "keyboard_mouse", deadmanActive: true });
        }, repeatMs);

        return () => {
            if (teleopLoopRef.current) {
                clearInterval(teleopLoopRef.current);
                teleopLoopRef.current = null;
            }
        };
    }, [pressedDirections, deadmanPressed, teleopProfile.repeatMs, episode?.status]);

    const handleAction = (action: string) => {
        // Direct execution for teleop commands to avoid the confirmation dialog popup
        if ([
            "move_forward",
            "move_backward",
            "move_left",
            "move_right",
            "stop_motion",
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
        ].includes(action)) {
            executeImmediateAction(action);
            return;
        }
        setConfirmAction(action);
    };

    const executeImmediateAction = async (action: string, options?: { source?: string; deadmanActive?: boolean; replayFrame?: any }) => {
        try {
            const res = await fetch(`/api/episodes/${id}/teleop`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    command: action,
                    source: options?.source || "ui_button",
                    deadmanActive: options?.deadmanActive ?? false,
                    replayFrame: options?.replayFrame,
                })
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setAlertMessage(data.error || `Command ${action} failed.`);
            }
        } catch (e) {
            setAlertMessage("Failed to send teleop command.");
        }
    };

    const startDeterministicRun = async () => {
        try {
            const res = await fetch(`/api/episodes/${id}/orchestration`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    durationSec: Math.max(20, Number(episode.durationSec || 30)),
                    requireRealTiago: true,
                    intent: "plan_pick_sink",
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                setAlertMessage(data.error || "Failed to start orchestration.");
                return;
            }
            setOrchestrationStatus(data);
        } catch {
            setAlertMessage("Failed to start deterministic orchestration.");
        }
    };

    const executeAction = async () => {
        if (!confirmAction) return;
        const action = confirmAction;
        setConfirmAction(null);
        try {
            const res = await fetch(`/api/episodes/${id}/${action}`, { method: "POST" });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setAlertMessage(data.error || `Action failed with status ${res.status}`);
                return;
            }
            // Small delay to let filesystem writes (like dummy video) complete before refetching
            setTimeout(() => {
                fetchEpisodeAndConfig();
            }, 500);
        } catch (e) {
            setAlertMessage("Failed to perform action due to a network error.");
        }
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "created": return <Badge variant="secondary">Created</Badge>;
            case "running": return <Badge className="bg-blue-600">Running</Badge>;
            case "stopping": return <Badge className="bg-orange-500">Stopping</Badge>;
            case "stopped": return <Badge variant="outline">Stopped</Badge>;
            case "completed": return <Badge className="bg-green-600">Completed</Badge>;
            case "failed": return <Badge variant="destructive">Failed</Badge>;
            default: return <Badge variant="outline">{status}</Badge>;
        }
    };

    const downloadMetadata = () => {
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(episode, null, 2));
        const downloadAnchorNode = document.createElement("a");
        downloadAnchorNode.setAttribute("href", dataStr);
        downloadAnchorNode.setAttribute("download", `episode-${id}-metadata.json`);
        document.body.appendChild(downloadAnchorNode);
        downloadAnchorNode.click();
        downloadAnchorNode.remove();
    };

    const updateTeleopProfile = (patch: any) => {
        setTeleopProfile((prev: any) => {
            const next = { ...prev, ...patch };
            try {
                localStorage.setItem("robolab.teleopProfile", JSON.stringify(next));
            } catch {
                // ignore
            }
            return next;
        });
    };

    if (loading) return <div className="p-8 text-center">Loading...</div>;
    if (!episode) return <div className="p-8 text-center text-red-500">Episode not found</div>;

    const isRunning = episode.status === "running";
    const canStart = ["created", "stopped", "failed"].includes(episode.status);

    const isCurrentlyRunning = episode?.status === "running" || episode?.status === "stopping";

    return (
        <div className="p-8 max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6">

            {/* LEFT COLUMN: Controls & Info */}
            <div className="md:col-span-1 space-y-6">
                <Card>
                    <CardHeader>
                        <CardTitle>Actions</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex items-center justify-between mb-4">
                            <span className="text-sm font-medium">Status</span>
                            {getStatusBadge(episode.status)}
                        </div>

                        <div className="grid grid-cols-2 gap-2">
                            <Button onClick={() => handleAction("start")} disabled={!canStart} className="w-full bg-blue-600 hover:bg-blue-700">
                                <Play className="w-4 h-4 mr-2" /> Start
                            </Button>
                            <Button onClick={() => handleAction("stop")} disabled={!isRunning && episode.status !== "stopping"} variant="destructive" className="w-full">
                                <Square className="w-4 h-4 mr-2" /> Stop
                            </Button>
                            <Button onClick={() => handleAction("mark-completed")} disabled={isCurrentlyRunning} variant="outline" className="w-full text-green-600">
                                <CheckCircle className="w-4 h-4 mr-2" /> Complete
                            </Button>
                            <Button onClick={() => handleAction("mark-failed")} disabled={isCurrentlyRunning} variant="outline" className="w-full text-red-600">
                                <XCircle className="w-4 h-4 mr-2" /> Failed
                            </Button>
                        </div>

                        <Button onClick={downloadMetadata} variant="secondary" className="w-full mt-4">
                            <Download className="w-4 h-4 mr-2" /> Download metadata.json
                        </Button>
                    </CardContent>
                </Card>

                <Card className="border-sky-200">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm">Deterministic MoveIt Orchestration</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                        <Button onClick={startDeterministicRun} className="w-full" disabled={orchestrationStatus?.status === "running"}>
                            Start Deterministic Run
                        </Button>
                        <div className="rounded border p-2 text-xs">
                            <div>Status: {orchestrationStatus?.status || "idle"}</div>
                            <div>Stage: {orchestrationStatus?.stage || "idle"}</div>
                            <div>ready: {String(!!orchestrationStatus?.ready)}</div>
                            <div>intent_sent: {String(!!orchestrationStatus?.intentSent)}</div>
                            <div>result_received: {String(!!orchestrationStatus?.resultReceived)}</div>
                            {orchestrationStatus?.failedReason && <div className="text-red-500">failed_reason: {orchestrationStatus.failedReason}</div>}
                        </div>
                    </CardContent>
                </Card>

                {isCurrentlyRunning && (
                    <Card className="border-blue-200 shadow-sm">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm flex items-center justify-between">
                                <span>Execution Progress</span>
                                <span className="font-mono">{Math.min(elapsedSec, episode.durationSec)}s / {episode.durationSec}s</span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <Progress value={Math.min((elapsedSec / episode.durationSec) * 100, 100)} className="h-2" />
                            {elapsedSec >= episode.durationSec && (
                                <p className="text-xs text-muted-foreground mt-2 italic">Waiting for finalization...</p>
                            )}
                        </CardContent>
                    </Card>
                )}

                <Card>
                    <CardHeader>
                        <CardTitle>Episode Details</CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm space-y-2">
                        <div className="flex justify-between">
                            <span className="text-muted-foreground">ID:</span>
                            <span className="font-mono text-xs truncate max-w-[150px]" title={episode.id}>{episode.id}</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="flex items-center text-muted-foreground">Scene <HelpTooltip content="The loaded USD stage environment." />:</span>
                            <span className="font-medium">{episode.scene?.name}</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="flex items-center text-muted-foreground">Object Set <HelpTooltip content="The collection of items spawned into the environment." />:</span>
                            <span>{episode.objectSet?.name || "None"}</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="flex items-center text-muted-foreground">Seed <HelpTooltip content="RNG seed for determinism." />:</span>
                            <span>{episode.seed}</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="flex items-center text-muted-foreground">Output Dir <HelpTooltip content="Where logs/videos will be saved on the remote target." />:</span>
                            <span className="font-mono text-xs truncate max-w-[120px]" title={episode.outputDir || "Pending"}>{episode.outputDir || "Pending"}</span>
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm">Keyboard/Mouse Teleop Profile</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        <div className="text-xs text-muted-foreground">Hold deadman + WASD. Motion stops on window blur and deadman release.</div>
                        <div className="grid grid-cols-2 gap-2">
                            <Input
                                value={teleopProfile.deadmanKey}
                                onChange={(e) => updateTeleopProfile({ deadmanKey: e.target.value || "Shift" })}
                                placeholder="Deadman key (Shift)"
                            />
                            <Input
                                type="number"
                                value={teleopProfile.repeatMs}
                                onChange={(e) => updateTeleopProfile({ repeatMs: Number(e.target.value || 140) })}
                                placeholder="Repeat ms"
                            />
                        </div>
                        <div className="text-xs">
                            deadman: <b>{deadmanPressed ? "pressed" : "released"}</b> | active command: {Object.entries(pressedDirections).find(([, active]) => active)?.[0] || "none"}
                        </div>
                    </CardContent>
                </Card>

                {(episode?.launchProfile?.enableVrTeleop || episode?.launchProfile?.enableMoveIt || episode?.launchProfile?.enableWebRTC) && (
                    <Card className="bg-purple-50/50 border-purple-200 dark:bg-purple-950/20 dark:border-purple-900">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm flex items-center text-purple-700 dark:text-purple-400">
                                <Info className="w-4 h-4 mr-2" /> Teleoperation Control Panel
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="text-xs text-purple-800 dark:text-purple-300 space-y-2">
                            <p>Use these commands to drive teleop, VR session lifecycle, and MoveIt-assisted actions.</p>

                            {episode?.launchProfile?.enableVrTeleop && (
                                <div className="grid grid-cols-2 gap-2 mt-2">
                                    <Button
                                        onClick={() => handleAction("start_vr_session")}
                                        variant="secondary"
                                        size="sm"
                                        className="w-full text-xs h-7"
                                        disabled={!!teleopStatus?.vrSessionActive}
                                    >
                                        Start VR Session
                                    </Button>
                                    <Button
                                        onClick={() => handleAction("stop_vr_session")}
                                        variant="outline"
                                        size="sm"
                                        className="w-full text-xs h-7"
                                        disabled={!teleopStatus?.vrSessionActive}
                                    >
                                        Stop VR Session
                                    </Button>
                                </div>
                            )}

                            <div className="grid grid-cols-3 gap-2 mt-3">
                                <Button onClick={() => handleAction("move_left")} variant="outline" size="sm" className="w-full text-xs h-7">Left</Button>
                                <Button onClick={() => handleAction("move_forward")} variant="default" size="sm" className="w-full text-xs h-7 bg-purple-600">Forward</Button>
                                <Button onClick={() => handleAction("move_right")} variant="outline" size="sm" className="w-full text-xs h-7">Right</Button>

                                <Button onClick={() => handleAction("grasp_mug")} variant="secondary" size="sm" className="w-full text-xs h-7 mt-2 col-span-1">Grasp Mug</Button>
                                <Button onClick={() => handleAction("move_backward")} variant="outline" size="sm" className="w-full text-xs h-7 mt-2">Backward</Button>
                                <Button onClick={() => handleAction("go_home")} variant="secondary" size="sm" className="w-full text-xs h-7 mt-2 col-span-1">Home Pose</Button>
                                <Button onClick={() => executeImmediateAction("stop_motion", { source: "ui_button", deadmanActive: true })} variant="destructive" size="sm" className="w-full text-xs h-7 mt-2 col-span-3">Emergency Stop</Button>
                            </div>

                            {episode?.launchProfile?.enableMoveIt && (
                                <div className="grid grid-cols-2 gap-2 mt-2">
                                    <Button
                                        onClick={() => handleAction("start_moveit_session")}
                                        variant="secondary"
                                        size="sm"
                                        className="w-full text-xs h-7"
                                        disabled={!!teleopStatus?.moveitSessionActive}
                                    >
                                        Start MoveIt Session
                                    </Button>
                                    <Button
                                        onClick={() => handleAction("stop_moveit_session")}
                                        variant="outline"
                                        size="sm"
                                        className="w-full text-xs h-7"
                                        disabled={!teleopStatus?.moveitSessionActive}
                                    >
                                        Stop MoveIt Session
                                    </Button>
                                    <Button onClick={() => handleAction("moveit_plan_pick")} variant="secondary" size="sm" className="w-full text-xs h-7">
                                        Plan Pick
                                    </Button>
                                    <Button onClick={() => handleAction("moveit_plan_place")} variant="secondary" size="sm" className="w-full text-xs h-7">
                                        Plan Place
                                    </Button>
                                    <Button onClick={() => handleAction("moveit_plan_pick_sink")} variant="secondary" size="sm" className="w-full text-xs h-7">
                                        Pick Sink
                                    </Button>
                                    <Button onClick={() => handleAction("moveit_plan_pick_fridge")} variant="secondary" size="sm" className="w-full text-xs h-7">
                                        Pick Fridge
                                    </Button>
                                    <Button onClick={() => handleAction("moveit_go_home")} variant="outline" size="sm" className="w-full text-xs h-7">
                                        MoveIt Home
                                    </Button>
                                </div>
                            )}
                            <div className="grid grid-cols-1 gap-2 mt-2">
                                <Button
                                    onClick={() => executeImmediateAction("", {
                                        source: "mock_vr_replay",
                                        deadmanActive: true,
                                        replayFrame: { linearX: 0.8, angularZ: 0.0 },
                                    })}
                                    variant="outline"
                                    size="sm"
                                    className="w-full text-xs h-7"
                                >
                                    Mock VR Replay Step
                                </Button>
                            </div>
                            {(teleopStatus?.vrEnabled || teleopStatus?.moveitEnabled) && (
                                <div className="rounded border border-purple-200 p-2 mt-2 text-[11px]">
                                    <div>VR session: {teleopStatus?.vrSessionActive ? "active" : "inactive"}</div>
                                    <div>MoveIt session: {teleopStatus?.moveitSessionActive ? "active" : "inactive"}</div>
                                    <div>ROS2 bridge: {teleopStatus?.ros2Available === null ? "unknown" : teleopStatus?.ros2Available ? "available" : "unavailable"}</div>
                                    <div>MoveIt bridge: {teleopStatus?.moveitAvailable === null ? "unknown" : teleopStatus?.moveitAvailable ? "available" : "unavailable"}</div>
                                    {teleopStatus?.bridgeMode && <div>Bridge mode: {teleopStatus.bridgeMode}</div>}
                                    <div>ROS2 setup source: {teleopStatus?.ros2SetupSource || "none"}</div>
                                    {teleopStatus?.activeRos2SetupCommand ? (
                                        <div className="break-all">ROS2 setup command: {teleopStatus.activeRos2SetupCommand}</div>
                                    ) : (
                                        <div>ROS2 setup command: not set</div>
                                    )}
                                    {teleopStatus?.lastCommand && <div>Last command: {teleopStatus.lastCommand}</div>}
                                    {Array.isArray(teleopStatus?.supportedInputSources) && (
                                        <div>Input sources: {teleopStatus.supportedInputSources.join(", ")}</div>
                                    )}
                                    {teleopStatus?.lastError && <div className="text-red-500">Last error: {teleopStatus.lastError}</div>}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                )}
            </div>

            {/* RIGHT COLUMN: Logs & Tasks */}
            <div className="md:col-span-2 space-y-6">
                <Card className="h-[400px] flex flex-col">
                    <CardHeader className="pb-2">
                        <CardTitle className="flex items-center">
                            <Terminal className="w-5 h-5 mr-2" /> Live Execution Logs
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="flex-1 p-0 overflow-hidden">
                        <div ref={scrollRef} className="h-full w-full bg-black text-green-400 p-4 font-mono text-xs overflow-y-auto">
                            {logs.length === 0 ? (
                                <div className="text-gray-500 italic">Waiting for logs...</div>
                            ) : (
                                logs.map((log, i) => (
                                    <div key={i} className="mb-1 leading-relaxed">
                                        <span className="text-gray-500 mr-2">[{format(new Date(), "HH:mm:ss")}]</span>
                                        {log}
                                    </div>
                                ))
                            )}
                        </div>
                    </CardContent>
                </Card>

                {config?.streamingMode === "browser_embedded_optional" && (
                    <Card className="h-[400px] flex flex-col overflow-hidden">
                        <CardHeader className="pb-2 space-y-2">
                            <CardTitle className="flex items-center text-sm justify-between">
                                <span>Live WebRTC Stream (Embedded)</span>
                                <span className="text-xs font-normal">State: {streamState}</span>
                            </CardTitle>
                            <div className="flex gap-2">
                                <Button size="sm" variant="outline" onClick={() => setStreamLayout((prev) => (prev === "fit" ? "fill" : "fit"))}>
                                    Layout: {streamLayout}
                                </Button>
                                <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => {
                                        setStreamTransport("webrtc");
                                        setStreamRefreshToken((prev) => prev + 1);
                                    }}
                                >
                                    <RefreshCcw className="w-4 h-4 mr-1" /> Reconnect
                                </Button>
                                <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => setStreamTransport((prev) => (prev === "webrtc" ? "frame_fallback" : "webrtc"))}
                                >
                                    Transport: {streamTransport === "webrtc" ? "WebRTC" : "Frame"}
                                </Button>
                                {config?.isaacHost && (
                                    <Button size="sm" variant="outline" asChild>
                                        <a href={streamHintUrl} target="_blank" rel="noreferrer">
                                            Open tab
                                        </a>
                                    </Button>
                                )}
                            </div>
                        </CardHeader>
                        <CardContent className="flex-1 p-0 bg-black">
                            {isRunning ? (
                                streamTransport === "webrtc" ? (
                                    <iframe
                                        key={streamRefreshToken}
                                        src={streamHintUrl}
                                        className={`w-full h-full border-0 ${streamLayout === "fill" ? "object-cover" : "object-contain"}`}
                                        sandbox="allow-scripts allow-same-origin"
                                        title="Isaac WebRTC Stream"
                                        onLoad={() => setStreamState((prev) => (prev === "offline" ? "offline" : "connecting"))}
                                        onError={() => {
                                            setStreamState("reconnecting");
                                            setStreamTransport("frame_fallback");
                                        }}
                                    />
                                ) : (
                                    <img
                                        src={`/api/episodes/${id}/stream/frame?refresh=${streamRefreshToken}&tick=${frameTick}`}
                                        alt="Live frame stream"
                                        className={`w-full h-full ${streamLayout === "fill" ? "object-cover" : "object-contain"}`}
                                        onLoad={() => setStreamState("live")}
                                        onError={() => setStreamState("reconnecting")}
                                    />
                                )
                            ) : (
                                <div className="h-full w-full flex items-center justify-center text-muted-foreground text-sm">
                                    Start episode to connect stream.
                                </div>
                            )}
                        </CardContent>
                    </Card>
                )}

                <VideoPlayerCard videos={videos} />

                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm">Dataset Validation</CardTitle>
                    </CardHeader>
                    <CardContent className="text-xs space-y-1">
                        <div>valid: {String(!!validation?.valid)}</div>
                        <div>required outputs: {(validation?.requiredOutputs || []).join(", ") || "n/a"}</div>
                        {(validation?.missingFiles || []).length > 0 && (
                            <div className="text-red-500">missing: {validation.missingFiles.join(", ")}</div>
                        )}
                        {(validation?.issues || []).length > 0 && (
                            <div className="text-red-500">issues: {validation.issues.join(" | ")}</div>
                        )}
                        {validation?.summary && <div>summary: {validation.summary}</div>}
                    </CardContent>
                </Card>

                {episode.status === "completed" && (
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between">
                            <CardTitle className="text-sm">Real Data Analysis</CardTitle>
                            <Button size="sm" onClick={() => handleAction("sync")} disabled={loading}>
                                <Download className="w-4 h-4 mr-2" /> Sync Data
                            </Button>
                        </CardHeader>
                        <CardContent>
                            {/* Simple local check: if we have downloaded the telemetry json, display it. Since we fetch videos, let's also fetch a quick preview from the API */}
                            <div className="text-xs text-muted-foreground mb-4">
                                Click 'Sync Data' to fetch artifact files (video, telemetry) from the remote simulation host.
                            </div>
                            {videos.filter(v => v.name.endsWith('.json')).length > 0 ? (
                                videos.filter(v => v.name.endsWith('.json')).map(file => (
                                    <Button key={file.name} variant="outline" size="sm" asChild className="w-full mb-2">
                                        <a href={file.downloadUrl || file.playUrl} download={file.name}>
                                            <Download className="w-4 h-4 mr-2" /> Download {file.name}
                                        </a>
                                    </Button>
                                ))
                            ) : (
                                <Button variant="outline" size="sm" asChild className="w-full" disabled>
                                    <span>
                                        <Download className="w-4 h-4 mr-2" /> No Data Files Found
                                    </span>
                                </Button>
                            )}
                        </CardContent>
                    </Card>
                )}

                <div className="grid grid-cols-2 gap-6">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Assigned Tasks</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ul className="list-disc pl-4 text-sm space-y-1">
                                {(() => {
                                    try {
                                        const tasks = JSON.parse(episode.tasks);
                                        if (tasks.length === 0) return <li className="text-muted-foreground">No tasks assigned</li>;
                                        return tasks.map((t: string) => <li key={t}>{t}</li>);
                                    } catch { return <li>Error parsing tasks</li> }
                                })()}
                            </ul>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Recording Sensors</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="flex flex-wrap gap-2">
                                {(() => {
                                    try {
                                        const sensors = JSON.parse(episode.sensors);
                                        if (sensors.length === 0) return <span className="text-muted-foreground text-sm">No sensors specified</span>;
                                        return sensors.map((s: string) => <Badge key={s} variant="outline">{s}</Badge>);
                                    } catch { return <span>Error parsing sensors</span> }
                                })()}
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>

            <AlertDialog open={!!confirmAction} onOpenChange={(open) => !open && setConfirmAction(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Confirm Action</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to {confirmAction} this episode?
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={executeAction}>Continue</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            <AlertDialog open={!!alertMessage} onOpenChange={(open) => !open && setAlertMessage(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Error</AlertDialogTitle>
                        <AlertDialogDescription className="text-red-500 font-medium whitespace-pre-wrap">
                            {alertMessage}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogAction onClick={() => setAlertMessage(null)}>OK</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}

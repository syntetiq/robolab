"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Progress } from "@/components/ui/progress";
import { Play, Pause, RotateCcw, Plus, Trash2, Loader2, RefreshCw } from "lucide-react";
import { format } from "date-fns";
import { HelpTooltip } from "@/components/HelpTooltip";

interface BatchEpisode {
    id: string;
    status: string;
    batchIndex: number;
    seed: number;
    startedAt?: string;
    stoppedAt?: string;
    notes?: string;
}

interface Batch {
    id: string;
    name: string;
    description: string;
    status: string;
    sceneId: string;
    launchProfileId?: string;
    objectSetId?: string;
    taskConfigPath: string;
    durationSec: number;
    totalEpisodes: number;
    completedCount: number;
    failedCount: number;
    baseSeed: number;
    currentIndex: number;
    episodes: BatchEpisode[];
    createdAt: string;
}

interface Scene {
    id: string;
    name: string;
}

interface LaunchProfile {
    id: string;
    name: string;
}

interface ObjectSet {
    id: string;
    name: string;
}

interface TaskConfig {
    file: string;
    configPath: string;
    name: string;
    durationSec: number;
    taskCount: number;
}

const STATUS_COLORS: Record<string, string> = {
    created: "bg-gray-100 text-gray-700",
    running: "bg-blue-100 text-blue-700",
    paused: "bg-yellow-100 text-yellow-700",
    completed: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    queued: "bg-gray-100 text-gray-600",
};

export default function BatchesPage() {
    const [batches, setBatches] = useState<Batch[]>([]);
    const [scenes, setScenes] = useState<Scene[]>([]);
    const [profiles, setProfiles] = useState<LaunchProfile[]>([]);
    const [objectSets, setObjectSets] = useState<ObjectSet[]>([]);
    const [taskConfigs, setTaskConfigs] = useState<TaskConfig[]>([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [expandedBatch, setExpandedBatch] = useState<string | null>(null);
    const [actionLoading, setActionLoading] = useState<string | null>(null);

    const [form, setForm] = useState({
        name: "",
        description: "",
        sceneId: "",
        launchProfileId: "",
        objectSetId: "",
        taskConfigPath: "",
        totalEpisodes: 5,
        durationSec: 60,
        baseSeed: 42,
    });

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const [bRes, sRes, pRes, oRes, tRes] = await Promise.all([
                fetch("/api/batches"),
                fetch("/api/scenes"),
                fetch("/api/launch-profiles"),
                fetch("/api/object-sets"),
                fetch("/api/experiments"),
            ]);
            if (bRes.ok) setBatches(await bRes.json());
            if (sRes.ok) setScenes(await sRes.json());
            if (pRes.ok) setProfiles(await pRes.json());
            if (oRes.ok) setObjectSets(await oRes.json());
            if (tRes.ok) setTaskConfigs(await tRes.json());
        } catch (e) {
            console.error("Failed to fetch:", e);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchAll(); }, [fetchAll]);

    // Auto-refresh running batches every 10s
    useEffect(() => {
        const hasRunning = batches.some((b) => b.status === "running");
        if (!hasRunning) return;
        const timer = setInterval(fetchAll, 10_000);
        return () => clearInterval(timer);
    }, [batches, fetchAll]);

    const handleCreate = async () => {
        if (!form.name.trim() || !form.sceneId) return;
        setActionLoading("create");
        try {
            const res = await fetch("/api/batches", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ...form,
                    launchProfileId: form.launchProfileId || undefined,
                    objectSetId: form.objectSetId || undefined,
                }),
            });
            if (res.ok) {
                setShowCreate(false);
                setForm({ name: "", description: "", sceneId: "", launchProfileId: "", objectSetId: "", taskConfigPath: "", totalEpisodes: 5, durationSec: 60, baseSeed: 42 });
                await fetchAll();
            }
        } finally {
            setActionLoading(null);
        }
    };

    const handleAction = async (batchId: string, action: "start" | "pause" | "resume" | "delete") => {
        setActionLoading(`${action}-${batchId}`);
        try {
            if (action === "delete") {
                await fetch(`/api/batches/${batchId}`, { method: "DELETE" });
            } else {
                await fetch(`/api/batches/${batchId}/${action}`, { method: "POST" });
            }
            await fetchAll();
        } finally {
            setActionLoading(null);
        }
    };

    const progressPercent = (b: Batch) => {
        if (b.totalEpisodes === 0) return 0;
        return Math.round(((b.completedCount + b.failedCount) / b.totalEpisodes) * 100);
    };

    return (
        <div className="p-8 max-w-7xl mx-auto space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Batch Queue</h1>
                    <p className="text-muted-foreground mt-1">Create and manage batch episode collections for data collection campaigns</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={fetchAll} disabled={loading}>
                        <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
                    </Button>
                    <Button size="sm" onClick={() => setShowCreate(true)}>
                        <Plus className="w-4 h-4 mr-1" /> New Batch
                    </Button>
                </div>
            </div>

            {batches.length === 0 && !loading && (
                <Card>
                    <CardContent className="py-12 text-center text-muted-foreground">
                        No batches yet. Create one to start collecting data at scale.
                    </CardContent>
                </Card>
            )}

            {batches.map((batch) => {
                const isExpanded = expandedBatch === batch.id;
                const pct = progressPercent(batch);
                return (
                    <Card key={batch.id}>
                        <CardHeader className="pb-3">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <CardTitle className="text-lg">{batch.name}</CardTitle>
                                    <Badge className={STATUS_COLORS[batch.status] || ""}>{batch.status}</Badge>
                                </div>
                                <div className="flex gap-2">
                                    {batch.status === "created" && (
                                        <Button
                                            size="sm"
                                            onClick={() => handleAction(batch.id, "start")}
                                            disabled={actionLoading === `start-${batch.id}`}
                                        >
                                            {actionLoading === `start-${batch.id}` ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 mr-1" />}
                                            Start
                                        </Button>
                                    )}
                                    {batch.status === "running" && (
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() => handleAction(batch.id, "pause")}
                                            disabled={actionLoading === `pause-${batch.id}`}
                                        >
                                            <Pause className="w-4 h-4 mr-1" /> Pause
                                        </Button>
                                    )}
                                    {batch.status === "paused" && (
                                        <Button
                                            size="sm"
                                            onClick={() => handleAction(batch.id, "resume")}
                                            disabled={actionLoading === `resume-${batch.id}`}
                                        >
                                            <RotateCcw className="w-4 h-4 mr-1" /> Resume
                                        </Button>
                                    )}
                                    {batch.status !== "running" && (
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="text-red-500 hover:text-red-700"
                                            onClick={() => handleAction(batch.id, "delete")}
                                            disabled={!!actionLoading}
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </Button>
                                    )}
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            {batch.description && (
                                <p className="text-sm text-muted-foreground">{batch.description}</p>
                            )}
                            <div className="flex gap-4 text-sm text-muted-foreground">
                                <span>{batch.totalEpisodes} episodes</span>
                                <span>{batch.completedCount} completed</span>
                                {batch.failedCount > 0 && <span className="text-red-500">{batch.failedCount} failed</span>}
                                <span>Seed: {batch.baseSeed}-{batch.baseSeed + batch.totalEpisodes - 1}</span>
                                <span>{batch.durationSec}s/episode</span>
                            </div>
                            <Progress value={pct} className="h-2" />
                            <div className="flex justify-between text-xs text-muted-foreground">
                                <span>{pct}% complete</span>
                                <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => setExpandedBatch(isExpanded ? null : batch.id)}>
                                    {isExpanded ? "Hide episodes" : "Show episodes"}
                                </Button>
                            </div>

                            {isExpanded && batch.episodes.length > 0 && (
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>#</TableHead>
                                            <TableHead>Status</TableHead>
                                            <TableHead>Seed</TableHead>
                                            <TableHead>Started</TableHead>
                                            <TableHead>Stopped</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {batch.episodes.map((ep) => (
                                            <TableRow key={ep.id}>
                                                <TableCell>{(ep.batchIndex ?? 0) + 1}</TableCell>
                                                <TableCell>
                                                    <Badge variant="outline" className={STATUS_COLORS[ep.status] || ""}>
                                                        {ep.status}
                                                    </Badge>
                                                </TableCell>
                                                <TableCell className="font-mono text-xs">{ep.seed}</TableCell>
                                                <TableCell className="text-xs text-muted-foreground">
                                                    {ep.startedAt ? format(new Date(ep.startedAt), "HH:mm:ss") : "—"}
                                                </TableCell>
                                                <TableCell className="text-xs text-muted-foreground">
                                                    {ep.stoppedAt ? format(new Date(ep.stoppedAt), "HH:mm:ss") : "—"}
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            )}
                        </CardContent>
                    </Card>
                );
            })}

            {/* Create Batch Dialog */}
            <Dialog open={showCreate} onOpenChange={setShowCreate}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle>New Batch</DialogTitle>
                        <DialogDescription>Create a batch of episodes with varying seeds for data collection.</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        <div className="space-y-2">
                            <Label>Batch Name</Label>
                            <Input
                                value={form.name}
                                onChange={(e) => setForm({ ...form, name: e.target.value })}
                                placeholder="Pick-Place Mug Campaign"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Description</Label>
                            <Input
                                value={form.description}
                                onChange={(e) => setForm({ ...form, description: e.target.value })}
                                placeholder="50 episodes of mug pick-place with varying seeds"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Scene</Label>
                            <Select value={form.sceneId} onValueChange={(v) => setForm({ ...form, sceneId: v })}>
                                <SelectTrigger><SelectValue placeholder="Select scene" /></SelectTrigger>
                                <SelectContent>
                                    {scenes.map((s) => (
                                        <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Launch Profile (optional)</Label>
                            <Select value={form.launchProfileId} onValueChange={(v) => setForm({ ...form, launchProfileId: v })}>
                                <SelectTrigger><SelectValue placeholder="Default" /></SelectTrigger>
                                <SelectContent>
                                    {profiles.map((p) => (
                                        <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label className="flex items-center">Object Set (optional) <HelpTooltip content="Predefined collection of graspable objects to spawn in the scene." /></Label>
                            <Select value={form.objectSetId} onValueChange={(v) => setForm({ ...form, objectSetId: v })}>
                                <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                                <SelectContent>
                                    {objectSets.map((o) => (
                                        <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label className="flex items-center">Task Config (optional) <HelpTooltip content="Optional task config defining automated actions. Leave empty for free-form teleoperation." /></Label>
                            <Select value={form.taskConfigPath} onValueChange={(v) => setForm({ ...form, taskConfigPath: v })}>
                                <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                                <SelectContent>
                                    {taskConfigs.map((t) => (
                                        <SelectItem key={t.configPath} value={t.configPath}>{t.name} ({t.taskCount} tasks)</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="grid grid-cols-3 gap-4">
                            <div className="space-y-2">
                                <Label className="flex items-center">Episodes <HelpTooltip content="Number of episodes to generate. Each runs with a unique seed." /></Label>
                                <Input
                                    type="number"
                                    min={1}
                                    max={100}
                                    value={form.totalEpisodes}
                                    onChange={(e) => setForm({ ...form, totalEpisodes: parseInt(e.target.value) || 1 })}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label className="flex items-center">Duration (s) <HelpTooltip content="How long each episode runs before auto-stopping (seconds)." /></Label>
                                <Input
                                    type="number"
                                    min={10}
                                    value={form.durationSec}
                                    onChange={(e) => setForm({ ...form, durationSec: parseInt(e.target.value) || 60 })}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label className="flex items-center">Base Seed <HelpTooltip content="Starting seed value. Each episode increments by 1 (e.g. 42, 43, 44...) for reproducible variation." /></Label>
                                <Input
                                    type="number"
                                    value={form.baseSeed}
                                    onChange={(e) => setForm({ ...form, baseSeed: parseInt(e.target.value) || 42 })}
                                />
                            </div>
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Seeds will be: {form.baseSeed}, {form.baseSeed + 1}, ... {form.baseSeed + (form.totalEpisodes || 1) - 1}. Each episode runs independently with its own seed for object placement randomization.
                        </p>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
                        <Button
                            onClick={handleCreate}
                            disabled={!form.name.trim() || !form.sceneId || actionLoading === "create"}
                        >
                            {actionLoading === "create" ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Plus className="w-4 h-4 mr-1" />}
                            Create Batch
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

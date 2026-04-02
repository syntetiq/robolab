"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
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
import { Play, FolderOpen, Clock, Bot, ListChecks, RefreshCw, Video, Loader2, Trash2, Eye } from "lucide-react";
import { format } from "date-fns";

interface Experiment {
    file: string;
    configPath: string;
    name: string;
    description: string;
    durationSec: number;
    robotModel: string;
    taskCount: number;
}

interface Run {
    dir: string;
    fullPath: string;
    experimentName: string;
    timestamp: string | null;
    createdAt: string | null;
    hasVideo: boolean;
    hasHeavy: boolean;
}

export default function ExperimentsPage() {
    const [experiments, setExperiments] = useState<Experiment[]>([]);
    const [runs, setRuns] = useState<Run[]>([]);
    const [loading, setLoading] = useState(true);
    const [launching, setLaunching] = useState<string | null>(null);
    const [confirmLaunch, setConfirmLaunch] = useState<Experiment | null>(null);
    const [confirmDeleteConfig, setConfirmDeleteConfig] = useState<Experiment | null>(null);
    const [confirmDeleteRun, setConfirmDeleteRun] = useState<Run | null>(null);
    const [deleting, setDeleting] = useState(false);
    const [lastResult, setLastResult] = useState<{ ok: boolean; message: string } | null>(null);

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const [expRes, runsRes] = await Promise.all([
                fetch("/api/experiments"),
                fetch("/api/experiments/runs"),
            ]);
            if (expRes.ok) setExperiments(await expRes.json());
            if (runsRes.ok) setRuns(await runsRes.json());
        } catch (e) {
            console.error("Failed to fetch experiments:", e);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleLaunch = async (exp: Experiment) => {
        setConfirmLaunch(null);
        setLaunching(exp.configPath);
        setLastResult(null);
        try {
            const res = await fetch("/api/experiments/run", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ configPath: exp.configPath }),
            });
            const data = await res.json();
            if (res.ok) {
                setLastResult({ ok: true, message: `Launched "${exp.name}" (PID ${data.pid}). Duration: ${data.durationSec}s` });
                setTimeout(fetchData, 3000);
            } else {
                setLastResult({ ok: false, message: data.error || "Launch failed" });
            }
        } catch (e: any) {
            setLastResult({ ok: false, message: e.message || "Network error" });
        } finally {
            setLaunching(null);
        }
    };

    const handleDeleteConfig = async () => {
        if (!confirmDeleteConfig) return;
        setDeleting(true);
        try {
            const res = await fetch("/api/experiments", {
                method: "DELETE",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ file: confirmDeleteConfig.file }),
            });
            if (res.ok) {
                setExperiments((prev) => prev.filter((e) => e.file !== confirmDeleteConfig.file));
                setLastResult({ ok: true, message: `Deleted config "${confirmDeleteConfig.name}"` });
            } else {
                const data = await res.json();
                setLastResult({ ok: false, message: data.error || "Delete failed" });
            }
        } catch (e: any) {
            setLastResult({ ok: false, message: e.message || "Network error" });
        } finally {
            setDeleting(false);
            setConfirmDeleteConfig(null);
        }
    };

    const handleDeleteRun = async () => {
        if (!confirmDeleteRun) return;
        setDeleting(true);
        try {
            const res = await fetch("/api/experiments/runs", {
                method: "DELETE",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ dir: confirmDeleteRun.dir }),
            });
            if (res.ok) {
                setRuns((prev) => prev.filter((r) => r.dir !== confirmDeleteRun.dir));
                setLastResult({ ok: true, message: `Deleted run "${confirmDeleteRun.dir}"` });
            } else {
                const data = await res.json();
                setLastResult({ ok: false, message: data.error || "Delete failed" });
            }
        } catch (e: any) {
            setLastResult({ ok: false, message: e.message || "Network error" });
        } finally {
            setDeleting(false);
            setConfirmDeleteRun(null);
        }
    };

    const runsForExperiment = (name: string) =>
        runs.filter((r) => r.experimentName === name);

    const formatDuration = (sec: number) => {
        if (sec < 60) return `${sec}s`;
        return `${Math.floor(sec / 60)}m ${sec % 60}s`;
    };

    return (
        <div className="p-8 max-w-7xl mx-auto space-y-8">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Experiments</h1>
                    <p className="text-muted-foreground mt-1">
                        Task-config experiments from <code className="text-xs bg-muted px-1 py-0.5 rounded">config/tasks/</code>
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchData} disabled={loading}>
                    <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
                    Refresh
                </Button>
            </div>

            {lastResult && (
                <div className={`rounded-lg border px-4 py-3 text-sm ${lastResult.ok ? "bg-green-50 border-green-200 text-green-800" : "bg-red-50 border-red-200 text-red-800"}`}>
                    {lastResult.message}
                </div>
            )}

            {loading && experiments.length === 0 ? (
                <div className="flex items-center justify-center py-20 text-muted-foreground">
                    <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading experiments...
                </div>
            ) : (
                <>
                    <section>
                        <h2 className="text-xl font-semibold mb-4">Available Configs ({experiments.length})</h2>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {experiments.map((exp) => {
                                const pastRuns = runsForExperiment(exp.name);
                                const isLaunching = launching === exp.configPath;
                                return (
                                    <Card key={exp.file} className="flex flex-col">
                                        <CardHeader>
                                            <CardTitle className="text-base">{exp.name}</CardTitle>
                                            {exp.description && (
                                                <CardDescription className="line-clamp-2">{exp.description}</CardDescription>
                                            )}
                                        </CardHeader>
                                        <CardContent className="flex-1">
                                            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                                                <span className="flex items-center gap-1">
                                                    <Clock className="w-3.5 h-3.5" /> {formatDuration(exp.durationSec)}
                                                </span>
                                                <span className="flex items-center gap-1">
                                                    <Bot className="w-3.5 h-3.5" /> {exp.robotModel}
                                                </span>
                                                {exp.taskCount > 0 && (
                                                    <span className="flex items-center gap-1">
                                                        <ListChecks className="w-3.5 h-3.5" /> {exp.taskCount} tasks
                                                    </span>
                                                )}
                                                {pastRuns.length > 0 && (
                                                    <Badge variant="secondary" className="text-xs">{pastRuns.length} run{pastRuns.length !== 1 ? "s" : ""}</Badge>
                                                )}
                                            </div>
                                        </CardContent>
                                        <CardFooter className="gap-2">
                                            <Button
                                                size="sm"
                                                className="flex-1"
                                                disabled={isLaunching}
                                                onClick={() => setConfirmLaunch(exp)}
                                            >
                                                {isLaunching ? (
                                                    <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Launching...</>
                                                ) : (
                                                    <><Play className="w-4 h-4 mr-1" /> Launch</>
                                                )}
                                            </Button>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="text-red-500 hover:text-red-700 hover:bg-red-50"
                                                onClick={() => setConfirmDeleteConfig(exp)}
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </Button>
                                        </CardFooter>
                                    </Card>
                                );
                            })}
                        </div>
                    </section>

                    <section>
                        <h2 className="text-xl font-semibold mb-4">Past Runs ({runs.length})</h2>
                        {runs.length === 0 ? (
                            <p className="text-muted-foreground text-sm">No past runs found in the output directory.</p>
                        ) : (
                            <Card>
                                <CardContent className="p-0">
                                    <Table>
                                        <TableHeader>
                                            <TableRow>
                                                <TableHead>Experiment</TableHead>
                                                <TableHead>Directory</TableHead>
                                                <TableHead>Date</TableHead>
                                                <TableHead>Content</TableHead>
                                                <TableHead className="text-right">Actions</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {runs.map((run) => (
                                                <TableRow key={run.dir}>
                                                    <TableCell className="font-medium">{run.experimentName}</TableCell>
                                                    <TableCell className="text-xs text-muted-foreground font-mono max-w-[200px] truncate" title={run.fullPath}>
                                                        {run.dir}
                                                    </TableCell>
                                                    <TableCell className="text-sm text-muted-foreground">
                                                        {run.timestamp
                                                            ? format(new Date(run.timestamp), "MMM d, HH:mm")
                                                            : run.createdAt
                                                                ? format(new Date(run.createdAt), "MMM d, HH:mm")
                                                                : "—"}
                                                    </TableCell>
                                                    <TableCell>
                                                        <div className="flex gap-1.5">
                                                            {run.hasHeavy && <Badge variant="outline" className="text-xs">heavy</Badge>}
                                                            {run.hasVideo && (
                                                                <Badge variant="secondary" className="text-xs">
                                                                    <Video className="w-3 h-3 mr-0.5" /> video
                                                                </Badge>
                                                            )}
                                                        </div>
                                                    </TableCell>
                                                    <TableCell className="text-right space-x-2">
                                                        <Link href={`/experiments/runs/${encodeURIComponent(run.dir)}`}>
                                                            <Button variant="outline" size="sm" title="View run content">
                                                                <Eye className="w-4 h-4 mr-1" /> View
                                                            </Button>
                                                        </Link>
                                                        <Button
                                                            variant="outline"
                                                            size="sm"
                                                            onClick={() => {
                                                                navigator.clipboard.writeText(run.fullPath);
                                                            }}
                                                            title="Copy full path to clipboard"
                                                        >
                                                            <FolderOpen className="w-4 h-4 mr-1" /> Copy Path
                                                        </Button>
                                                        <Button
                                                            variant="outline"
                                                            size="sm"
                                                            className="text-red-500 hover:text-red-700 hover:bg-red-50"
                                                            onClick={() => setConfirmDeleteRun(run)}
                                                            title="Delete this run directory"
                                                        >
                                                            <Trash2 className="w-4 h-4" />
                                                        </Button>
                                                    </TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </CardContent>
                            </Card>
                        )}
                    </section>
                </>
            )}

            <AlertDialog open={!!confirmLaunch} onOpenChange={(o) => !o && setConfirmLaunch(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Launch Experiment</AlertDialogTitle>
                        <AlertDialogDescription>
                            Run <strong>{confirmLaunch?.name}</strong> ({formatDuration(confirmLaunch?.durationSec || 0)})?
                            This will spawn <code className="text-xs bg-muted px-1 py-0.5 rounded">run_task_config.ps1</code> in the background.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={() => confirmLaunch && handleLaunch(confirmLaunch)}>
                            <Play className="w-4 h-4 mr-1" /> Launch
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            <AlertDialog open={!!confirmDeleteConfig} onOpenChange={(o) => !o && setConfirmDeleteConfig(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Config</AlertDialogTitle>
                        <AlertDialogDescription>
                            Permanently delete <strong>{confirmDeleteConfig?.name}</strong> (<code className="text-xs bg-muted px-1 py-0.5 rounded">{confirmDeleteConfig?.file}</code>)?
                            This cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={handleDeleteConfig} disabled={deleting} className="bg-red-600 hover:bg-red-700">
                            {deleting ? "Deleting..." : "Delete"}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            <AlertDialog open={!!confirmDeleteRun} onOpenChange={(o) => !o && setConfirmDeleteRun(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Run</AlertDialogTitle>
                        <AlertDialogDescription>
                            Permanently delete run directory <strong>{confirmDeleteRun?.dir}</strong> and all its contents?
                            This cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={handleDeleteRun} disabled={deleting} className="bg-red-600 hover:bg-red-700">
                            {deleting ? "Deleting..." : "Delete"}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}

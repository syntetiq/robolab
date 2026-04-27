"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Video, FileJson, FileText, FolderOpen, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { format } from "date-fns";

interface FileItem {
    name: string;
    relPath: string;
    isDir: boolean;
    size?: number;
}

interface RunDetail {
    dir: string;
    experimentName: string;
    timestamp: string | null;
    createdAt: string | null;
    hasHeavy: boolean;
    videos: FileItem[];
    jsonFiles: FileItem[];
    otherFiles: FileItem[];
    allFiles: FileItem[];
}

function fileUrl(dir: string, relPath: string) {
    return `/api/experiments/runs/${encodeURIComponent(dir)}/file?path=${encodeURIComponent(relPath)}`;
}

function formatSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function RunDetailPage() {
    const params = useParams();
    const dir = typeof params.dir === "string" ? params.dir : params.dir?.[0] ?? "";
    const [run, setRun] = useState<RunDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [jsonContent, setJsonContent] = useState<Record<string, unknown> | null>(null);
    const [jsonLoading, setJsonLoading] = useState<string | null>(null);

    useEffect(() => {
        if (!dir) return;
        setLoading(true);
        fetch(`/api/experiments/runs/${encodeURIComponent(dir)}`)
            .then((r) => (r.ok ? r.json() : Promise.reject(r)))
            .then(setRun)
            .catch(() => setRun(null))
            .finally(() => setLoading(false));
    }, [dir]);

    const loadJson = (relPath: string) => {
        if (jsonLoading === relPath) return;
        setJsonLoading(relPath);
        fetch(fileUrl(dir, relPath))
            .then((r) => r.json())
            .then((data) => setJsonContent({ [relPath]: data }))
            .catch(() => setJsonContent({ [relPath]: { error: "Failed to load" } }))
            .finally(() => setJsonLoading(null));
    };

    if (loading) {
        return (
            <div className="p-8 max-w-5xl mx-auto flex items-center justify-center gap-2 text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin" /> Loading...
            </div>
        );
    }

    if (!run) {
        return (
            <div className="p-8 max-w-5xl mx-auto space-y-4">
                <Button variant="ghost" asChild>
                    <Link href="/experiments"><ArrowLeft className="w-4 h-4 mr-1" /> Back to Experiments</Link>
                </Button>
                <p className="text-destructive">Run not found.</p>
            </div>
        );
    }

    return (
        <div className="p-8 max-w-5xl mx-auto space-y-6">
            <div className="flex items-center gap-4">
                <Button variant="ghost" size="sm" asChild>
                    <Link href="/experiments"><ArrowLeft className="w-4 h-4 mr-1" /> Back</Link>
                </Button>
                <div className="flex-1">
                    <h1 className="text-2xl font-bold">{run.experimentName}</h1>
                    <p className="text-sm text-muted-foreground font-mono">{run.dir}</p>
                    <div className="flex gap-2 mt-2">
                        {run.timestamp && (
                            <Badge variant="outline">{format(new Date(run.timestamp), "MMM d, yyyy HH:mm")}</Badge>
                        )}
                        {run.hasHeavy && <Badge variant="secondary">heavy</Badge>}
                    </div>
                </div>
            </div>

            {run.videos.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Video className="w-5 h-5" /> Videos
                        </CardTitle>
                        <CardDescription>Available video recordings for this run</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {run.videos.map((v) => (
                                <div key={v.relPath} className="space-y-1">
                                    <p className="text-sm font-medium truncate" title={v.relPath}>{v.name}</p>
                                    <video
                                        src={fileUrl(dir, v.relPath)}
                                        controls
                                        className="w-full rounded-lg border bg-black max-h-64"
                                        preload="metadata"
                                    />
                                    {v.size != null && (
                                        <p className="text-xs text-muted-foreground">{formatSize(v.size)}</p>
                                    )}
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}

            {run.jsonFiles.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <FileJson className="w-5 h-5" /> JSON Files
                        </CardTitle>
                        <CardDescription>task_results, physics_log, and other metadata</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex flex-wrap gap-2 mb-4">
                            {run.jsonFiles.map((f) => (
                                <Button
                                    key={f.relPath}
                                    variant="outline"
                                    size="sm"
                                    onClick={() => loadJson(f.relPath)}
                                    disabled={!!jsonLoading}
                                >
                                    {jsonLoading === f.relPath ? (
                                        <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                                    ) : (
                                        <FileJson className="w-4 h-4 mr-1" />
                                    )}
                                    {f.name}
                                </Button>
                            ))}
                        </div>
                        {jsonContent && (
                            <pre className="text-xs bg-muted p-4 rounded-lg overflow-auto max-h-96">
                                {JSON.stringify(Object.values(jsonContent)[0], null, 2)}
                            </pre>
                        )}
                    </CardContent>
                </Card>
            )}

            {run.otherFiles.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <FileText className="w-5 h-5" /> Other Files
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ul className="space-y-1 text-sm">
                            {run.otherFiles.map((f) => (
                                <li key={f.relPath} className="flex items-center gap-2">
                                    <FileText className="w-4 h-4 text-muted-foreground" />
                                    <span className="font-mono">{f.relPath}</span>
                                    {f.size != null && (
                                        <span className="text-muted-foreground">{formatSize(f.size)}</span>
                                    )}
                                </li>
                            ))}
                        </ul>
                    </CardContent>
                </Card>
            )}

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <FolderOpen className="w-5 h-5" /> All Files
                    </CardTitle>
                    <CardDescription>Complete file listing</CardDescription>
                </CardHeader>
                <CardContent>
                    <ul className="space-y-1 text-sm font-mono">
                        {run.allFiles.map((f) => (
                            <li key={f.relPath} className="flex items-center gap-2">
                                {f.isDir ? <FolderOpen className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                                {f.relPath}
                                {f.size != null && (
                                    <span className="text-muted-foreground ml-auto">{formatSize(f.size)}</span>
                                )}
                            </li>
                        ))}
                    </ul>
                </CardContent>
            </Card>
        </div>
    );
}

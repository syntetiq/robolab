"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface RecordingItem {
    episodeId: string;
    name: string;
    kind: "video" | "json";
    bytes: number;
    checksumSha256: string;
    updatedAt: string;
    playUrl: string;
    downloadUrl: string;
    sceneName: string;
}

export default function RecordingsPage() {
    const [items, setItems] = useState<RecordingItem[]>([]);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [kind, setKind] = useState("");
    const [query, setQuery] = useState("");
    const pageSize = 20;

    useEffect(() => {
        const qp = new URLSearchParams({
            page: String(page),
            pageSize: String(pageSize),
        });
        if (kind) qp.set("kind", kind);
        if (query) qp.set("q", query);
        fetch(`/api/recordings?${qp.toString()}`)
            .then((r) => r.json())
            .then((data) => {
                setItems(Array.isArray(data.items) ? data.items : []);
                setTotal(Number(data.total || 0));
            })
            .catch(() => {
                setItems([]);
                setTotal(0);
            });
    }, [page, kind, query]);

    return (
        <div className="p-8 max-w-7xl mx-auto space-y-4">
            <div>
                <h1 className="text-3xl font-bold tracking-tight">Recordings Library</h1>
                <p className="text-muted-foreground">Searchable index for episode videos and telemetry artifacts.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by filename, scene, task..." />
                <Input value={kind} onChange={(e) => setKind(e.target.value)} placeholder="Kind: video or json" />
                <div className="text-sm text-muted-foreground flex items-center">Total: {total}</div>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Artifacts</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                    {items.length === 0 && <div className="text-sm text-muted-foreground">No artifacts found.</div>}
                    {items.map((item) => (
                        <div key={`${item.episodeId}-${item.name}`} className="border rounded p-3 text-sm flex items-center justify-between gap-3">
                            <div>
                                <div className="font-medium">{item.name}</div>
                                <div className="text-muted-foreground">
                                    Episode: {item.episodeId} | Scene: {item.sceneName || "n/a"} | {Math.round(item.bytes / 1024)} KB
                                </div>
                            </div>
                            <div className="flex gap-2">
                                <Button variant="outline" size="sm" asChild>
                                    <a href={item.playUrl} target="_blank" rel="noreferrer">Open</a>
                                </Button>
                                <Button variant="outline" size="sm" asChild>
                                    <a href={item.downloadUrl} download={item.name}>Download</a>
                                </Button>
                            </div>
                        </div>
                    ))}
                    <div className="flex justify-end gap-2 pt-2">
                        <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>Prev</Button>
                        <Button variant="outline" size="sm" onClick={() => setPage((p) => p + 1)} disabled={page * pageSize >= total}>Next</Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

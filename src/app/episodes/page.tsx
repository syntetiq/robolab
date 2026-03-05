"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Eye, Play, CheckCircle2, XCircle, Clock, Square } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { format } from "date-fns";

export default function EpisodesPage() {
    const [episodes, setEpisodes] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchEpisodes = async () => {
        setLoading(true);
        try {
            const res = await fetch("/api/episodes");
            const data = await res.json();
            setEpisodes(data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchEpisodes();
    }, []);

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "created": return <Badge variant="secondary"><Clock className="w-3 h-3 mr-1" />Created</Badge>;
            case "running": return <Badge className="bg-blue-600"><Play className="w-3 h-3 mr-1" />Running</Badge>;
            case "stopping": return <Badge className="bg-orange-500"><Square className="w-3 h-3 mr-1" />Stopping</Badge>;
            case "stopped": return <Badge variant="outline"><Square className="w-3 h-3 mr-1" />Stopped</Badge>;
            case "completed": return <Badge className="bg-green-600"><CheckCircle2 className="w-3 h-3 mr-1" />Completed</Badge>;
            case "failed": return <Badge variant="destructive"><XCircle className="w-3 h-3 mr-1" />Failed</Badge>;
            default: return <Badge variant="outline">{status}</Badge>;
        }
    };

    return (
        <div className="p-8 max-w-7xl mx-auto">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Episodes</h1>
                    <p className="text-muted-foreground">Manage data-collection runs and track their status.</p>
                </div>
                <Link href="/episodes/new">
                    <Button>
                        <Plus className="w-4 h-4 mr-2" />
                        New Episode
                    </Button>
                </Link>
            </div>

            <div className="border rounded-lg bg-card">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Status</TableHead>
                            <TableHead>Scene</TableHead>
                            <TableHead>Object Set</TableHead>
                            <TableHead>Duration</TableHead>
                            <TableHead>Created</TableHead>
                            <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {loading ? (
                            <TableRow><TableCell colSpan={6} className="text-center py-8">Loading...</TableCell></TableRow>
                        ) : episodes.length === 0 ? (
                            <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No episodes found</TableCell></TableRow>
                        ) : episodes.map((ep) => (
                            <TableRow key={ep.id}>
                                <TableCell>{getStatusBadge(ep.status)}</TableCell>
                                <TableCell className="font-medium">{ep.scene?.name || "Unknown"}</TableCell>
                                <TableCell>{ep.objectSet?.name || "None"}</TableCell>
                                <TableCell>{ep.durationSec}s</TableCell>
                                <TableCell className="text-sm text-muted-foreground">
                                    {format(new Date(ep.createdAt), "MMM d, HH:mm")}
                                </TableCell>
                                <TableCell className="text-right">
                                    <Link href={`/episodes/${ep.id}`}>
                                        <Button variant="outline" size="sm">
                                            <Eye className="w-4 h-4 mr-2" />
                                            View
                                        </Button>
                                    </Link>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>
        </div>
    );
}

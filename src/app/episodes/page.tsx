"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Eye, Play, CheckCircle2, XCircle, Clock, Square, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { format } from "date-fns";
import { Input } from "@/components/ui/input";
import { HelpTooltip } from "@/components/HelpTooltip";
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

export default function EpisodesPage() {
    const [episodes, setEpisodes] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [statusFilter, setStatusFilter] = useState("");
    const [taskFilter, setTaskFilter] = useState("");
    const [queryFilter, setQueryFilter] = useState("");
    const [deleteTarget, setDeleteTarget] = useState<{ id: string; scene: string } | null>(null);
    const [deleting, setDeleting] = useState(false);

    const fetchEpisodes = async () => {
        setLoading(true);
        try {
            const qp = new URLSearchParams();
            if (statusFilter) qp.set("status", statusFilter);
            if (taskFilter) qp.set("task", taskFilter);
            if (queryFilter) qp.set("q", queryFilter);
            const res = await fetch(`/api/episodes?${qp.toString()}`);
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
    }, [statusFilter, taskFilter, queryFilter]);

    const handleDelete = async () => {
        if (!deleteTarget) return;
        setDeleting(true);
        try {
            const res = await fetch(`/api/episodes/${deleteTarget.id}`, { method: "DELETE" });
            if (res.ok) {
                setEpisodes((prev) => prev.filter((ep) => ep.id !== deleteTarget.id));
            }
        } catch (e) {
            console.error(e);
        } finally {
            setDeleting(false);
            setDeleteTarget(null);
        }
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "created": return <Badge variant="secondary"><Clock className="w-3 h-3 mr-1" />Created</Badge>;
            case "running": return <Badge variant="outline" className="border-blue-600 text-blue-700 bg-blue-50"><Play className="w-3 h-3 mr-1" />Running</Badge>;
            case "stopping": return <Badge variant="outline" className="border-orange-500 text-orange-700 bg-orange-50"><Square className="w-3 h-3 mr-1" />Stopping</Badge>;
            case "stopped": return <Badge variant="outline"><Square className="w-3 h-3 mr-1" />Stopped</Badge>;
            case "completed": return <Badge variant="outline" className="border-green-600 text-green-700 bg-green-50"><CheckCircle2 className="w-3 h-3 mr-1" />Completed</Badge>;
            case "failed": return <Badge variant="destructive"><XCircle className="w-3 h-3 mr-1" />Failed</Badge>;
            default: return <Badge variant="outline">{status}</Badge>;
        }
    };

    const canDelete = (status: string) => !["running", "stopping"].includes(status);

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

            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
                <Input value={queryFilter} onChange={(e) => setQueryFilter(e.target.value)} placeholder="Search by id, note, scene..." />
                <Input value={taskFilter} onChange={(e) => setTaskFilter(e.target.value)} placeholder="Task tag (e.g. pick_place_sink)" />
                <Input value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} placeholder="Status (running/completed/failed)" />
                <Link href="/recordings">
                    <Button variant="outline" className="w-full">Open Recordings Library</Button>
                </Link>
            </div>

            <div className="border rounded-lg bg-card">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead><span className="flex items-center">Status <HelpTooltip content="Created = ready to launch, Running = active, Completed = finished successfully, Failed = error occurred." /></span></TableHead>
                            <TableHead><span className="flex items-center">Scene <HelpTooltip content="The 3D environment (USD scene) used for this episode." /></span></TableHead>
                            <TableHead><span className="flex items-center">Duration <HelpTooltip content="Total episode run time in seconds." /></span></TableHead>
                            <TableHead>Created</TableHead>
                            <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {loading ? (
                            <TableRow><TableCell colSpan={5} className="text-center py-8">Loading...</TableCell></TableRow>
                        ) : episodes.length === 0 ? (
                            <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground">No episodes found</TableCell></TableRow>
                        ) : episodes.map((ep) => (
                            <TableRow key={ep.id}>
                                <TableCell>{getStatusBadge(ep.status)}</TableCell>
                                <TableCell className="font-medium">{ep.scene?.name || "Unknown"}</TableCell>
                                <TableCell>{ep.durationSec}s</TableCell>
                                <TableCell className="text-sm text-muted-foreground">
                                    {format(new Date(ep.createdAt), "MMM d, HH:mm")}
                                </TableCell>
                                <TableCell className="text-right space-x-2">
                                    <Link href={`/episodes/${ep.id}`}>
                                        <Button variant="outline" size="sm">
                                            <Eye className="w-4 h-4 mr-1" /> View
                                        </Button>
                                    </Link>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="text-red-500 hover:text-red-700 hover:bg-red-50"
                                        disabled={!canDelete(ep.status)}
                                        onClick={() => setDeleteTarget({ id: ep.id, scene: ep.scene?.name || "Unknown" })}
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </Button>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>

            <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Episode</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete this episode ({deleteTarget?.scene})? This action cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={handleDelete} disabled={deleting} className="bg-red-600 hover:bg-red-700">
                            {deleting ? "Deleting..." : "Delete"}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}

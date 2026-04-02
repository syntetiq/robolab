"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Edit2, MoreVertical, Plus, Trash2 } from "lucide-react";
import SceneDialog from "./SceneDialog";
import { Badge } from "@/components/ui/badge";

export default function ScenesPage() {
    const [scenes, setScenes] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingScene, setEditingScene] = useState<any>(null);

    const showExperimental = process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_SCENES === "1";

    const fetchScenes = async () => {
        setLoading(true);
        try {
            const res = await fetch(showExperimental ? "/api/scenes?includeExperimental=1" : "/api/scenes");
            const data = await res.json();
            setScenes(data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchScenes();
    }, []);

    const handleDelete = async (id: string) => {
        if (!confirm("Are you sure you want to delete this scene?")) return;
        try {
            await fetch(`/api/scenes/${id}`, { method: "DELETE" });
            fetchScenes();
        } catch (e) {
            console.error("Failed to delete", e);
        }
    };

    const openNew = () => {
        setEditingScene(null);
        setDialogOpen(true);
    };

    const openEdit = (scene: any) => {
        setEditingScene(scene);
        setDialogOpen(true);
    };

    return (
        <div className="p-8 max-w-6xl mx-auto">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Scenes</h1>
                    <p className="text-muted-foreground">Manage simulation environments available for episodes.</p>
                </div>
                <Button onClick={openNew}>
                    <Plus className="w-4 h-4 mr-2" />
                    Add Scene
                </Button>
            </div>

            <div className="border rounded-lg overflow-hidden bg-card">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Name</TableHead>
                            <TableHead>Type</TableHead>
                            <TableHead>Stage USD Path</TableHead>
                            <TableHead>Capabilities</TableHead>
                            <TableHead className="w-[80px] text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {loading ? (
                            <TableRow><TableCell colSpan={5} className="text-center py-8">Loading...</TableCell></TableRow>
                        ) : scenes.length === 0 ? (
                            <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground">No scenes found</TableCell></TableRow>
                        ) : scenes.map((scene) => (
                            <TableRow key={scene.id}>
                                <TableCell className="font-medium">{scene.name}</TableCell>
                                <TableCell className="capitalize">{scene.type}</TableCell>
                                <TableCell className="text-xs font-mono truncate max-w-xs" title={scene.stageUsdPath}>
                                    {scene.stageUsdPath}
                                </TableCell>
                                <TableCell>
                                    <div className="flex gap-1 flex-wrap">
                                        {(() => {
                                            try {
                                                const tags = JSON.parse(scene.tags || "[]");
                                                if (!Array.isArray(tags)) return null;
                                                const lower = tags.map((t: any) => String(t).toLowerCase());
                                                return (
                                                    <>
                                                        {lower.includes("experimental") ? <Badge variant="outline" className="text-[10px]">experimental</Badge> : null}
                                                        {lower.includes("fit-validated")
                                                            ? <Badge variant="secondary" className="text-[10px]">fit-validated</Badge>
                                                            : <Badge variant="outline" className="text-[10px]">draft</Badge>}
                                                        {lower.includes("rollout-enabled")
                                                            ? <Badge variant="secondary" className="text-[10px]">rollout-enabled</Badge>
                                                            : null}
                                                    </>
                                                );
                                            } catch {
                                                return null;
                                            }
                                        })()}
                                        {(() => {
                                            try {
                                                const caps = JSON.parse(scene.capabilities);
                                                if (!Array.isArray(caps) || caps.length === 0) return <span className="text-muted-foreground text-xs">None</span>;
                                                return caps.map(c => <Badge key={c} variant="secondary" className="text-[10px]">{c}</Badge>);
                                            } catch {
                                                return <span className="text-red-500 text-xs">Invalid JSON</span>;
                                            }
                                        })()}
                                    </div>
                                </TableCell>
                                <TableCell className="text-right">
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button variant="ghost" className="h-8 w-8 p-0">
                                                <MoreVertical className="h-4 w-4" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end">
                                            <DropdownMenuItem onClick={() => openEdit(scene)}>
                                                <Edit2 className="w-4 h-4 mr-2" />
                                                Edit
                                            </DropdownMenuItem>
                                            <DropdownMenuItem className="text-red-600" onClick={() => handleDelete(scene.id)}>
                                                <Trash2 className="w-4 h-4 mr-2" />
                                                Delete
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>

            <SceneDialog
                open={dialogOpen}
                onOpenChange={setDialogOpen}
                scene={editingScene}
                onSaved={fetchScenes}
            />
        </div>
    );
}

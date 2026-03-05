"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Edit2, MoreVertical, Plus, Trash2 } from "lucide-react";
import ObjectSetDialog from "./ObjectSetDialog";
import { Badge } from "@/components/ui/badge";

export default function ObjectSetsPage() {
    const [objectSets, setObjectSets] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingObjectSet, setEditingObjectSet] = useState<any>(null);

    const fetchObjectSets = async () => {
        setLoading(true);
        try {
            const res = await fetch("/api/object-sets");
            const data = await res.json();
            setObjectSets(data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchObjectSets();
    }, []);

    const handleDelete = async (id: string) => {
        if (!confirm("Are you sure you want to delete this Object Set?")) return;
        try {
            await fetch(`/api/object-sets/${id}`, { method: "DELETE" });
            fetchObjectSets();
        } catch (e) {
            console.error("Failed to delete", e);
        }
    };

    const openNew = () => {
        setEditingObjectSet(null);
        setDialogOpen(true);
    };

    const openEdit = (objectSet: any) => {
        setEditingObjectSet(objectSet);
        setDialogOpen(true);
    };

    return (
        <div className="p-8 max-w-6xl mx-auto">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Object Sets</h1>
                    <p className="text-muted-foreground">Manage object collections across multiple simulation runs.</p>
                </div>
                <Button onClick={openNew}>
                    <Plus className="w-4 h-4 mr-2" />
                    Add Object Set
                </Button>
            </div>

            <div className="border rounded-lg overflow-hidden bg-card">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Name</TableHead>
                            <TableHead>Categories</TableHead>
                            <TableHead>Asset Paths Count</TableHead>
                            <TableHead className="w-[80px] text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {loading ? (
                            <TableRow><TableCell colSpan={4} className="text-center py-8">Loading...</TableCell></TableRow>
                        ) : objectSets.length === 0 ? (
                            <TableRow><TableCell colSpan={4} className="text-center py-8 text-muted-foreground">No object sets found</TableCell></TableRow>
                        ) : objectSets.map((os) => {
                            let assetCount = 0;
                            try { assetCount = JSON.parse(os.assetPaths).length; } catch { }

                            return (
                                <TableRow key={os.id}>
                                    <TableCell className="font-medium">{os.name}</TableCell>
                                    <TableCell>
                                        <div className="flex gap-1 flex-wrap">
                                            {(() => {
                                                try {
                                                    const cats = JSON.parse(os.categories);
                                                    if (!Array.isArray(cats) || cats.length === 0) return <span className="text-muted-foreground text-xs">None</span>;
                                                    return cats.map(c => <Badge key={c} variant="secondary" className="text-[10px]">{c}</Badge>);
                                                } catch {
                                                    return <span className="text-red-500 text-xs">Invalid JSON</span>;
                                                }
                                            })()}
                                        </div>
                                    </TableCell>
                                    <TableCell>{assetCount} Assets</TableCell>
                                    <TableCell className="text-right">
                                        <DropdownMenu>
                                            <DropdownMenuTrigger asChild>
                                                <Button variant="ghost" className="h-8 w-8 p-0">
                                                    <MoreVertical className="h-4 w-4" />
                                                </Button>
                                            </DropdownMenuTrigger>
                                            <DropdownMenuContent align="end">
                                                <DropdownMenuItem onClick={() => openEdit(os)}>
                                                    <Edit2 className="w-4 h-4 mr-2" />
                                                    Edit
                                                </DropdownMenuItem>
                                                <DropdownMenuItem className="text-red-600" onClick={() => handleDelete(os.id)}>
                                                    <Trash2 className="w-4 h-4 mr-2" />
                                                    Delete
                                                </DropdownMenuItem>
                                            </DropdownMenuContent>
                                        </DropdownMenu>
                                    </TableCell>
                                </TableRow>
                            )
                        })}
                    </TableBody>
                </Table>
            </div>

            <ObjectSetDialog
                open={dialogOpen}
                onOpenChange={setDialogOpen}
                objectSet={editingObjectSet}
                onSaved={fetchObjectSets}
            />
        </div>
    );
}

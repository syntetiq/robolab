"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Edit2, MoreVertical, Plus, Trash2 } from "lucide-react";
import LaunchProfileDialog from "./LaunchProfileDialog";
import { Badge } from "@/components/ui/badge";

export default function LaunchProfilesPage() {
    const [profiles, setProfiles] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingProfile, setEditingProfile] = useState<any>(null);

    const fetchProfiles = async () => {
        setLoading(true);
        try {
            const res = await fetch("/api/launch-profiles");
            const data = await res.json();
            setProfiles(data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchProfiles();
    }, []);

    const handleDelete = async (id: string) => {
        if (!confirm("Are you sure you want to delete this Launch Profile?")) return;
        try {
            await fetch(`/api/launch-profiles/${id}`, { method: "DELETE" });
            fetchProfiles();
        } catch (e) {
            console.error("Failed to delete", e);
        }
    };

    const openNew = () => {
        setEditingProfile(null);
        setDialogOpen(true);
    };

    const openEdit = (profile: any) => {
        setEditingProfile(profile);
        setDialogOpen(true);
    };

    return (
        <div className="p-8 max-w-6xl mx-auto">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Launch Profiles</h1>
                    <p className="text-muted-foreground">Manage reusable templates for executing Isaac Sim and ROS commands.</p>
                </div>
                <Button onClick={openNew}>
                    <Plus className="w-4 h-4 mr-2" />
                    Add Profile
                </Button>
            </div>

            <div className="border rounded-lg overflow-hidden bg-card">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Name</TableHead>
                            <TableHead>Runner Mode</TableHead>
                            <TableHead>Isaac Template</TableHead>
                            <TableHead>rosbag Template</TableHead>
                            <TableHead className="w-[80px] text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {loading ? (
                            <TableRow><TableCell colSpan={5} className="text-center py-8">Loading...</TableCell></TableRow>
                        ) : profiles.length === 0 ? (
                            <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground">No launch profiles found</TableCell></TableRow>
                        ) : profiles.map((p) => (
                            <TableRow key={p.id}>
                                <TableCell className="font-medium">{p.name}</TableCell>
                                <TableCell><Badge variant="outline">{p.runnerMode}</Badge></TableCell>
                                <TableCell className="font-mono text-[10px] truncate max-w-[200px]" title={p.isaacLaunchTemplate}>
                                    {p.isaacLaunchTemplate || <span className="text-muted-foreground">None</span>}
                                </TableCell>
                                <TableCell className="font-mono text-[10px] truncate max-w-[200px]" title={p.rosbagLaunchTemplate}>
                                    {p.rosbagLaunchTemplate || <span className="text-muted-foreground">None</span>}
                                </TableCell>
                                <TableCell className="text-right">
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button variant="ghost" className="h-8 w-8 p-0">
                                                <MoreVertical className="h-4 w-4" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end">
                                            <DropdownMenuItem onClick={() => openEdit(p)}>
                                                <Edit2 className="w-4 h-4 mr-2" />
                                                Edit
                                            </DropdownMenuItem>
                                            <DropdownMenuItem className="text-red-600" onClick={() => handleDelete(p.id)}>
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

            <LaunchProfileDialog
                open={dialogOpen}
                onOpenChange={setDialogOpen}
                profile={editingProfile}
                onSaved={fetchProfiles}
            />
        </div>
    );
}

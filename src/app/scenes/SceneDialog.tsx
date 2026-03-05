"use client";

import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

export default function SceneDialog({
    open,
    onOpenChange,
    scene,
    onSaved
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    scene?: any;
    onSaved: () => void;
}) {
    const [formData, setFormData] = useState({
        name: "",
        type: "office",
        stageUsdPath: "",
        mapPath: "",
        robotSpawnPose: '{"x":0,"y":0,"z":0,"yaw":0}',
        capabilities: "[]",
        tags: "[]",
        notes: ""
    });
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (open) {
            if (scene) {
                setFormData({
                    name: scene.name,
                    type: scene.type,
                    stageUsdPath: scene.stageUsdPath,
                    mapPath: scene.mapPath || "",
                    robotSpawnPose: scene.robotSpawnPose,
                    capabilities: scene.capabilities,
                    tags: scene.tags,
                    notes: scene.notes
                });
            } else {
                setFormData({
                    name: "",
                    type: "office",
                    stageUsdPath: "",
                    mapPath: "",
                    robotSpawnPose: '{"x":0,"y":0,"z":0,"yaw":0}',
                    capabilities: "[]",
                    tags: "[]",
                    notes: ""
                });
            }
        }
    }, [open, scene]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        try {
            const url = scene ? `/api/scenes/${scene.id}` : "/api/scenes";
            const method = scene ? "PUT" : "POST";
            const res = await fetch(url, {
                method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(formData)
            });
            if (!res.ok) throw new Error("Failed to save scene");
            onSaved();
            onOpenChange(false);
        } catch (error: any) {
            alert(error.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>{scene ? "Edit Scene" : "New Scene"}</DialogTitle>
                    <DialogDescription>Define a simulation scene to be used in episodes.</DialogDescription>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4 py-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label>Name</Label>
                            <Input
                                required
                                value={formData.name}
                                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Type</Label>
                            <Select
                                value={formData.type}
                                onValueChange={(val) => setFormData({ ...formData, type: val })}
                            >
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="office">Office</SelectItem>
                                    <SelectItem value="home">Home</SelectItem>
                                    <SelectItem value="custom">Custom</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2 col-span-2">
                            <Label>Stage USD Path</Label>
                            <Input
                                required
                                value={formData.stageUsdPath}
                                onChange={(e) => setFormData({ ...formData, stageUsdPath: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2 col-span-2">
                            <Label>Map Path (Optional)</Label>
                            <Input
                                value={formData.mapPath}
                                onChange={(e) => setFormData({ ...formData, mapPath: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2 col-span-2">
                            <Label>Robot Spawn Pose (JSON)</Label>
                            <Input
                                value={formData.robotSpawnPose}
                                onChange={(e) => setFormData({ ...formData, robotSpawnPose: e.target.value })}
                                className="font-mono text-xs"
                            />
                        </div>
                        <div className="space-y-2 col-span-2">
                            <Label>Capabilities (JSON array)</Label>
                            <Input
                                value={formData.capabilities}
                                onChange={(e) => setFormData({ ...formData, capabilities: e.target.value })}
                                className="font-mono text-xs"
                                placeholder='e.g. ["hasFridge", "hasSink"]'
                            />
                        </div>
                        <div className="space-y-2 col-span-2">
                            <Label>Tags (JSON array)</Label>
                            <Input
                                value={formData.tags}
                                onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
                                className="font-mono text-xs"
                                placeholder='e.g. ["office", "test"]'
                            />
                        </div>
                        <div className="space-y-2 col-span-2">
                            <Label>Notes</Label>
                            <Textarea
                                value={formData.notes}
                                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
                        <Button type="submit" disabled={loading}>{loading ? "Saving..." : "Save Scene"}</Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

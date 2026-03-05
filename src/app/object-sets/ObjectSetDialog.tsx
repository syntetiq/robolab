"use client";

import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function ObjectSetDialog({
    open,
    onOpenChange,
    objectSet,
    onSaved
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    objectSet?: any;
    onSaved: () => void;
}) {
    const [formData, setFormData] = useState({
        name: "",
        categories: "[]",
        assetPaths: "[]",
        notes: ""
    });
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (open) {
            if (objectSet) {
                setFormData({
                    name: objectSet.name,
                    categories: objectSet.categories,
                    assetPaths: objectSet.assetPaths,
                    notes: objectSet.notes
                });
            } else {
                setFormData({
                    name: "",
                    categories: "[]",
                    assetPaths: "[]",
                    notes: ""
                });
            }
        }
    }, [open, objectSet]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        try {
            const url = objectSet ? `/api/object-sets/${objectSet.id}` : "/api/object-sets";
            const method = objectSet ? "PUT" : "POST";
            const res = await fetch(url, {
                method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(formData)
            });
            if (!res.ok) throw new Error("Failed to save object set");
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
                    <DialogTitle>{objectSet ? "Edit Object Set" : "New Object Set"}</DialogTitle>
                    <DialogDescription>Define a set of objects available for episodes.</DialogDescription>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4 py-4">
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label>Name</Label>
                            <Input
                                required
                                value={formData.name}
                                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Categories (JSON array)</Label>
                            <Input
                                value={formData.categories}
                                onChange={(e) => setFormData({ ...formData, categories: e.target.value })}
                                className="font-mono text-xs"
                                placeholder='e.g. ["mugs", "bottles"]'
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Asset Paths (JSON array)</Label>
                            <Textarea
                                value={formData.assetPaths}
                                onChange={(e) => setFormData({ ...formData, assetPaths: e.target.value })}
                                className="font-mono text-xs h-32"
                                placeholder='e.g. ["/Props/mugs/mug_01.usd"]'
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Notes</Label>
                            <Textarea
                                value={formData.notes}
                                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
                        <Button type="submit" disabled={loading}>{loading ? "Saving..." : "Save Object Set"}</Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

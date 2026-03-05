"use client";

import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

export default function LaunchProfileDialog({
    open,
    onOpenChange,
    profile,
    onSaved
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    profile?: any;
    onSaved: () => void;
}) {
    const [formData, setFormData] = useState({
        name: "",
        runnerMode: "SSH_RUNNER",
        isaacLaunchTemplate: "",
        rosbagLaunchTemplate: "",
        teleopLaunchTemplate: "",
        stopTemplate: "",
        environmentOverrides: "{}"
    });
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (open) {
            if (profile) {
                setFormData({
                    name: profile.name,
                    runnerMode: profile.runnerMode,
                    isaacLaunchTemplate: profile.isaacLaunchTemplate,
                    rosbagLaunchTemplate: profile.rosbagLaunchTemplate,
                    teleopLaunchTemplate: profile.teleopLaunchTemplate,
                    stopTemplate: profile.stopTemplate,
                    environmentOverrides: profile.environmentOverrides
                });
            } else {
                setFormData({
                    name: "",
                    runnerMode: "SSH_RUNNER",
                    isaacLaunchTemplate: "",
                    rosbagLaunchTemplate: "",
                    teleopLaunchTemplate: "",
                    stopTemplate: "",
                    environmentOverrides: "{}"
                });
            }
        }
    }, [open, profile]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        try {
            const url = profile ? `/api/launch-profiles/${profile.id}` : "/api/launch-profiles";
            const method = profile ? "PUT" : "POST";
            const res = await fetch(url, {
                method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(formData)
            });
            if (!res.ok) throw new Error("Failed to save launch profile");
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
                    <DialogTitle>{profile ? "Edit Launch Profile" : "New Launch Profile"}</DialogTitle>
                    <DialogDescription>Define command templates for launching various components on the runner.</DialogDescription>
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
                            <Label>Runner Mode</Label>
                            <Select
                                value={formData.runnerMode}
                                onValueChange={(val) => setFormData({ ...formData, runnerMode: val })}
                            >
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="LOCAL_RUNNER">Local Machine</SelectItem>
                                    <SelectItem value="SSH_RUNNER">Remote Server (SSH)</SelectItem>
                                    <SelectItem value="AGENT_RUNNER">Agent Orchestrator</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Isaac Launch Template</Label>
                            <Input
                                value={formData.isaacLaunchTemplate}
                                onChange={(e) => setFormData({ ...formData, isaacLaunchTemplate: e.target.value })}
                                className="font-mono text-xs"
                                placeholder='./isaac-sim.sh --allow-root'
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>rosbag Launch Template</Label>
                            <Input
                                value={formData.rosbagLaunchTemplate}
                                onChange={(e) => setFormData({ ...formData, rosbagLaunchTemplate: e.target.value })}
                                className="font-mono text-xs"
                                placeholder='ros2 bag record -o {BAG_PATH} {TOPICS}'
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Teleop Launch Template</Label>
                            <Input
                                value={formData.teleopLaunchTemplate}
                                onChange={(e) => setFormData({ ...formData, teleopLaunchTemplate: e.target.value })}
                                className="font-mono text-xs"
                                placeholder='ros2 launch teleop_twist_joy teleop.launch.py'
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Stop Template</Label>
                            <Input
                                value={formData.stopTemplate}
                                onChange={(e) => setFormData({ ...formData, stopTemplate: e.target.value })}
                                className="font-mono text-xs"
                                placeholder='pkill -f isaac-sim'
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Environment Overrides (JSON)</Label>
                            <Textarea
                                value={formData.environmentOverrides}
                                onChange={(e) => setFormData({ ...formData, environmentOverrides: e.target.value })}
                                className="font-mono text-xs"
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
                        <Button type="submit" disabled={loading}>{loading ? "Saving..." : "Save Profile"}</Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

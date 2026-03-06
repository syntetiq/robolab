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
        scriptName: "data_collector_tiago.py",
        environmentUsd: "C:\\RoboLab_Data\\scenes\\Small_House_Interactive.usd",
        enableWebRTC: false,
        enableVrTeleop: false,
        enableMoveIt: false,
        robotPovCameraPrim: "/World/Tiago",
        ros2SetupCommand: "",
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
                    scriptName: profile.scriptName || "data_collector_tiago.py",
                    environmentUsd: profile.environmentUsd || "C:\\RoboLab_Data\\scenes\\Small_House_Interactive.usd",
                    enableWebRTC: !!profile.enableWebRTC,
                    enableVrTeleop: !!profile.enableVrTeleop,
                    enableMoveIt: !!profile.enableMoveIt,
                    robotPovCameraPrim: profile.robotPovCameraPrim || "/World/Tiago",
                    ros2SetupCommand: profile.ros2SetupCommand || "",
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
                    scriptName: "data_collector_tiago.py",
                    environmentUsd: "C:\\RoboLab_Data\\scenes\\Small_House_Interactive.usd",
                    enableWebRTC: false,
                    enableVrTeleop: false,
                    enableMoveIt: false,
                    robotPovCameraPrim: "/World/Tiago",
                    ros2SetupCommand: "",
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
                            <Label>Runner Script Name</Label>
                            <Input
                                value={formData.scriptName}
                                onChange={(e) => setFormData({ ...formData, scriptName: e.target.value })}
                                className="font-mono text-xs"
                                placeholder="data_collector_tiago.py"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Environment USD Path</Label>
                            <Input
                                value={formData.environmentUsd}
                                onChange={(e) => setFormData({ ...formData, environmentUsd: e.target.value })}
                                className="font-mono text-xs"
                                placeholder="C:\\RoboLab_Data\\scenes\\Small_House_Interactive.usd"
                            />
                        </div>
                        <div className="flex items-center space-x-2">
                            <input
                                id="enableWebRTC"
                                type="checkbox"
                                checked={formData.enableWebRTC}
                                onChange={(e) => setFormData({ ...formData, enableWebRTC: e.target.checked })}
                            />
                            <Label htmlFor="enableWebRTC">Enable WebRTC livestream</Label>
                        </div>
                        <div className="flex items-center space-x-2">
                            <input
                                id="enableVrTeleop"
                                type="checkbox"
                                checked={formData.enableVrTeleop}
                                onChange={(e) => setFormData({ ...formData, enableVrTeleop: e.target.checked })}
                            />
                            <Label htmlFor="enableVrTeleop">Enable VR teleoperation mode (Vive/OpenXR)</Label>
                        </div>
                        <div className="flex items-center space-x-2">
                            <input
                                id="enableMoveIt"
                                type="checkbox"
                                checked={formData.enableMoveIt}
                                onChange={(e) => setFormData({ ...formData, enableMoveIt: e.target.checked })}
                            />
                            <Label htmlFor="enableMoveIt">Enable MoveIt integration mode</Label>
                        </div>
                        <div className="space-y-2">
                            <Label>Robot POV Camera Prim</Label>
                            <Input
                                value={formData.robotPovCameraPrim}
                                onChange={(e) => setFormData({ ...formData, robotPovCameraPrim: e.target.value })}
                                className="font-mono text-xs"
                                placeholder="/World/Tiago/head_2_link/POVCamera"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>ROS2 Setup Command Override</Label>
                            <Input
                                value={formData.ros2SetupCommand}
                                onChange={(e) => setFormData({ ...formData, ros2SetupCommand: e.target.value })}
                                className="font-mono text-xs"
                                placeholder='call C:\ros2\local_setup.bat'
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Isaac Launch Template</Label>
                            <Input
                                value={formData.isaacLaunchTemplate}
                                onChange={(e) => setFormData({ ...formData, isaacLaunchTemplate: e.target.value })}
                                className="font-mono text-xs"
                                placeholder='"C:\\Users\\max\\Documents\\IsaacSim\\python.bat" "<project>\\scripts\\run_episode.py" --output_dir "C:\\RoboLab_Data\\episodes\\{EPISODE_ID}"'
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
                                placeholder='taskkill /F /IM python.exe /T'
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

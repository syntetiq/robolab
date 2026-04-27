"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Trash2, GripVertical } from "lucide-react";
import { HelpTooltip } from "@/components/HelpTooltip";

const TASK_TYPES = [
    { value: "navigate_to", label: "Navigate To" },
    { value: "pick_object", label: "Pick Object" },
    { value: "carry_to", label: "Carry To" },
    { value: "place_object", label: "Place Object" },
    { value: "open_door", label: "Open Door" },
    { value: "close_door", label: "Close Door" },
];

const TASK_DEFAULTS: Record<string, Record<string, unknown>> = {
    navigate_to: { target_xy: [0, 0], tolerance_m: 0.25, timeout_s: 50, drive_speed_ms: 0.4 },
    pick_object: { object_usd_path: "", grasp_mode: "top", lift_height_m: 0.20, timeout_s: 90, approach_clearance_m: 0.13 },
    carry_to: { destination_xy: [0, 0], carry_height_m: 0.20, tolerance_m: 0.20, timeout_s: 40, drive_speed_ms: 0.15 },
    place_object: { release_height_m: 0.05, timeout_s: 10, placement_top_z: 0.80 },
    open_door: { handle_usd_path: "", target_angle_deg: 90, timeout_s: 90, pull_speed_ms: 0.12 },
    close_door: { handle_usd_path: "", timeout_s: 90, push_speed_ms: 0.10 },
};

interface TaskStep {
    id: string;
    type: string;
    annotation: string;
    params: Record<string, unknown>;
}

function generateId(type: string, index: number): string {
    return `T${index + 1}_${type}`;
}

export default function TaskEditorDialog({
    open,
    onOpenChange,
    onSaved,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSaved: () => void;
}) {
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [duration, setDuration] = useState(300);
    const [sceneFeatures, setSceneFeatures] = useState({ fridge: true, sink: true, plate_fruit: true });
    const [sensors, setSensors] = useState({ robot_head_camera: true, wrist_camera: true, external_camera: true, replicator_depth: true, contact_sensors: true });
    const [tasks, setTasks] = useState<TaskStep[]>([]);
    const [saving, setSaving] = useState(false);

    const addTask = (type: string) => {
        const idx = tasks.length;
        setTasks([...tasks, {
            id: generateId(type, idx),
            type,
            annotation: "",
            params: { ...TASK_DEFAULTS[type] },
        }]);
    };

    const removeTask = (index: number) => {
        const updated = tasks.filter((_, i) => i !== index).map((t, i) => ({
            ...t,
            id: generateId(t.type, i),
        }));
        setTasks(updated);
    };

    const updateTaskParam = (index: number, key: string, value: unknown) => {
        const updated = [...tasks];
        updated[index] = { ...updated[index], params: { ...updated[index].params, [key]: value } };
        setTasks(updated);
    };

    const updateTaskAnnotation = (index: number, annotation: string) => {
        const updated = [...tasks];
        updated[index] = { ...updated[index], annotation };
        setTasks(updated);
    };

    const handleSave = async () => {
        if (!name.trim() || tasks.length === 0) return;
        setSaving(true);
        try {
            const config = {
                episode_name: name.trim(),
                description: description.trim(),
                kitchen_scene: "fixed",
                simulation_duration_s: duration,
                scene: sceneFeatures,
                robot: {
                    start_pose: [0.0, 0.0, 90],
                    model: "heavy",
                    gripper_length_m: 0.10,
                    robot_profile: "config/robots/tiago_heavy.yaml",
                },
                global: {
                    drive_speed_ms: 0.3,
                    approach_clearance_m: 0.13,
                    torso_speed: 0.05,
                    on_task_failure: "abort",
                },
                sensors,
                tasks: tasks.map((t) => ({
                    id: t.id,
                    type: t.type,
                    ...t.params,
                    ...(t.annotation ? { annotation: t.annotation } : {}),
                })),
            };

            const res = await fetch("/api/experiments", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(config),
            });
            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.error || "Failed to save");
            }
            onSaved();
            onOpenChange(false);
            // Reset
            setName("");
            setDescription("");
            setDuration(300);
            setTasks([]);
        } catch (e: any) {
            alert(e.message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>New Task Config</DialogTitle>
                    <DialogDescription>
                        Define a task sequence for automated or teleoperated episodes.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-2">
                    {/* Metadata */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label>Task Name</Label>
                            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="mug_to_fridge" />
                        </div>
                        <div className="space-y-2">
                            <Label>Duration (seconds)</Label>
                            <Input type="number" value={duration} onChange={(e) => setDuration(parseInt(e.target.value) || 300)} />
                        </div>
                    </div>
                    <div className="space-y-2">
                        <Label>Description</Label>
                        <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Pick mug from table, carry to fridge, place inside" />
                    </div>

                    {/* Scene features */}
                    <div className="space-y-2">
                        <Label>Scene Features <HelpTooltip content="Interactive assets available in the scene. Disable to exclude from the environment." /></Label>
                        <div className="flex gap-4">
                            {(["fridge", "sink", "plate_fruit"] as const).map((feat) => (
                                <label key={feat} className="flex items-center gap-1.5 text-sm">
                                    <input
                                        type="checkbox"
                                        checked={sceneFeatures[feat]}
                                        onChange={(e) => setSceneFeatures({ ...sceneFeatures, [feat]: e.target.checked })}
                                    />
                                    {feat.replace("_", " ")}
                                </label>
                            ))}
                        </div>
                    </div>

                    {/* Sensors */}
                    <div className="space-y-2">
                        <Label>Sensors <HelpTooltip content="Which data streams to record. Enable for vision-based training (RGB, Depth) or manipulation (contact sensors)." /></Label>
                        <div className="flex gap-4 flex-wrap">
                            {(Object.keys(sensors) as (keyof typeof sensors)[]).map((s) => (
                                <label key={s} className="flex items-center gap-1.5 text-sm">
                                    <input
                                        type="checkbox"
                                        checked={sensors[s]}
                                        onChange={(e) => setSensors({ ...sensors, [s]: e.target.checked })}
                                    />
                                    {s.replace(/_/g, " ")}
                                </label>
                            ))}
                        </div>
                    </div>

                    {/* Task Sequence */}
                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <Label>Task Sequence ({tasks.length} steps)</Label>
                            <Select onValueChange={(v) => addTask(v)}>
                                <SelectTrigger className="w-[180px]">
                                    <SelectValue placeholder="+ Add step" />
                                </SelectTrigger>
                                <SelectContent>
                                    {TASK_TYPES.map((t) => (
                                        <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        {tasks.length === 0 && (
                            <p className="text-sm text-muted-foreground py-4 text-center border rounded-md">
                                No tasks yet. Add steps using the dropdown above.
                            </p>
                        )}

                        <div className="space-y-3">
                            {tasks.map((task, idx) => (
                                <div key={idx} className="border rounded-md p-3 space-y-2 bg-muted/30">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <GripVertical className="w-4 h-4 text-muted-foreground" />
                                            <span className="font-mono text-xs text-muted-foreground">{task.id}</span>
                                            <span className="text-sm font-medium capitalize">{task.type.replace(/_/g, " ")}</span>
                                        </div>
                                        <Button variant="ghost" size="sm" onClick={() => removeTask(idx)}>
                                            <Trash2 className="w-3.5 h-3.5 text-red-500" />
                                        </Button>
                                    </div>

                                    {/* Type-specific params */}
                                    <TaskParamEditor task={task} index={idx} onUpdate={updateTaskParam} />

                                    <div>
                                        <Input
                                            className="text-xs"
                                            placeholder="Annotation (optional description)"
                                            value={task.annotation}
                                            onChange={(e) => updateTaskAnnotation(idx, e.target.value)}
                                        />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
                    <Button onClick={handleSave} disabled={saving || !name.trim() || tasks.length === 0}>
                        {saving ? "Saving..." : "Save Task Config"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function TaskParamEditor({ task, index, onUpdate }: {
    task: TaskStep;
    index: number;
    onUpdate: (index: number, key: string, value: unknown) => void;
}) {
    const p = task.params;
    const set = (key: string, value: unknown) => onUpdate(index, key, value);

    switch (task.type) {
        case "navigate_to":
            return (
                <div className="grid grid-cols-4 gap-2">
                    <div>
                        <Label className="text-xs">Target X</Label>
                        <Input type="number" step="0.1" className="text-xs" value={(p.target_xy as number[])?.[0] ?? 0}
                            onChange={(e) => set("target_xy", [parseFloat(e.target.value) || 0, (p.target_xy as number[])?.[1] ?? 0])} />
                    </div>
                    <div>
                        <Label className="text-xs">Target Y</Label>
                        <Input type="number" step="0.1" className="text-xs" value={(p.target_xy as number[])?.[1] ?? 0}
                            onChange={(e) => set("target_xy", [(p.target_xy as number[])?.[0] ?? 0, parseFloat(e.target.value) || 0])} />
                    </div>
                    <div>
                        <Label className="text-xs">Tolerance (m)</Label>
                        <Input type="number" step="0.05" className="text-xs" value={(p.tolerance_m as number) ?? 0.25}
                            onChange={(e) => set("tolerance_m", parseFloat(e.target.value) || 0.25)} />
                    </div>
                    <div>
                        <Label className="text-xs">Timeout (s)</Label>
                        <Input type="number" className="text-xs" value={(p.timeout_s as number) ?? 50}
                            onChange={(e) => set("timeout_s", parseInt(e.target.value) || 50)} />
                    </div>
                </div>
            );
        case "pick_object":
            return (
                <div className="space-y-2">
                    <div>
                        <Label className="text-xs">Object USD Path</Label>
                        <Input className="text-xs font-mono" value={(p.object_usd_path as string) ?? ""}
                            onChange={(e) => set("object_usd_path", e.target.value)}
                            placeholder="/World/Kitchen/Objects/Mug" />
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                        <div>
                            <Label className="text-xs">Grasp Mode</Label>
                            <Select value={(p.grasp_mode as string) ?? "top"} onValueChange={(v) => set("grasp_mode", v)}>
                                <SelectTrigger className="text-xs"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="top">Top</SelectItem>
                                    <SelectItem value="side">Side</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label className="text-xs">Lift Height (m)</Label>
                            <Input type="number" step="0.05" className="text-xs" value={(p.lift_height_m as number) ?? 0.20}
                                onChange={(e) => set("lift_height_m", parseFloat(e.target.value) || 0.20)} />
                        </div>
                        <div>
                            <Label className="text-xs">Timeout (s)</Label>
                            <Input type="number" className="text-xs" value={(p.timeout_s as number) ?? 90}
                                onChange={(e) => set("timeout_s", parseInt(e.target.value) || 90)} />
                        </div>
                    </div>
                </div>
            );
        case "carry_to":
            return (
                <div className="grid grid-cols-4 gap-2">
                    <div>
                        <Label className="text-xs">Dest X</Label>
                        <Input type="number" step="0.1" className="text-xs" value={(p.destination_xy as number[])?.[0] ?? 0}
                            onChange={(e) => set("destination_xy", [parseFloat(e.target.value) || 0, (p.destination_xy as number[])?.[1] ?? 0])} />
                    </div>
                    <div>
                        <Label className="text-xs">Dest Y</Label>
                        <Input type="number" step="0.1" className="text-xs" value={(p.destination_xy as number[])?.[1] ?? 0}
                            onChange={(e) => set("destination_xy", [(p.destination_xy as number[])?.[0] ?? 0, parseFloat(e.target.value) || 0])} />
                    </div>
                    <div>
                        <Label className="text-xs">Carry Height (m)</Label>
                        <Input type="number" step="0.05" className="text-xs" value={(p.carry_height_m as number) ?? 0.20}
                            onChange={(e) => set("carry_height_m", parseFloat(e.target.value) || 0.20)} />
                    </div>
                    <div>
                        <Label className="text-xs">Timeout (s)</Label>
                        <Input type="number" className="text-xs" value={(p.timeout_s as number) ?? 40}
                            onChange={(e) => set("timeout_s", parseInt(e.target.value) || 40)} />
                    </div>
                </div>
            );
        case "place_object":
            return (
                <div className="grid grid-cols-3 gap-2">
                    <div>
                        <Label className="text-xs">Placement Z (m)</Label>
                        <Input type="number" step="0.05" className="text-xs" value={(p.placement_top_z as number) ?? 0.80}
                            onChange={(e) => set("placement_top_z", parseFloat(e.target.value) || 0.80)} />
                    </div>
                    <div>
                        <Label className="text-xs">Release Height (m)</Label>
                        <Input type="number" step="0.01" className="text-xs" value={(p.release_height_m as number) ?? 0.05}
                            onChange={(e) => set("release_height_m", parseFloat(e.target.value) || 0.05)} />
                    </div>
                    <div>
                        <Label className="text-xs">Timeout (s)</Label>
                        <Input type="number" className="text-xs" value={(p.timeout_s as number) ?? 10}
                            onChange={(e) => set("timeout_s", parseInt(e.target.value) || 10)} />
                    </div>
                </div>
            );
        case "open_door":
        case "close_door":
            return (
                <div className="space-y-2">
                    <div>
                        <Label className="text-xs">Handle USD Path</Label>
                        <Input className="text-xs font-mono" value={(p.handle_usd_path as string) ?? ""}
                            onChange={(e) => set("handle_usd_path", e.target.value)}
                            placeholder="/World/Kitchen/Furniture/Fridge/Door/Handle" />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <Label className="text-xs">{task.type === "open_door" ? "Target Angle" : "Max Angle"} (deg)</Label>
                            <Input type="number" className="text-xs"
                                value={(p.target_angle_deg as number) ?? (task.type === "open_door" ? 90 : 10)}
                                onChange={(e) => set("target_angle_deg", parseInt(e.target.value) || 90)} />
                        </div>
                        <div>
                            <Label className="text-xs">Timeout (s)</Label>
                            <Input type="number" className="text-xs" value={(p.timeout_s as number) ?? 90}
                                onChange={(e) => set("timeout_s", parseInt(e.target.value) || 90)} />
                        </div>
                    </div>
                </div>
            );
        default:
            return null;
    }
}

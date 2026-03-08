"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { HelpTooltip } from "@/components/HelpTooltip";

const TASKS = [
    "pick_place_sink",
    "pick_place_fridge",
    "pick_place_dishwasher",
    "open_close_fridge",
    "open_close_dishwasher"
];

const SENSORS = [
    "RGB", "Depth", "CameraInfo", "PointCloud2", "GT Poses", "JointStates"
];

const TASK_PRESETS: Record<string, { label: string; tasks: string[]; sensors: string[] }> = {
    home_assist_full: {
        label: "Home Assist (all 5 tasks)",
        tasks: [...TASKS],
        sensors: [...SENSORS],
    },
    pick_place_pack: {
        label: "Pick & Place trio (sink/fridge/dishwasher)",
        tasks: ["pick_place_sink", "pick_place_fridge", "pick_place_dishwasher"],
        sensors: [...SENSORS],
    },
    door_manipulation_pack: {
        label: "Door manipulation (fridge + dishwasher)",
        tasks: ["open_close_fridge", "open_close_dishwasher"],
        sensors: [...SENSORS],
    },
};

const DEFAULT_SAFE_PROFILE_NAME = "Default Safe Live Teleop";

export default function NewEpisodeWizard() {
    const router = useRouter();
    const [step, setStep] = useState(1);
    const [loadingConfig, setLoadingConfig] = useState(true);

    const [config, setConfig] = useState<any>(null);
    const [scenes, setScenes] = useState<any[]>([]);
    const [objectSets, setObjectSets] = useState<any[]>([]);
    const [profiles, setProfiles] = useState<any[]>([]);

    const [formData, setFormData] = useState({
        sceneId: "",
        objectSetId: "",
        launchProfileId: "",
        tasks: [] as string[],
        sensors: [] as string[],
        seed: "42",
        durationSec: "60",
        notes: ""
    });

    const [submitting, setSubmitting] = useState(false);
    const [preset, setPreset] = useState<string>("");

    useEffect(() => {
        Promise.all([
            fetch("/api/config").then(r => r.json()),
            fetch("/api/scenes").then(r => r.json()),
            fetch("/api/object-sets").then(r => r.json()),
            fetch("/api/launch-profiles").then(r => r.json())
        ]).then(([configData, scenesData, objectSetsData, profilesData]) => {
            setConfig(configData);
            setScenes(scenesData);
            setObjectSets(objectSetsData);
            setProfiles(profilesData);
            const defaultProfile =
                (profilesData || []).find((p: any) => p?.name === DEFAULT_SAFE_PROFILE_NAME && p?.enabled !== false) ||
                (profilesData || []).find((p: any) => p?.runnerMode === "LOCAL_RUNNER" && p?.enableWebRTC === true && p?.enabled !== false) ||
                (profilesData || []).find((p: any) => p?.enableWebRTC === true && p?.enabled !== false);
            if (defaultProfile?.id) {
                setFormData((prev) => ({ ...prev, launchProfileId: String(defaultProfile.id) }));
            }
            setLoadingConfig(false);
        });
    }, []);

    const handleNext = () => setStep(s => Math.min(s + 1, 6));
    const handlePrev = () => setStep(s => Math.max(s - 1, 1));

    const toggleTask = (task: string) => {
        setFormData(prev => ({
            ...prev,
            tasks: prev.tasks.includes(task) ? prev.tasks.filter(t => t !== task) : [...prev.tasks, task]
        }));
    };

    const toggleSensor = (sensor: string) => {
        setFormData(prev => ({
            ...prev,
            sensors: prev.sensors.includes(sensor) ? prev.sensors.filter(s => s !== sensor) : [...prev.sensors, sensor]
        }));
    };

    const handleSubmit = async () => {
        setSubmitting(true);
        try {
            const payload = {
                sceneId: formData.sceneId,
                objectSetId: formData.objectSetId || null,
                launchProfileId: formData.launchProfileId || null,
                tasks: JSON.stringify(formData.tasks),
                sensors: JSON.stringify(formData.sensors),
                seed: parseInt(formData.seed, 10),
                durationSec: parseInt(formData.durationSec, 10),
                notes: formData.notes
            };

            const res = await fetch("/api/episodes", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!res.ok) throw new Error("Failed to create episode");
            const created = await res.json();
            router.push(`/episodes/${created.id}`);
        } catch (e: any) {
            alert(e.message);
            setSubmitting(false);
        }
    };

    const applyTaskPreset = (presetKey: string) => {
        const spec = TASK_PRESETS[presetKey];
        if (!spec) return;
        setPreset(presetKey);
        setFormData((prev) => ({
            ...prev,
            tasks: [...spec.tasks],
            sensors: [...spec.sensors],
        }));
    };

    const selectedScene = scenes.find(s => s.id === formData.sceneId);
    const selectedObjectSet = objectSets.find(o => o.id === formData.objectSetId);
    const selectedProfile = profiles.find(p => p.id === formData.launchProfileId);

    if (loadingConfig) return <div className="p-8 text-center">Loading options...</div>;

    return (
        <div className="max-w-3xl mx-auto p-8">
            <div className="mb-8">
                <h1 className="text-3xl font-bold tracking-tight mb-2">Create New Episode</h1>
                <div className="flex gap-2">
                    {[1, 2, 3, 4, 5, 6].map(i => (
                        <div key={i} className={`h-2 flex-1 rounded-full ${step >= i ? 'bg-primary' : 'bg-muted'}`} />
                    ))}
                </div>
                <p className="text-muted-foreground text-sm mt-2">Step {step} of 6</p>
            </div>

            <Card className="mb-6 min-h-[400px]">
                <CardHeader>
                    <CardTitle>
                        {step === 1 && "Select Scene"}
                        {step === 2 && "Select Object Set & Profile"}
                        {step === 3 && "Select Tasks"}
                        {step === 4 && "Select Sensors"}
                        {step === 5 && "Episode Params"}
                        {step === 6 && "Review Execution Plan"}
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    {step === 1 && (
                        <div className="space-y-4">
                            <Label className="flex items-center">Target Scene <HelpTooltip content="The 3D environment (USD file) where the simulation will take place." /></Label>
                            <Select value={formData.sceneId} onValueChange={(val) => setFormData(p => ({ ...p, sceneId: val }))}>
                                <SelectTrigger><SelectValue placeholder="Select a scene" /></SelectTrigger>
                                <SelectContent>
                                    {scenes.map(s => <SelectItem key={s.id} value={s.id}>{s.name} ({s.type})</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="space-y-6">
                            <div className="space-y-4">
                                <Label className="flex items-center">Object Set (Optional) <HelpTooltip content="A collection of 3D props (e.g., mugs, blocks) to spawn into the scene." /></Label>
                                <Select value={formData.objectSetId} onValueChange={(val) => setFormData(p => ({ ...p, objectSetId: val }))}>
                                    <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="none">None</SelectItem>
                                        {objectSets.map(o => <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="space-y-4">
                                <Label className="flex items-center">Launch Profile (Optional) <HelpTooltip content="Select a preset configuration that overrides default execution parameters (e.g., to use a specific agent or SSH target)." /></Label>
                                <Select value={formData.launchProfileId} onValueChange={(val) => setFormData(p => ({ ...p, launchProfileId: val }))}>
                                    <SelectTrigger><SelectValue placeholder="Use default commands" /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="none">Use default commands</SelectItem>
                                        {profiles.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                                <p className="text-xs text-muted-foreground mt-1">
                                    Overrides default runner scripts with saved templates.
                                </p>
                            </div>
                        </div>
                    )}

                    {step === 3 && (
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <Label>Task preset</Label>
                                <Select value={preset} onValueChange={applyTaskPreset}>
                                    <SelectTrigger><SelectValue placeholder="Select preset (optional)" /></SelectTrigger>
                                    <SelectContent>
                                        {Object.entries(TASK_PRESETS).map(([key, spec]) => (
                                            <SelectItem key={key} value={key}>{spec.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                {TASKS.map(task => (
                                    <div key={task} className="flex flex-row items-center space-x-3 space-y-0 rounded-md border p-4">
                                        <Checkbox
                                            checked={formData.tasks.includes(task)}
                                            onCheckedChange={() => toggleTask(task)}
                                        />
                                        <div className="space-y-1 leading-none">
                                            <Label className="font-medium cursor-pointer" onClick={() => toggleTask(task)}>{task}</Label>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {step === 4 && (
                        <div className="grid grid-cols-2 gap-4">
                            {SENSORS.map(sensor => (
                                <div key={sensor} className="flex flex-row items-center space-x-3 space-y-0 rounded-md border p-4">
                                    <Checkbox
                                        checked={formData.sensors.includes(sensor)}
                                        onCheckedChange={() => toggleSensor(sensor)}
                                    />
                                    <div className="space-y-1 leading-none">
                                        <Label className="font-medium cursor-pointer" onClick={() => toggleSensor(sensor)}>{sensor}</Label>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {step === 5 && (
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label className="flex items-center">Random Seed <HelpTooltip content="Integer seed used for deterministic physical randomization across the scene." /></Label>
                                    <Input type="number" value={formData.seed} onChange={e => setFormData(p => ({ ...p, seed: e.target.value }))} />
                                </div>
                                <div className="space-y-2">
                                    <Label className="flex items-center">Duration (sec) <HelpTooltip content="How long the simulation episode will run before automatically terminating and saving." /></Label>
                                    <Input type="number" value={formData.durationSec} onChange={e => setFormData(p => ({ ...p, durationSec: e.target.value }))} />
                                </div>
                            </div>
                            <div className="space-y-2">
                                <Label>Notes</Label>
                                <Textarea value={formData.notes} onChange={e => setFormData(p => ({ ...p, notes: e.target.value }))} />
                            </div>
                        </div>
                    )}

                    {step === 6 && (
                        <div className="space-y-4 bg-muted/50 p-6 rounded-lg font-mono text-sm max-h-[400px] overflow-y-auto">
                            <div className="grid grid-cols-[150px_1fr] gap-2">
                                <div className="text-muted-foreground">Scene:</div>
                                <div className="font-bold">{selectedScene?.name || "None"}</div>

                                <div className="text-muted-foreground">Object Set:</div>
                                <div className="font-bold">{selectedObjectSet?.name || "None"}</div>

                                <div className="text-muted-foreground">Tasks:</div>
                                <div>{formData.tasks.join(", ") || "None"}</div>

                                <div className="text-muted-foreground">Sensors:</div>
                                <div>{formData.sensors.join(", ") || "None"}</div>

                                <div className="text-muted-foreground">Seed:</div>
                                <div>{formData.seed}</div>

                                <div className="text-muted-foreground">Duration:</div>
                                <div>{formData.durationSec}s</div>

                                <div className="text-muted-foreground mt-4 col-span-2 border-b border-border pb-1">Environment Config</div>
                                <div className="text-muted-foreground">Output Dir:</div>
                                <div>{config?.defaultOutputDir || "./data"}</div>

                                <div className="text-muted-foreground">Launch Profile:</div>
                                <div>{selectedProfile?.name || "Default Config Templates"}</div>

                                <div className="text-muted-foreground">Runner Mode:</div>
                                <div>{selectedProfile?.runnerMode || config?.runnerMode || "SSH_RUNNER"}</div>

                                <div className="text-muted-foreground">Session Mode:</div>
                                <div>{config?.isaacSessionMode || "launch_new"}</div>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

            <div className="flex justify-between">
                <Button variant="outline" onClick={handlePrev} disabled={step === 1}>
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Back
                </Button>
                {step < 6 ? (
                    <Button onClick={handleNext} disabled={step === 1 && !formData.sceneId}>
                        Next
                        <ArrowRight className="w-4 h-4 ml-2" />
                    </Button>
                ) : (
                    <Button onClick={handleSubmit} disabled={submitting}>
                        <Check className="w-4 h-4 mr-2" />
                        {submitting ? "Creating..." : "Create Episode"}
                    </Button>
                )}
            </div>
        </div>
    );
}

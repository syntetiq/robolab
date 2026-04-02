"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { HelpTooltip } from "@/components/HelpTooltip";

const SENSORS = [
    "RGB", "Depth", "CameraInfo", "PointCloud2", "GT Poses", "JointStates"
];

const DEFAULT_SAFE_PROFILE_NAME = "Default Safe Live Teleop";
const SHOW_EXPERIMENTAL_SCENES = process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_SCENES === "1";

export default function NewEpisodeWizard() {
    const router = useRouter();
    const [step, setStep] = useState(1);
    const [loadingConfig, setLoadingConfig] = useState(true);

    const [config, setConfig] = useState<any>(null);
    const [scenes, setScenes] = useState<any[]>([]);
    const [profiles, setProfiles] = useState<any[]>([]);

    const [formData, setFormData] = useState({
        sceneId: "",
        launchProfileId: "",
        sensors: [] as string[],
        seed: "42",
        durationSec: "60",
        notes: ""
    });

    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        Promise.all([
            fetch("/api/config").then(r => r.json()),
            fetch(SHOW_EXPERIMENTAL_SCENES ? "/api/scenes?includeExperimental=1" : "/api/scenes").then(r => r.json()),
            fetch("/api/launch-profiles").then(r => r.json())
        ]).then(([configData, scenesData, profilesData]) => {
            setConfig(configData);
            setScenes(scenesData);
            setProfiles(profilesData);
            const defaultProfile =
                (profilesData || []).find((p: any) => p?.name === DEFAULT_SAFE_PROFILE_NAME && p?.enabled !== false) ||
                (profilesData || []).find((p: any) => p?.runnerMode === "LOCAL_RUNNER" && p?.enableWebRTC === true && p?.enabled !== false) ||
                (profilesData || []).find((p: any) => p?.enableWebRTC === true && p?.enabled !== false);
            if (defaultProfile?.id) {
                setFormData((prev) => ({ ...prev, launchProfileId: String(defaultProfile.id) }));
            }
            const defaultScene =
                (scenesData || []).find((s: any) => s?.name?.toLowerCase().includes("kitchen fixed")) ||
                (scenesData || [])[0];
            if (defaultScene?.id) {
                setFormData((prev) => ({ ...prev, sceneId: String(defaultScene.id) }));
            }
            setLoadingConfig(false);
        });
    }, []);

    const TOTAL_STEPS = 5;
    const handleNext = () => setStep(s => Math.min(s + 1, TOTAL_STEPS));
    const handlePrev = () => setStep(s => Math.max(s - 1, 1));

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
                objectSetId: null,
                launchProfileId: formData.launchProfileId || null,
                tasks: JSON.stringify([]),
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

    const selectedScene = scenes.find(s => s.id === formData.sceneId);
    const selectedProfile = profiles.find(p => p.id === formData.launchProfileId);

    if (loadingConfig) return <div className="p-8 text-center">Loading options...</div>;

    return (
        <div className="max-w-3xl mx-auto p-8">
            <div className="mb-8">
                <h1 className="text-3xl font-bold tracking-tight mb-2">Create New Episode</h1>
                <div className="flex gap-2">
                    {Array.from({ length: TOTAL_STEPS }, (_, i) => i + 1).map(i => (
                        <div key={i} className={`h-2 flex-1 rounded-full ${step >= i ? 'bg-primary' : 'bg-muted'}`} />
                    ))}
                </div>
                <p className="text-muted-foreground text-sm mt-2">Step {step} of {TOTAL_STEPS}</p>
            </div>

            <Card className="mb-6 min-h-[400px]">
                <CardHeader>
                    <CardTitle>
                        {step === 1 && "Select Scene"}
                        {step === 2 && "Select Launch Profile"}
                        {step === 3 && "Select Sensors"}
                        {step === 4 && "Episode Params"}
                        {step === 5 && "Review Execution Plan"}
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
                    )}

                    {step === 3 && (
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

                    {step === 4 && (
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

                    {step === 5 && (
                        <div className="space-y-4 bg-muted/50 p-6 rounded-lg font-mono text-sm max-h-[400px] overflow-y-auto">
                            <div className="grid grid-cols-[150px_1fr] gap-2">
                                <div className="text-muted-foreground">Scene:</div>
                                <div className="font-bold">{selectedScene?.name || "None"}</div>

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
                {step < TOTAL_STEPS ? (
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

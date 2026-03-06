"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ConfigFormData, configSchema } from "@/lib/schemas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Download, Upload, Activity, Save, CheckCircle2, AlertCircle } from "lucide-react";
import { HelpTooltip } from "@/components/HelpTooltip";

export default function ConfigForm({ initialData }: { initialData: any }) {
    const [isSaving, setIsSaving] = useState(false);
    const [testReport, setTestReport] = useState<any>(null);
    const [isTesting, setIsTesting] = useState(false);

    const form = useForm<ConfigFormData>({
        resolver: zodResolver(configSchema) as any,
        defaultValues: initialData,
    });

    const onSubmit = async (data: ConfigFormData) => {
        setIsSaving(true);
        try {
            const res = await fetch("/api/config", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data)
            });
            if (!res.ok) throw new Error("Failed to save configuration");
            alert("Configuration saved successfully.");
        } catch (e: any) {
            alert(e.message);
        } finally {
            setIsSaving(false);
        }
    };

    const handleTestConnection = async () => {
        setIsTesting(true);
        setTestReport(null);
        try {
            const res = await fetch("/api/config/test-connection", { method: "POST" });
            const data = await res.json();
            setTestReport(data);
        } catch (e) {
            setTestReport({ error: "Failed to run diagnostic test." });
        } finally {
            setIsTesting(false);
        }
    };

    const exportConfig = () => {
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(form.getValues(), null, 2));
        const downloadAnchorNode = document.createElement("a");
        downloadAnchorNode.setAttribute("href", dataStr);
        downloadAnchorNode.setAttribute("download", "robolab-config.json");
        document.body.appendChild(downloadAnchorNode);
        downloadAnchorNode.click();
        downloadAnchorNode.remove();
    };

    const importConfig = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const json = JSON.parse(event.target?.result as string);
                form.reset(json);
                alert("Configuration loaded. Press Save to persist changes.");
            } catch (err) {
                alert("Invalid JSON file.");
            }
        };
        reader.readAsText(file);
        e.target.value = ""; // reset input
    };

    return (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="md:col-span-3">
                <Form {...form}>
                    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-8">
                        <Tabs defaultValue="general" className="w-full">
                            <TabsList className="flex flex-wrap h-auto">
                                <TabsTrigger value="general">General</TabsTrigger>
                                <TabsTrigger value="isaac">Isaac Sim</TabsTrigger>
                                <TabsTrigger value="ros2">ROS2</TabsTrigger>
                                <TabsTrigger value="recording">Recording</TabsTrigger>
                                <TabsTrigger value="streaming">Streaming</TabsTrigger>
                                <TabsTrigger value="advanced">Advanced</TabsTrigger>
                            </TabsList>

                            {/* GENERAL TAB */}
                            <TabsContent value="general">
                                <Card>
                                    <CardHeader>
                                        <CardTitle>General Settings</CardTitle>
                                        <CardDescription>Core application settings for the console.</CardDescription>
                                    </CardHeader>
                                    <CardContent className="space-y-4">
                                        <FormField control={form.control} name="appName" render={({ field }) => (
                                            <FormItem>
                                                <FormLabel className="flex items-center">Application Name <HelpTooltip content="The title displayed in the header of the console interface." /></FormLabel>
                                                <FormControl><Input {...field} /></FormControl>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        <FormField control={form.control} name="runnerMode" render={({ field }) => (
                                            <FormItem>
                                                <FormLabel className="flex items-center">Default Runner Mode <HelpTooltip content="Determines where Isaac Sim is executed: locally on this machine, remotely via SSH, or through an agent orchestrator." /></FormLabel>
                                                <Select onValueChange={field.onChange} defaultValue={field.value}>
                                                    <FormControl>
                                                        <SelectTrigger><SelectValue placeholder="Select runner mode" /></SelectTrigger>
                                                    </FormControl>
                                                    <SelectContent>
                                                        <SelectItem value="LOCAL_RUNNER">Local Machine</SelectItem>
                                                        <SelectItem value="SSH_RUNNER">Remote Server (SSH)</SelectItem>
                                                        <SelectItem value="AGENT_RUNNER">Agent Orchestrator</SelectItem>
                                                    </SelectContent>
                                                </Select>
                                                <FormDescription>Where Isaac Sim executes.</FormDescription>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        <FormField control={form.control} name="defaultOutputDir" render={({ field }) => (
                                            <FormItem>
                                                <FormLabel className="flex items-center">Default Output Directory <HelpTooltip content="The base directory path on the target machine where telemetry data, videos, and ROS bag logs will be saved." /></FormLabel>
                                                <FormControl><Input {...field} /></FormControl>
                                                <FormDescription>Local or remote path where resulting datasets/bags are stored.</FormDescription>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                    </CardContent>
                                </Card>
                            </TabsContent>

                            {/* ISAAC TAB */}
                            <TabsContent value="isaac">
                                <Card>
                                    <CardHeader>
                                        <CardTitle>Isaac Sim Host</CardTitle>
                                        <CardDescription>Connection and session parameters for the Isaac Sim instance.</CardDescription>
                                    </CardHeader>
                                    <CardContent className="space-y-4 grid grid-cols-2 gap-4">
                                        <FormField control={form.control} name="isaacHost" render={({ field }) => (
                                            <FormItem className="col-span-2 md:col-span-1">
                                                <FormLabel>Host IP / Domain</FormLabel>
                                                <FormControl><Input {...field} /></FormControl>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        <FormField control={form.control} name="isaacSshPort" render={({ field }) => (
                                            <FormItem className="col-span-2 md:col-span-1">
                                                <FormLabel className="flex items-center">SSH Port <HelpTooltip content="The port number used for SSH access to the remote machine running Isaac Sim (usually 22)." /></FormLabel>
                                                <FormControl><Input type="number" {...field} /></FormControl>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        <FormField control={form.control} name="isaacUser" render={({ field }) => (
                                            <FormItem className="col-span-2 md:col-span-1">
                                                <FormLabel>SSH Username</FormLabel>
                                                <FormControl><Input {...field} /></FormControl>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        <FormField control={form.control} name="isaacInstallPath" render={({ field }) => (
                                            <FormItem className="col-span-2">
                                                <FormLabel>Isaac Sim Install Path</FormLabel>
                                                <FormControl><Input {...field} /></FormControl>
                                                <FormDescription>Absolute path to the Isaac Sim folder on the target host (e.g., C:\Users\max\Documents\IsaacSim).</FormDescription>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        <FormField control={form.control} name="isaacAuthMode" render={({ field }) => (
                                            <FormItem className="col-span-2 md:col-span-1">
                                                <FormLabel className="flex items-center">Authentication Mode <HelpTooltip content="Select how the Node.js backend should authenticate with the SSH server." /></FormLabel>
                                                <Select onValueChange={field.onChange} defaultValue={field.value}>
                                                    <FormControl><SelectTrigger><SelectValue placeholder="Select Auth" /></SelectTrigger></FormControl>
                                                    <SelectContent>
                                                        <SelectItem value="password">Password (Interactive)</SelectItem>
                                                        <SelectItem value="ssh_key">SSH Key</SelectItem>
                                                    </SelectContent>
                                                </Select>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        <FormField control={form.control} name="sshKeyPath" render={({ field }) => (
                                            <FormItem className="col-span-2 md:col-span-1">
                                                <FormLabel>SSH Key Path (Local)</FormLabel>
                                                <FormControl><Input {...field} /></FormControl>
                                                <FormDescription>Required if using SSH Key auth mode.</FormDescription>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        <FormField control={form.control} name="sshPassword" render={({ field }) => (
                                            <FormItem className="col-span-2 md:col-span-1">
                                                <FormLabel>SSH Password</FormLabel>
                                                <FormControl><Input type="password" {...field} /></FormControl>
                                                <FormDescription>Required if using Password auth mode.</FormDescription>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        <FormField control={form.control} name="isaacSessionMode" render={({ field }) => (
                                            <FormItem className="col-span-2">
                                                <FormLabel>Session Mode</FormLabel>
                                                <Select onValueChange={field.onChange} defaultValue={field.value}>
                                                    <FormControl><SelectTrigger><SelectValue placeholder="Session Mode" /></SelectTrigger></FormControl>
                                                    <SelectContent>
                                                        <SelectItem value="launch_new">Launch New Session</SelectItem>
                                                        <SelectItem value="attach_to_running">Attach to Running Session</SelectItem>
                                                    </SelectContent>
                                                </Select>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                    </CardContent>
                                </Card>
                            </TabsContent>

                            {/* ROS2 TAB */}
                            <TabsContent value="ros2">
                                <Card>
                                    <CardHeader>
                                        <CardTitle>ROS 2 Configuration</CardTitle>
                                        <CardDescription>Network and namespace settings for ROS 2.</CardDescription>
                                    </CardHeader>
                                    <CardContent className="space-y-4">
                                        <div className="grid grid-cols-2 gap-4">
                                            <FormField control={form.control} name="rosDomainId" render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className="flex items-center">ROS_DOMAIN_ID <HelpTooltip content="The domain ID for Data Distribution Service (DDS) isolation in ROS 2." /></FormLabel>
                                                    <FormControl><Input type="number" {...field} /></FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )} />
                                            <FormField control={form.control} name="rosNamespace" render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel>Robot Namespace</FormLabel>
                                                    <FormControl><Input {...field} /></FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )} />
                                        </div>
                                        <FormField control={form.control} name="rmwImplementation" render={({ field }) => (
                                            <FormItem>
                                                <FormLabel>RMW Implementation</FormLabel>
                                                <FormControl><Input {...field} /></FormControl>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        <FormField control={form.control} name="cycloneDdsConfigPath" render={({ field }) => (
                                            <FormItem>
                                                <FormLabel>CycloneDDS Profile XML Path</FormLabel>
                                                <FormControl><Input {...field} /></FormControl>
                                                <FormDescription>Leave blank if using defaults.</FormDescription>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        <FormField control={form.control} name="ros2SetupCommand" render={({ field }) => (
                                            <FormItem>
                                                <FormLabel className="flex items-center">ROS2 Setup Command <HelpTooltip content="Optional command executed before teleop ROS2 commands (e.g., call C:\\ros2\\local_setup.bat)." /></FormLabel>
                                                <FormControl><Input {...field} placeholder='call C:\ros2\local_setup.bat' /></FormControl>
                                                <FormDescription>Used by teleop bridge to source ROS2 environment automatically.</FormDescription>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                    </CardContent>
                                </Card>
                            </TabsContent>

                            {/* RECORDING TAB */}
                            <TabsContent value="recording">
                                <Card>
                                    <CardHeader>
                                        <CardTitle>Recording Defaults</CardTitle>
                                        <CardDescription>Default ROS 2 topics to record via rosbag2.</CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <FormField control={form.control} name="defaultRecordTopics" render={({ field }) => (
                                            <FormItem>
                                                <FormLabel>Topics (JSON array format)</FormLabel>
                                                <FormControl><Textarea className="font-mono h-48" {...field} /></FormControl>
                                                <FormDescription>Provide a valid JSON array of strings.</FormDescription>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                    </CardContent>
                                </Card>
                            </TabsContent>

                            {/* STREAMING TAB */}
                            <TabsContent value="streaming">
                                <Card>
                                    <CardHeader>
                                        <CardTitle>Streaming Settings</CardTitle>
                                        <CardDescription>How video feed is shown to operators.</CardDescription>
                                    </CardHeader>
                                    <CardContent className="space-y-4">
                                        <FormField control={form.control} name="streamingMode" render={({ field }) => (
                                            <FormItem>
                                                <FormLabel className="flex items-center">Streaming Mode <HelpTooltip content="Defines how the operator interacts with the simulation (e.g., using a standalone WebRTC app like Vive VR or viewing an embedded iframe)." /></FormLabel>
                                                <Select onValueChange={field.onChange} defaultValue={field.value}>
                                                    <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                                                    <SelectContent>
                                                        <SelectItem value="none">None</SelectItem>
                                                        <SelectItem value="external_webrtc_client">External WebRTC Client</SelectItem>
                                                        <SelectItem value="browser_embedded_optional">Browser Embedded (Optional)</SelectItem>
                                                    </SelectContent>
                                                </Select>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                        {/* @ts-ignore RHF types match nullable string loosely */}
                                        <FormField control={form.control} name="streamingHint" render={({ field }) => (
                                            <FormItem>
                                                <FormLabel>Instructions/Hint Info</FormLabel>
                                                <FormControl><Textarea {...field} /></FormControl>
                                                <FormDescription>Shown to operator during episode.</FormDescription>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                    </CardContent>
                                </Card>
                            </TabsContent>

                            {/* ADVANCED TAB */}
                            <TabsContent value="advanced">
                                <Card>
                                    <CardHeader>
                                        <CardTitle>Advanced</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        {/* @ts-ignore RHF types match nullable string loosely */}
                                        <FormField control={form.control} name="futurePlaceholders" render={({ field }) => (
                                            <FormItem>
                                                <FormLabel>Future Placeholders (JSON)</FormLabel>
                                                <FormControl><Textarea className="font-mono h-32" {...field} /></FormControl>
                                                <FormMessage />
                                            </FormItem>
                                        )} />
                                    </CardContent>
                                </Card>
                            </TabsContent>

                            <div className="flex justify-end pt-4">
                                <Button type="submit" disabled={isSaving}>
                                    <Save className="w-4 h-4 mr-2" />
                                    {isSaving ? "Saving..." : "Save Configuration"}
                                </Button>
                            </div>
                        </Tabs>
                    </form>
                </Form>
            </div>

            <div className="space-y-4">
                <Card>
                    <CardHeader>
                        <CardTitle className="text-sm font-medium">Actions</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <Button variant="secondary" className="w-full justify-start" onClick={handleTestConnection} disabled={isTesting}>
                            <Activity className="w-4 h-4 mr-2" />
                            {isTesting ? "Testing..." : "Test Connection"}
                        </Button>
                        <Button variant="outline" className="w-full justify-start" onClick={exportConfig}>
                            <Download className="w-4 h-4 mr-2" />
                            Export JSON
                        </Button>
                        <div className="relative">
                            <Button variant="outline" className="w-full justify-start">
                                <Upload className="w-4 h-4 mr-2" />
                                Import JSON
                            </Button>
                            <input type="file" accept=".json" className="absolute inset-0 opacity-0 cursor-pointer" onChange={importConfig} />
                        </div>
                    </CardContent>
                </Card>

                {testReport && (
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm font-medium">Connection Test</CardTitle>
                        </CardHeader>
                        <CardContent>
                            {testReport.error ? (
                                <div className="text-sm text-red-500">{testReport.error}</div>
                            ) : (
                                <div className="text-sm space-y-2">
                                    <div className="flex items-center gap-2">
                                        {testReport.isaacHostReachable ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <AlertCircle className="w-4 h-4 text-red-500" />}
                                        <span>Host: {testReport.resolvedIp}</span>
                                    </div>
                                    {testReport.sshReachable !== null && (
                                        <div className="flex items-center gap-2">
                                            {testReport.sshReachable ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <AlertCircle className="w-4 h-4 text-red-500" />}
                                            <span>SSH Ready</span>
                                        </div>
                                    )}
                                    <div className="text-muted-foreground text-xs mt-2 font-mono">
                                        Latency: {testReport.latencyMs}ms
                                    </div>
                                    {testReport.recommendations?.length > 0 && (
                                        <div className="text-xs mt-2 bg-secondary p-2 rounded">
                                            {testReport.recommendations[0]}
                                        </div>
                                    )}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                )}
            </div>
        </div>
    );
}

"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Activity, Cpu, Server, PlayCircle, Layers, Package, Settings } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function Dashboard() {
  const [health, setHealth] = useState({ cpu: 0, memory: 0 });
  const [config, setConfig] = useState<any>(null);

  useEffect(() => {
    fetch("/api/config").then((r) => r.json()).then(setConfig).catch(console.error);

    const evtSource = new EventSource("/api/events");
    evtSource.addEventListener("system.health", (e) => {
      setHealth(JSON.parse(e.data));
    });

    return () => evtSource.close();
  }, []);

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">System Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

        {/* System Health Widget */}
        <Card className="md:col-span-1 shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center text-lg">
              <Activity className="w-5 h-5 mr-2 text-blue-500" />
              Instance Health
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="flex items-center"><Cpu className="w-4 h-4 mr-1" /> CPU Load</span>
                <span>{health.cpu}%</span>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 transition-all duration-500" style={{ width: `${health.cpu}%` }} />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="flex items-center"><Server className="w-4 h-4 mr-1" /> Memory Usage</span>
                <span>{health.memory}%</span>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div className="h-full bg-green-500 transition-all duration-500" style={{ width: `${health.memory}%` }} />
              </div>
            </div>

            <div className="pt-4 border-t mt-4 text-sm text-muted-foreground">
              Host: <span className="font-mono text-foreground">{config?.isaacHost || "Connecting..."}</span>
            </div>
            <div className="text-sm text-muted-foreground">
              Runner: <span className="font-mono text-foreground">{config?.runnerMode || "..."}</span>
            </div>
          </CardContent>
        </Card>

        {/* Quick Actions */}
        <Card className="md:col-span-2 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg">Quick Actions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <Link href="/episodes/new">
                <Button className="w-full h-24 flex flex-col gap-2 bg-primary/10 text-primary hover:bg-primary/20 border-primary/20" variant="outline">
                  <PlayCircle className="w-6 h-6" />
                  New Episode
                </Button>
              </Link>

              <Link href="/scenes">
                <Button className="w-full h-24 flex flex-col gap-2" variant="outline">
                  <Layers className="w-6 h-6 text-orange-500" />
                  Manage Scenes
                </Button>
              </Link>

              <Link href="/object-sets">
                <Button className="w-full h-24 flex flex-col gap-2" variant="outline">
                  <Package className="w-6 h-6 text-purple-500" />
                  Manage Objects
                </Button>
              </Link>

              <Link href="/config">
                <Button className="w-full h-24 flex flex-col gap-2" variant="outline">
                  <Settings className="w-6 h-6 text-gray-500" />
                  Console Settings
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

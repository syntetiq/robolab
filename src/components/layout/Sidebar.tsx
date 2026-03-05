"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Settings, Package, LayoutGrid, PlayCircle, Rocket } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
    { name: "Dashboard", href: "/", icon: Activity },
    { name: "Episodes", href: "/episodes", icon: PlayCircle },
    { name: "Scenes", href: "/scenes", icon: LayoutGrid },
    { name: "Object Sets", href: "/object-sets", icon: Package },
    { name: "Launch Profiles", href: "/launch-profiles", icon: Rocket },
    { name: "Configuration", href: "/config", icon: Settings },
];

export function Sidebar() {
    const pathname = usePathname();

    return (
        <div className="flex flex-col w-64 border-r bg-card min-h-screen">
            <div className="p-6">
                <h2 className="text-2xl font-bold tracking-tight text-primary flex items-center gap-2">
                    <Activity className="w-6 h-6" />
                    RoboLab Console
                </h2>
                <p className="text-sm text-muted-foreground mt-1">Data Collection MVP</p>
            </div>

            <nav className="flex-1 px-4 space-y-2 mt-4">
                {NAV_ITEMS.map((item) => {
                    const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={cn(
                                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                                isActive
                                    ? "bg-primary text-primary-foreground"
                                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                            )}
                        >
                            <item.icon className="w-4 h-4" />
                            {item.name}
                        </Link>
                    );
                })}
            </nav>

            <div className="p-4 border-t text-xs text-muted-foreground text-center">
                Isaac Sim Web Operator &copy; 2026
            </div>
        </div>
    );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Settings, LayoutGrid, PlayCircle, Rocket, Film, FlaskConical, Layers } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
    { name: "Dashboard", href: "/", icon: Activity },
    { name: "Episodes", href: "/episodes", icon: PlayCircle },
    { name: "Batch Queue", href: "/batches", icon: Layers },
    { name: "Experiments", href: "/experiments", icon: FlaskConical },
    { name: "Recordings", href: "/recordings", icon: Film },
    { name: "Scenes", href: "/scenes", icon: LayoutGrid },
    { name: "Launch Profiles", href: "/launch-profiles", icon: Rocket },
    { name: "Configuration", href: "/config", icon: Settings },
];

export function Sidebar() {
    const pathname = usePathname();

    return (
        <div className="flex flex-col w-64 border-r bg-card min-h-screen">
            <Link href="/" className="block p-6 group">
                <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary text-primary-foreground shadow-sm">
                        <Activity className="w-5 h-5" />
                    </div>
                    <div>
                        <h2 className="text-lg font-bold tracking-tight leading-tight group-hover:text-primary transition-colors">RoboLab</h2>
                        <p className="text-xs text-muted-foreground leading-tight">Data Collection</p>
                    </div>
                </div>
            </Link>

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
                <a href="https://www.syntetiq.com/" target="_blank" rel="noopener noreferrer" className="hover:underline">SyntetiQ</a> &copy; 2026
            </div>
        </div>
    );
}

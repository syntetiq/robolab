import { prisma } from "@/lib/prisma";
import ConfigForm from "./ConfigForm";

export const dynamic = 'force-dynamic';

export default async function ConfigPage() {
    const config = await prisma.config.findFirst();

    if (!config) {
        return (
            <div className="p-8">
                <h1 className="text-3xl font-bold mb-4">Configuration</h1>
                <p className="text-red-500">Error: Configuration not found. Please run the database seed.</p>
            </div>
        );
    }

    return (
        <div className="max-w-4xl mx-auto p-8">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Configuration</h1>
                    <p className="text-muted-foreground">Manage RoboLab MVP Console settings.</p>
                </div>
            </div>

            <ConfigForm initialData={config} />
        </div>
    );
}

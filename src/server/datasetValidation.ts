import fs from "fs";
import path from "path";

export interface DatasetValidationResult {
    valid: boolean;
    missingFiles: string[];
    issues: string[];
}

const REQUIRED_FILES = [
    "metadata.json",
    "dataset.json",
    "dataset_manifest.json",
    "telemetry.json",
    "camera_0.mp4",
];

export function normalizeEpisodeDir(outputDir: string | null | undefined): string | null {
    if (!outputDir) return null;
    const trimmed = outputDir.trim();
    if (!trimmed) return null;
    return trimmed.replace(/[\\/]+$/, "");
}

export function validateEpisodeDataset(outputDir: string | null | undefined): DatasetValidationResult {
    const issues: string[] = [];
    const missingFiles: string[] = [];

    const normalized = normalizeEpisodeDir(outputDir);
    if (!normalized) {
        return {
            valid: false,
            missingFiles: ["<episode output dir>"],
            issues: ["Episode output directory is not set."],
        };
    }

    if (!fs.existsSync(normalized)) {
        return {
            valid: false,
            missingFiles: [normalized],
            issues: ["Episode output directory does not exist."],
        };
    }

    for (const fileName of REQUIRED_FILES) {
        const fullPath = path.join(normalized, fileName);
        if (!fs.existsSync(fullPath)) {
            missingFiles.push(fileName);
        }
    }

    const datasetPath = path.join(normalized, "dataset.json");
    if (fs.existsSync(datasetPath)) {
        try {
            const data = JSON.parse(fs.readFileSync(datasetPath, "utf8"));
            const frames = Array.isArray(data.frames) ? data.frames : [];

            if (frames.length === 0) {
                issues.push("dataset.json has no frames.");
            }

            const hasJointVelocity = frames.some((frame: any) => {
                const joints = frame?.robot_joints || {};
                return Object.values(joints).some((joint: any) => typeof joint?.velocity === "number");
            });
            if (!hasJointVelocity) {
                issues.push("No joint velocity samples found in dataset frames.");
            }

            const hasWorldPose = frames.some((frame: any) => {
                const poses = frame?.world_poses || {};
                return Object.keys(poses).length > 0;
            });
            if (!hasWorldPose) {
                issues.push("No world poses found in dataset frames.");
            }
        } catch (err: any) {
            issues.push(`Failed to parse dataset.json: ${err.message}`);
        }
    }

    return {
        valid: missingFiles.length === 0 && issues.length === 0,
        missingFiles,
        issues,
    };
}

export function formatValidationSummary(result: DatasetValidationResult): string {
    const parts: string[] = [];
    if (result.missingFiles.length > 0) {
        parts.push(`Missing files: ${result.missingFiles.join(", ")}`);
    }
    if (result.issues.length > 0) {
        parts.push(...result.issues);
    }
    return parts.join(" | ");
}

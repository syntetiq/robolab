import fs from "fs";
import path from "path";

export interface DatasetValidationResult {
    valid: boolean;
    missingFiles: string[];
    issues: string[];
    optionalPresent?: string[];
    optionalMissing?: string[];
}

const REQUIRED_FILES = [
    "metadata.json",
    "dataset.json",
    "dataset_manifest.json",
    "telemetry.json",
    "camera_0.mp4",
];

const OPTIONAL_FILES = [
    "grasp_events.json",
    "camera_1_wrist.mp4",
    "camera_2_external.mp4",
];

const OPTIONAL_DIRS = [
    "replicator_data",
    "replicator_wrist",
    "replicator_external",
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

    const optionalPresent: string[] = [];
    const optionalMissing: string[] = [];
    for (const fileName of OPTIONAL_FILES) {
        if (fs.existsSync(path.join(normalized, fileName))) {
            optionalPresent.push(fileName);
        } else {
            optionalMissing.push(fileName);
        }
    }
    for (const dirName of OPTIONAL_DIRS) {
        const dirPath = path.join(normalized, dirName);
        if (fs.existsSync(dirPath) && fs.statSync(dirPath).isDirectory()) {
            const files = fs.readdirSync(dirPath);
            optionalPresent.push(`${dirName}/ (${files.length} files)`);
        } else {
            optionalMissing.push(`${dirName}/`);
        }
    }

    const datasetPath = path.join(normalized, "dataset.json");
    const metadataPath = path.join(normalized, "metadata.json");
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

            const hasMapFrame = frames.some((frame: any) => frame?.map_frame === "map");
            if (!hasMapFrame) {
                issues.push("No frames with map_frame='map' found.");
            }

            const trajectories = Array.isArray(data.joint_trajectories) ? data.joint_trajectories : [];
            if (trajectories.length === 0) {
                issues.push("No joint_trajectories samples found in dataset.");
            }
        } catch (err: any) {
            issues.push(`Failed to parse dataset.json: ${err.message}`);
        }
    }

    const replicatorDataPath = path.join(normalized, "replicator_data");
    if (!fs.existsSync(replicatorDataPath) || !fs.statSync(replicatorDataPath).isDirectory()) {
        missingFiles.push("replicator_data/");
    } else {
        const repFiles = fs.readdirSync(replicatorDataPath);
        const hasPointcloud = repFiles.some((f) => f.toLowerCase().includes("pointcloud"));
        const hasDepth = repFiles.some((f) => f.toLowerCase().includes("distance_to_camera"));
        if (!hasPointcloud) {
            issues.push("replicator_data has no pointcloud files.");
        }
        if (!hasDepth) {
            issues.push("replicator_data has no distance_to_camera files.");
        }
    }

    if (fs.existsSync(metadataPath)) {
        try {
            const meta = JSON.parse(fs.readFileSync(metadataPath, "utf8"));
            const sensors = Array.isArray(meta?.sensors) ? meta.sensors.map((s: any) => String(s)) : [];
            if (sensors.length > 0 && !sensors.includes("pointcloud")) {
                issues.push("metadata.sensors does not include pointcloud.");
            }
        } catch (err: any) {
            issues.push(`Failed to parse metadata.json: ${err.message}`);
        }
    }

    return {
        valid: missingFiles.length === 0 && issues.length === 0,
        missingFiles,
        issues,
        optionalPresent,
        optionalMissing,
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

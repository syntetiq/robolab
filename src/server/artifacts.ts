import fs from "fs";
import path from "path";
import crypto from "crypto";

export interface ArtifactItem {
    episodeId: string;
    name: string;
    kind: "video" | "json";
    bytes: number;
    checksumSha256: string;
    updatedAt: string;
    playUrl: string;
    downloadUrl: string;
    sourceDir: string;
}

interface ArtifactIndexEntry {
    name: string;
    bytes: number;
    mtimeMs: number;
    checksumSha256: string;
}

interface ArtifactIndexFile {
    generatedAt: string;
    entries: ArtifactIndexEntry[];
}

const INDEX_FILE = ".artifact-index.json";
const MAX_HASH_BYTES = 64 * 1024 * 1024;

function isRelevantArtifact(fileName: string): boolean {
    return fileName.endsWith(".mp4") || fileName.endsWith(".webm") || fileName.endsWith(".json");
}

function artifactKind(fileName: string): "video" | "json" {
    if (fileName.endsWith(".mp4") || fileName.endsWith(".webm")) return "video";
    return "json";
}

function sha256ForFile(filePath: string, bytes: number): string {
    if (bytes > MAX_HASH_BYTES) {
        return "";
    }
    const hash = crypto.createHash("sha256");
    const data = fs.readFileSync(filePath);
    hash.update(data);
    return hash.digest("hex");
}

function loadIndex(indexPath: string): ArtifactIndexFile | null {
    if (!fs.existsSync(indexPath)) return null;
    try {
        return JSON.parse(fs.readFileSync(indexPath, "utf8")) as ArtifactIndexFile;
    } catch {
        return null;
    }
}

function saveIndex(indexPath: string, index: ArtifactIndexFile): void {
    fs.writeFileSync(indexPath, JSON.stringify(index, null, 2), "utf8");
}

export function resolveEpisodeArtifactDir(episodeId: string, outputDir: string | null | undefined): {
    dirPath: string;
    source: "public" | "output";
} | null {
    const publicDir = path.resolve(process.cwd(), `public/episodes/${episodeId}`);
    if (fs.existsSync(publicDir) && fs.statSync(publicDir).isDirectory()) {
        return { dirPath: publicDir, source: "public" };
    }

    if (outputDir && outputDir.trim()) {
        const candidate = path.resolve(process.cwd(), outputDir);
        if (fs.existsSync(candidate) && fs.statSync(candidate).isDirectory()) {
            return { dirPath: candidate, source: "output" };
        }
    }

    return null;
}

export function listEpisodeArtifacts(episodeId: string, outputDir: string | null | undefined): ArtifactItem[] {
    const resolved = resolveEpisodeArtifactDir(episodeId, outputDir);
    if (!resolved) return [];

    const names = fs.readdirSync(resolved.dirPath).filter(isRelevantArtifact);
    const indexPath = path.join(resolved.dirPath, INDEX_FILE);
    const prior = loadIndex(indexPath);
    const priorMap = new Map((prior?.entries || []).map((entry) => [entry.name, entry]));
    const nextEntries: ArtifactIndexEntry[] = [];

    const items: ArtifactItem[] = names.map((name) => {
        const fullPath = path.join(resolved.dirPath, name);
        const stat = fs.statSync(fullPath);
        const priorEntry = priorMap.get(name);
        const checksumSha256 =
            priorEntry && priorEntry.bytes === stat.size && priorEntry.mtimeMs === stat.mtimeMs
                ? priorEntry.checksumSha256
                : sha256ForFile(fullPath, stat.size);

        nextEntries.push({
            name,
            bytes: stat.size,
            mtimeMs: stat.mtimeMs,
            checksumSha256,
        });

        const inPublic = resolved.source === "public";
        const encoded = encodeURIComponent(name);
        const mediaUrl = inPublic
            ? `/episodes/${episodeId}/${encoded}`
            : `/api/episodes/${episodeId}/videos/${encoded}`;
        return {
            episodeId,
            name,
            kind: artifactKind(name),
            bytes: stat.size,
            checksumSha256,
            updatedAt: stat.mtime.toISOString(),
            playUrl: mediaUrl,
            downloadUrl: mediaUrl,
            sourceDir: resolved.dirPath,
        };
    });

    saveIndex(indexPath, { generatedAt: new Date().toISOString(), entries: nextEntries });
    return items.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

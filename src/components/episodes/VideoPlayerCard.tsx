import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Download } from 'lucide-react';

export interface VideoArtifact {
    name: string;
    playUrl: string;
    downloadUrl: string;
    bytes?: number;
    updatedAt?: string;
}

export function VideoPlayerCard({ videos }: { videos: VideoArtifact[] }) {
    // Regression protection: ensuring we only ever render video formats
    const validVideos = videos.filter(v => v.name.endsWith('.mp4') || v.name.endsWith('.webm'));

    if (validVideos.length === 0) return null;

    return (
        <Card data-testid="video-player-card">
            <CardHeader>
                <CardTitle className="text-sm">Recorded Videos</CardTitle>
            </CardHeader>
            <CardContent>
                <div className="grid grid-cols-1 gap-4">
                    {validVideos.map((vid) => (
                        <div key={vid.name} className="space-y-2">
                            <p className="text-xs font-mono text-muted-foreground">{vid.name}</p>
                            <video controls className="w-full rounded border bg-black" data-testid={`video-${vid.name}`}>
                                <source src={vid.playUrl} type={vid.name.endsWith('.mp4') ? 'video/mp4' : 'video/webm'} />
                            </video>
                            <div className="flex justify-end">
                                <Button variant="outline" size="sm" asChild>
                                    <a href={vid.downloadUrl} download={vid.name}><Download className="w-4 h-4 mr-2" /> Download</a>
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}

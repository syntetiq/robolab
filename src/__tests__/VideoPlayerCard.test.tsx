import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { VideoPlayerCard } from '../components/episodes/VideoPlayerCard';
import React from 'react';

describe('VideoPlayerCard', () => {
    it('does not render the card when no valid videos are provided', () => {
        const artifacts = [
            { name: 'telemetry.json', playUrl: '/episodes/123/telemetry.json', downloadUrl: '/episodes/123/telemetry.json' },
            { name: 'logs.txt', playUrl: '/episodes/123/logs.txt', downloadUrl: '/episodes/123/logs.txt' }
        ];

        render(<VideoPlayerCard videos={artifacts} />);

        // Card should not be in document at all
        expect(screen.queryByTestId('video-player-card')).toBeNull();
    });

    it('renders only valid MP4/WEBM videos and filters out JSON', () => {
        const artifacts = [
            { name: 'camera_0.mp4', playUrl: '/episodes/123/camera_0.mp4', downloadUrl: '/episodes/123/camera_0.mp4' },
            { name: 'telemetry.json', playUrl: '/episodes/123/telemetry.json', downloadUrl: '/episodes/123/telemetry.json' },
            { name: 'camera_1.webm', playUrl: '/episodes/123/camera_1.webm', downloadUrl: '/episodes/123/camera_1.webm' }
        ];

        render(<VideoPlayerCard videos={artifacts} />);

        // Card should be rendered
        expect(screen.getByTestId('video-player-card')).toBeTruthy();

        // Should render camera_0 and camera_1
        expect(screen.getByTestId('video-camera_0.mp4')).toBeTruthy();
        expect(screen.getByTestId('video-camera_1.webm')).toBeTruthy();

        // Should NOT render telemetry.json as a video
        expect(screen.queryByTestId('video-telemetry.json')).toBeNull();
    });
});

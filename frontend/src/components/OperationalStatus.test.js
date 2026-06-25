import { describe, expect, it } from 'vitest';
import { deriveOperationalStatus } from '../utils/operationalStatus';

describe('deriveOperationalStatus', () => {
    it('reports the active Stage 2B batch instead of generic pending state', () => {
        const message = {
            loading: { stage2: true, stage2b: true },
            timers: { stage1Start: 1_000, stage2bStart: 51_000 },
            progress: { stage2b: { count: 2, total: 4 } },
            stage2b: [
                { model: 'a', status: 'completed' },
                { model: 'b', status: 'failed', error: true },
                { model: 'c', status: 'queued' },
                { model: 'd', status: 'queued' },
            ],
            metadata: { current_round: 1, debate_rounds_configured: 1 },
        };

        const status = deriveOperationalStatus(message, { now: 61_000 });

        expect(status.phase).toBe('stage2b');
        expect(status.label).toContain('Claim-by-claim audit');
        expect(status.detail).toContain('2 of 4 requests complete');
        expect(status.detail).toContain('1 failed');
        expect(status.progressPercent).toBeGreaterThan(45);
        expect(status.progressPercent).toBeLessThan(70);
    });

    it('uses source length to produce a bounded Stage 4 estimate', () => {
        const message = {
            loading: { stage4: true },
            timers: { stage1Start: 1_000, stage4Start: 101_000 },
            metadata: {},
        };

        const status = deriveOperationalStatus(message, {
            now: 131_000,
            sourceWordCount: 6_654,
        });

        expect(status.phase).toBe('stage4');
        expect(status.progressPercent).toBeGreaterThanOrEqual(92);
        expect(status.progressPercent).toBeLessThan(100);
        expect(status.etaSeconds).toBeGreaterThan(0);
        expect(status.detail).toContain('complete corrected document');
    });

    it('shows held and active request counts while paused', () => {
        const status = deriveOperationalStatus(
            { loading: { stage1: true }, timers: { stage1Start: 1_000 } },
            {
                now: 5_000,
                runPaused: true,
                activeProviders: ['one'],
                pendingProviders: ['two', 'three'],
            },
        );

        expect(status.phase).toBe('paused');
        expect(status.progressPercent).toBeNull();
        expect(status.detail).toContain('1 active');
        expect(status.detail).toContain('2 held');
    });
});

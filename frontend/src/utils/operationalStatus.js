import { getRequestStatus } from './requestStatus';

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'unaccounted']);

const PHASE_CONFIG = {
    dispatch: { label: 'Dispatching council requests', range: [0.01, 0.04], expectedSeconds: 12 },
    search: { label: 'Web search', range: [0.02, 0.08], expectedSeconds: 25 },
    stage1: { label: 'Stage 1 · Council responses', range: [0.08, 0.36], expectedSeconds: 75 },
    claimDecomposition: { label: 'Claim decomposition', range: [0.36, 0.43], expectedSeconds: 55 },
    stage2: { label: 'Stage 2 · Peer rankings', range: [0.43, 0.72], expectedSeconds: 95 },
    stage2a: { label: 'Stage 2A · Holistic peer evaluations', range: [0.43, 0.55], expectedSeconds: 90 },
    stage2b: { label: 'Stage 2B · Claim-by-claim audit', range: [0.55, 0.70], expectedSeconds: 110 },
    stage2c: { label: 'Stage 2C · Chairman adjudication', range: [0.70, 0.78], expectedSeconds: 70 },
    stage3: { label: 'Stage 3 · Chairman synthesis', range: [0.78, 0.90], expectedSeconds: 90 },
    stage4: { label: 'Stage 4 · Corrected draft', range: [0.92, 0.99], expectedSeconds: 120 },
    paused: { label: 'Run paused', range: [0, 0], expectedSeconds: 0 },
};

const TIMER_KEYS = {
    search: 'searchStart',
    stage1: 'stage1Start',
    claimDecomposition: 'claimDecompositionStart',
    stage2: 'stage2Start',
    stage2a: 'stage2aStart',
    stage2b: 'stage2bStart',
    stage2c: 'stage2cStart',
    stage3: 'stage3Start',
    stage4: 'stage4Start',
};

function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
}

export function formatOperationalDuration(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return '—';
    const rounded = Math.max(0, Math.round(seconds));
    if (rounded < 60) return `${rounded}s`;
    const minutes = Math.floor(rounded / 60);
    const remainder = rounded % 60;
    return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
}

function getRunStart(timers = {}, now = Date.now()) {
    const starts = Object.entries(timers)
        .filter(([key, value]) => key.endsWith('Start') && Number.isFinite(value) && value <= now)
        .map(([, value]) => value);
    return starts.length ? Math.min(...starts) : now;
}

function getBatch(message, phase) {
    const progress = message?.progress?.[phase]
        || (phase === 'stage2' ? message?.progress?.stage2 : null)
        || {};
    const items = phase === 'stage1'
        ? (message?.stage1 || [])
        : phase === 'stage2a'
            ? (message?.stage2a || message?.stage2 || [])
            : phase === 'stage2b'
                ? (message?.stage2b || [])
                : phase === 'stage2'
                    ? (message?.stage2 || [])
                    : [];

    const statuses = items.map((item) => getRequestStatus(item));
    const statusCompleted = statuses.filter((status) => TERMINAL_STATUSES.has(status)).length;
    const completed = Math.max(Number(progress.count) || 0, statusCompleted);
    const total = Math.max(Number(progress.total) || 0, items.length, completed);
    const failed = statuses.filter((status) => status === 'failed' || status === 'unaccounted').length;
    const running = statuses.filter((status) => status === 'running').length;
    const queued = Math.max(0, total - completed - running);

    return { completed, total, failed, running, queued };
}

function getActivePhase(message, runPaused) {
    if (runPaused) return 'paused';
    const loading = message?.loading || {};
    if (loading.stage4) return 'stage4';
    if (loading.stage3) return 'stage3';
    if (loading.stage2c) return 'stage2c';
    if (loading.stage2b) return 'stage2b';
    if (loading.stage2a) return 'stage2a';
    if (loading.stage2) return 'stage2';
    if (loading.claimDecomposition) return 'claimDecomposition';
    if (loading.stage1) return 'stage1';
    if (loading.search) return 'search';
    return 'dispatch';
}

function getPhaseDetail(phase, batch, message, pendingCount, activeProviders, pendingProviders) {
    if (phase === 'paused') {
        const active = activeProviders?.length || 0;
        const held = pendingProviders?.length || pendingCount || 0;
        return `${active} active · ${held} held pending recovery`;
    }
    if (batch.total > 0) {
        const parts = [`${batch.completed} of ${batch.total} requests complete`];
        if (batch.running) parts.push(`${batch.running} active`);
        if (batch.queued) parts.push(`${batch.queued} queued`);
        if (batch.failed) parts.push(`${batch.failed} failed`);
        return parts.join(' · ');
    }
    if (phase === 'search') return 'Retrieving and preparing external context';
    if (phase === 'claimDecomposition') return 'Building the canonical claim set for peer review';
    if (phase === 'stage2c') return 'Resolving disputed and qualified claims';
    if (phase === 'stage3') return 'Synthesizing the council record into the final answer';
    if (phase === 'stage4') {
        const strategy = message?.metadata?.stage4_progress?.strategy;
        return strategy === 'exact_edit_plan'
            ? 'Applying exact edits while preserving the original document'
            : 'Generating and validating the complete corrected document';
    }
    return 'Preparing the next operation';
}

export function deriveOperationalStatus(message, options = {}) {
    const {
        now = Date.now(),
        runPaused = false,
        pendingCount = 0,
        activeProviders = [],
        pendingProviders = [],
        sourceWordCount = 0,
    } = options;

    const phase = getActivePhase(message, runPaused);
    const config = PHASE_CONFIG[phase];
    const timers = message?.timers || {};
    const timerKey = TIMER_KEYS[phase];
    const phaseStart = timerKey && Number.isFinite(timers[timerKey]) ? timers[timerKey] : getRunStart(timers, now);
    const elapsedSeconds = Math.max(0, (now - phaseStart) / 1000);
    const runStart = getRunStart(timers, now);
    const runElapsedSeconds = Math.max(0, (now - runStart) / 1000);
    const batch = getBatch(message, phase);

    let localProgress;
    if (batch.total > 0) {
        localProgress = clamp(batch.completed / batch.total, 0, 0.98);
    } else {
        let expectedSeconds = config.expectedSeconds;
        if (phase === 'stage4' && sourceWordCount > 0) {
            expectedSeconds = clamp(sourceWordCount / 48, 75, 360);
        }
        localProgress = clamp(elapsedSeconds / expectedSeconds, 0.04, 0.88);
    }

    const [phaseStartFraction, phaseEndFraction] = config.range;
    const round = Math.max(1, Number(message?.metadata?.current_round) || 1);
    const totalRounds = Math.max(
        round,
        Number(message?.metadata?.debate_rounds_configured) || 1,
        Array.isArray(message?.metadata?.rounds) ? message.metadata.rounds.length : 0,
    );

    let overallFraction;
    if (phase === 'paused') {
        overallFraction = null;
    } else if (phase === 'stage4') {
        overallFraction = phaseStartFraction + ((phaseEndFraction - phaseStartFraction) * localProgress);
    } else {
        const roundFraction = phaseStartFraction + ((phaseEndFraction - phaseStartFraction) * localProgress);
        overallFraction = (((round - 1) + roundFraction) / totalRounds) * 0.90;
    }

    let stageRemainingSeconds = null;
    if (phase !== 'paused') {
        if (batch.total > 0 && batch.completed > 0) {
            stageRemainingSeconds = Math.max(0, (elapsedSeconds / batch.completed) * (batch.total - batch.completed));
        } else {
            let expectedSeconds = config.expectedSeconds;
            if (phase === 'stage4' && sourceWordCount > 0) {
                expectedSeconds = clamp(sourceWordCount / 48, 75, 360);
            }
            stageRemainingSeconds = Math.max(0, expectedSeconds - elapsedSeconds);
        }
    }

    let overallRemainingSeconds = null;
    if (overallFraction && overallFraction >= 0.05 && runElapsedSeconds >= 8) {
        overallRemainingSeconds = runElapsedSeconds * ((1 - overallFraction) / overallFraction);
    }
    const etaSeconds = stageRemainingSeconds == null
        ? null
        : Math.max(stageRemainingSeconds, overallRemainingSeconds || 0);

    return {
        phase,
        label: config.label,
        detail: getPhaseDetail(phase, batch, message, pendingCount, activeProviders, pendingProviders),
        batch,
        elapsedSeconds,
        etaSeconds,
        progressPercent: overallFraction == null ? null : Math.round(clamp(overallFraction * 100, 1, 99)),
        round,
        totalRounds,
    };
}

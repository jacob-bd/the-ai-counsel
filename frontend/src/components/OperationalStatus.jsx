import { useEffect, useMemo, useState } from 'react';
import {
    deriveOperationalStatus,
    formatOperationalDuration,
} from '../utils/operationalStatus';
import './OperationalStatus.css';

export default function OperationalStatus({
    message,
    isLoading,
    runPaused,
    pendingCount,
    activeProviders,
    pendingProviders,
    sourceWordCount,
}) {
    const [now, setNow] = useState(() => Date.now());

    useEffect(() => {
        if (!isLoading && !runPaused) return undefined;
        const interval = window.setInterval(() => setNow(Date.now()), 1000);
        return () => window.clearInterval(interval);
    }, [isLoading, runPaused]);

    const status = useMemo(
        () => deriveOperationalStatus(message, {
            now,
            runPaused,
            pendingCount,
            activeProviders,
            pendingProviders,
            sourceWordCount,
        }),
        [message, runPaused, pendingCount, activeProviders, pendingProviders, sourceWordCount, now],
    );

    if (!isLoading && !runPaused) return null;

    const etaLabel = status.etaSeconds == null
        ? 'ETA unavailable'
        : status.etaSeconds <= 1
            ? 'Finishing…'
            : `ETA ≈ ${formatOperationalDuration(status.etaSeconds)}`;

    return (
        <div
            className={`operational-status operational-status--${status.phase}`}
            role="status"
            aria-live="polite"
            aria-label={`${status.label}. ${status.detail}`}
        >
            <div className="operational-status__header">
                <div className="operational-status__identity">
                    <span className="operational-status__pulse" aria-hidden="true" />
                    <strong>{status.label}</strong>
                    {status.totalRounds > 1 && status.phase !== 'stage4' && (
                        <span className="operational-status__round">Round {status.round}/{status.totalRounds}</span>
                    )}
                </div>
                <div className="operational-status__timing">
                    <span>{formatOperationalDuration(status.elapsedSeconds)} elapsed</span>
                    <span className="operational-status__separator">·</span>
                    <span>{etaLabel}</span>
                </div>
            </div>
            <div className="operational-status__detail">{status.detail}</div>
            <div
                className={`operational-status__track ${status.progressPercent == null ? 'is-indeterminate' : ''}`}
                role="progressbar"
                aria-valuemin="0"
                aria-valuemax="100"
                aria-valuenow={status.progressPercent ?? undefined}
            >
                <span
                    className="operational-status__bar"
                    style={status.progressPercent == null ? undefined : { width: `${status.progressPercent}%` }}
                />
            </div>
            <div className="operational-status__footer">
                <span>{status.progressPercent == null ? 'Paused' : `Approx. ${status.progressPercent}% overall`}</span>
                <span>Progress and ETA are estimates</span>
            </div>
        </div>
    );
}

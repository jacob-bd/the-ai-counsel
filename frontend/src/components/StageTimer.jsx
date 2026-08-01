import { useState, useEffect } from 'react';

export default function StageTimer({ startTime, endTime, label = "Elapsed" }) {
    const [elapsed, setElapsed] = useState(0);

    useEffect(() => {
        if (!startTime) return;

        if (endTime) {
            // Final duration
            setElapsed(endTime - startTime);
            return;
        }

        // Active timer
        const interval = setInterval(() => {
            setElapsed(Date.now() - startTime);
        }, 100); // Update every 100ms for smoothness

        return () => clearInterval(interval);
    }, [startTime, endTime]);

    if (!startTime) return null;

    const formatTime = (ms) => {
        const seconds = (ms / 1000).toFixed(1);
        return `${seconds}s`;
    };

    return (
        <span className="stage-timer" style={{
            marginLeft: '10px',
            fontSize: 'calc(12px * var(--font-scale))',
            color: '#666',
            fontFamily: 'monospace'
        }}>
            {label}: {formatTime(elapsed)}
        </span>
    );
}

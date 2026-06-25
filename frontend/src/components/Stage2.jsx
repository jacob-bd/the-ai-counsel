import { useState, useEffect } from 'react';
import Skeleton from './common/Skeleton';
import MarkdownContent from './MarkdownContent';
import { getModelVisuals, getShortModelName } from '../utils/modelHelpers';
import { getRequestStatus, getRequestStatusLabel } from '../utils/requestStatus';
import RankingHeatmap from './RankingHeatmap';
import { ClaimCardWithVerdicts } from './ClaimCards';
import './Stage2.css';
import './ClaimCards.css';
import StageTimer from './StageTimer';
import ModelVisualIcon from './ModelVisualIcon';
import { copyToClipboard } from '../utils/clipboard';

function looksLikeEvaluatorRefusal(text) {
    const normalized = String(text || '').replace(/\s+/g, ' ').trim().toLowerCase();
    if (!normalized) return false;

    return [
        'i cannot perform this task',
        "i can't perform this task",
        'the request you pasted requires capabilities and a role i do not have',
        'i do not have tools or the ability to',
        'my capabilities are strictly limited to notion workspace operations',
    ].some((marker) => normalized.includes(marker));
}
function deAnonymizeText(text, labelToModel) {
    if (!labelToModel) return text;

    let result = text;
    // Replace each "Response X" with the actual model name
    Object.entries(labelToModel).forEach(([label, model]) => {
        const modelShortName = getShortModelName(model);
        result = result.replace(new RegExp(label, 'g'), `**${modelShortName}**`);
    });
    return result;
}

// Helper to convert hex to rgb for CSS variable
function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}` : '255, 255, 255';
}

export default function Stage2({ rankings, labelToModel, aggregateRankings, startTime, endTime, canonicalClaims, aggregateClaimVerdicts, onRetryProvider, onFireProvider }) {
    const [activeTab, setActiveTab] = useState(0);
    const [viewMode, setViewMode] = useState('leaderboard'); // 'leaderboard' or 'heatmap'
    const [isCopied, setIsCopied] = useState(false);

    // Reset activeTab if it becomes out of bounds (e.g., during streaming)
    useEffect(() => {
        if (rankings && rankings.length > 0 && activeTab >= rankings.length) {
            const timer = setTimeout(() => {
                setActiveTab(rankings.length - 1);
            }, 0);
            return () => clearTimeout(timer);
        }
    }, [rankings, activeTab]);

    // Reset copy state when tab changes
    useEffect(() => {
        const timer = setTimeout(() => {
            setIsCopied(false);
        }, 0);
        return () => clearTimeout(timer);
    }, [activeTab]);

    if (!rankings || rankings.length === 0) {
        return null;
    }

    // Ensure activeTab is within bounds
    const safeActiveTab = Math.min(activeTab, rankings.length - 1);
    const currentRanking = rankings[safeActiveTab] || {};
    const currentStatus = getRequestStatus(currentRanking);
    const hasError = currentStatus === 'failed' || currentStatus === 'unaccounted';

    // Get visuals for current tab
    const currentVisuals = getModelVisuals(currentRanking?.model);
    const knownLabels = labelToModel ? new Set(Object.keys(labelToModel)) : null;
    const parsedRanking = (currentRanking?.parsed_ranking || []).filter(
        (label) => !knownLabels || knownLabels.has(label)
    );
    const anonymizedLabelText = labelToModel
        ? Object.keys(labelToModel).join(', ')
        : 'Response A, Response B, etc.';

    const isClaimMode = !!(canonicalClaims && aggregateClaimVerdicts);

    const handleCopy = async () => {
        const ranking = currentRanking?.ranking;
        const rankingText = typeof ranking === 'string' ? ranking : String(ranking || '');
        const textToCopy = deAnonymizeText(rankingText, labelToModel);

        if (!textToCopy) return;

        const copied = await copyToClipboard(textToCopy);
        if (copied) {
            setIsCopied(true);
            setTimeout(() => setIsCopied(false), 2000);
        }
    };

    return (
        <div className="stage-container stage-2">
            <div className="stage-header">
                <div className="stage-title">
                    <span className="stage-icon">⚖️</span>
                    Stage 2: Peer Rankings
                </div>
                <StageTimer startTime={startTime} endTime={endTime} label="Duration" />
            </div>

            {/* Claim Mode: show ClaimCards as the primary view */}
            {isClaimMode && (
                <ClaimCardWithVerdicts
                    claims={canonicalClaims}
                    aggregatedVerdicts={aggregateClaimVerdicts}
                    labelToModel={labelToModel}
                    stage2Results={rankings}
                />
            )}

            {isClaimMode ? (
                <details className="raw-evaluations-collapse">
                    <summary className="raw-evaluations-toggle">
                        Show Raw Evaluations ({rankings?.length || 0} evaluators)
                    </summary>
                    <div style={{ marginTop: '12px' }}>
                        <RawEvaluationTabs
                            rankings={rankings}
                            labelToModel={labelToModel}
                            activeTab={activeTab}
                            setActiveTab={setActiveTab}
                            currentRanking={currentRanking}
                            currentVisuals={currentVisuals}
                            hasError={hasError}
                            isCopied={isCopied}
                            handleCopy={handleCopy}
                            safeActiveTab={safeActiveTab}
                            anonymizedLabelText={anonymizedLabelText}
                            parsedRanking={parsedRanking}
                            onRetryProvider={onRetryProvider}
                            onFireProvider={onFireProvider}
                        />
                    </div>
                </details>
            ) : (
                <>
                    <h4>Raw Evaluations</h4>
                    <p className="stage-description">
                        Each model evaluated all responses (anonymized as {anonymizedLabelText}) and provided rankings.
                        Below, model names are shown in <strong>bold</strong> for readability, but the original evaluation used anonymous labels.
                    </p>
                    <RawEvaluationTabs
                        rankings={rankings}
                        labelToModel={labelToModel}
                        activeTab={activeTab}
                        setActiveTab={setActiveTab}
                        currentRanking={currentRanking}
                        currentVisuals={currentVisuals}
                        hasError={hasError}
                        isCopied={isCopied}
                        handleCopy={handleCopy}
                        safeActiveTab={safeActiveTab}
                        anonymizedLabelText={anonymizedLabelText}
                        parsedRanking={parsedRanking}
                        onRetryProvider={onRetryProvider}
                        onFireProvider={onFireProvider}
                    />
                </>
            )}

            {aggregateRankings && aggregateRankings.length > 0 && (
                <div className="aggregate-rankings">
                    <div className="aggregate-header-row">
                        <div className="aggregate-title-group">
                            <h4>🏆 Stage 2 Results</h4>
                            <p className="stage-description">
                                {viewMode === 'leaderboard' || aggregateRankings.length < 3
                                    ? 'Combined results across all peer evaluations. Bar length corresponds to average rank value.'
                                    : 'Detailed matrix of anonymous peer evaluations.'
                                }
                            </p>
                        </div>
                        {aggregateRankings.length >= 3 && (
                            <div className="view-mode-toggle">
                                <button
                                    className={`toggle-btn ${viewMode === 'leaderboard' ? 'active' : ''}`}
                                    onClick={() => setViewMode('leaderboard')}
                                    title="Show Leaderboard List"
                                >
                                    🏆 Leaderboard
                                </button>
                                <button
                                    className={`toggle-btn ${viewMode === 'heatmap' ? 'active' : ''}`}
                                    onClick={() => setViewMode('heatmap')}
                                    title="Show Detailed Matrix"
                                >
                                    📊 Detail Matrix
                                </button>
                            </div>
                        )}
                    </div>

                    {viewMode === 'leaderboard' || aggregateRankings.length < 3 ? (
                        <div className="aggregate-list animate-fade-in">
                            {aggregateRankings.map((agg, index) => {
                                const visuals = getModelVisuals(agg.model);
                                const shortName = getShortModelName(agg.model);

                                // Calculate bar width proportional to the rank value
                                // Higher rank = longer bar (matches the number visually)
                                const maxRank = aggregateRankings.length;
                                const scorePercent = Math.max(5, Math.min(100, (agg.average_rank / maxRank) * 100));

                                return (
                                    <div key={index} className="aggregate-item">
                                        <span className="rank-position">#{index + 1}</span>

                                        <div className="rank-bar-container">
                                            <div
                                                className="rank-bar-fill"
                                                style={{
                                                    width: `${scorePercent}%`,
                                                    '--bar-color-rgb': hexToRgb(visuals.color)
                                                }}
                                            >
                                                <div className="rank-content">
                                                    <div className="rank-model-info">
                                                        <span className="mini-avatar" style={{ backgroundColor: visuals.color }}>
                                                            <ModelVisualIcon visuals={visuals} scale={0.68} />
                                                        </span>
                                                        <span className="rank-model-name">{shortName}</span>
                                                    </div>

                                                    <div className="rank-stats">
                                                        <span className="rank-score">
                                                            {agg.average_rank.toFixed(2)}
                                                        </span>
                                                        {index === 0 && <span className="trophy-icon">🏆</span>}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <RankingHeatmap rankings={rankings} labelToModel={labelToModel} />
                    )}
                </div>
            )}
        </div>
    );
}

export function Stage2Skeleton() {
    return (
        <div className="stage-container stage-2 skeleton-mode">
            <div className="stage-header">
                <div className="stage-title">
                    <span className="stage-icon">⚖️</span>
                    Stage 2: Peer Rankings
                </div>
                <div className="stage-timer-skeleton">
                    <Skeleton variant="text" width="60px" />
                </div>
            </div>

            <h4><Skeleton variant="text" width="150px" /></h4>
            <div className="stage-description">
                <Skeleton variant="text" width="100%" />
                <Skeleton variant="text" width="80%" />
            </div>

            {/* Tabs Skeleton */}
            <div className="tabs">
                {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="tab skeleton-tab">
                        <Skeleton variant="circle" width="24px" height="24px" style={{ marginBottom: '8px' }} />
                        <Skeleton variant="text" width="50%" height="0.8em" />
                    </div>
                ))}
            </div>

            <div className="tab-content glass-panel" style={{ minHeight: '300px' }}>
                <div className="model-header">
                    <div className="model-identity">
                        <Skeleton variant="avatar" />
                        <div className="model-info" style={{ gap: '4px', display: 'flex', flexDirection: 'column' }}>
                            <Skeleton variant="text" width="120px" height="1.2em" />
                            <Skeleton variant="text" width="80px" height="0.8em" />
                        </div>
                    </div>
                </div>

                <div className="ranking-content" style={{ marginTop: '20px' }}>
                    <Skeleton variant="text" width="100%" />
                    <Skeleton variant="text" width="90%" />
                    <Skeleton variant="text" width="95%" />
                    <Skeleton variant="text" width="85%" />
                </div>
            </div>

            <div className="aggregate-rankings" style={{ marginTop: '20px' }}>
                <h4><Skeleton variant="text" width="180px" /></h4>
                <div className="stage-description">
                    <Skeleton variant="text" width="90%" />
                </div>

                <div className="aggregate-list">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="aggregate-item" style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                            <Skeleton variant="text" width="20px" />
                            <div style={{ flex: 1 }}>
                                <Skeleton variant="rect" width={`${100 - (i * 15)}%`} height="32px" style={{ borderRadius: '4px' }} />
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function RawEvaluationTabs({
    rankings,
    labelToModel,
    setActiveTab,
    currentRanking,
    currentVisuals,
    hasError,
    isCopied,
    handleCopy,
    safeActiveTab,
    parsedRanking,
    onRetryProvider,
    onFireProvider
}) {
    const currentStatus = getRequestStatus(currentRanking);
    const isRankingFormatError = ['invalid_evaluator_output', 'truncated_evaluator_output'].includes(currentRanking?.status);
    const isTruncatedEvaluatorOutput = currentRanking?.status === 'truncated_evaluator_output';
    const isProviderError = currentRanking?.status === 'provider_error';
    const isEvaluatorRefusal = currentRanking?.status === 'evaluator_refused'
        || looksLikeEvaluatorRefusal(currentRanking?.ranking);

    return (
        <>
            {/* Avatar Tabs */}
            <div className="tabs">
                {rankings.map((rank, index) => {
                    const visuals = getModelVisuals(rank?.model);
                    const shortName = getShortModelName(rank?.model);
                    const status = getRequestStatus(rank);
                    const statusError = status === 'failed' || status === 'unaccounted';

                    return (
                        <button
                            key={rank?.model || index}
                            className={`tab ${safeActiveTab === index ? 'active' : ''} ${statusError ? 'tab-error' : ''}`}
                            onClick={() => setActiveTab(index)}
                            style={safeActiveTab === index ? { borderColor: visuals.color, color: visuals.color } : {}}
                            title={`${rank?.model || 'Unknown model'} — ${getRequestStatusLabel(status)}`}
                        >
                            <span className="tab-icon" style={{ backgroundColor: safeActiveTab === index ? 'transparent' : 'rgba(255,255,255,0.1)' }}>
                                <ModelVisualIcon visuals={visuals} scale={0.7} />
                            </span>
                            <span className="tab-name">{shortName}</span>
                            {statusError && <span className="error-badge" style={{ backgroundColor: '#ef4444' }}>!</span>}
                            {status === 'running' && <span className="error-badge" style={{ backgroundColor: '#3b82f6' }}>↻</span>}
                            {status === 'queued' && <span className="error-badge" style={{ backgroundColor: '#6b7280' }}>…</span>}
                            {status === 'paused' && <span className="error-badge" style={{ backgroundColor: '#d97706' }}>Ⅱ</span>}
                        </button>
                    );
                })}
            </div>

            <div className="tab-content glass-panel">
                <div className="model-header">
                    <div className="model-identity">
                        <span className="model-avatar" style={{ backgroundColor: hasError ? '#ef4444' : currentVisuals.color }}>
                            <ModelVisualIcon visuals={currentVisuals} scale={0.72} />
                        </span>
                        <div className="model-info">
                            <span className="model-name-large" title={currentRanking.model || ''}>
                                {getShortModelName(currentRanking.model)}
                            </span>
                            <span className="model-provider-badge" style={{ borderColor: currentVisuals.color, color: currentVisuals.color }}>
                                {currentVisuals.name}
                            </span>
                        </div>
                    </div>

                    <div className="header-actions">
                        {currentStatus === 'completed' && (
                            <button
                                className={`copy-button ${isCopied ? 'copied' : ''}`}
                                onClick={handleCopy}
                                title="Copy to clipboard"
                            >
                                {isCopied ? (
                                    <>
                                        <span className="icon">✓</span>
                                        <span className="label">Copied</span>
                                    </>
                                ) : (
                                    <>
                                        <span className="icon">📋</span>
                                        <span className="label">Copy</span>
                                    </>
                                )}
                            </button>
                        )}

                        <span className={`model-status ${currentStatus}`}>
                            {getRequestStatusLabel(currentStatus)}
                        </span>
                    </div>
                </div>

                {currentStatus === 'queued' ? (
                    <Stage2RequestState
                        icon="⏳"
                        title="Queued"
                        message="Waiting for an execution slot. This ranking request has not been dispatched yet."
                    />
                ) : currentStatus === 'running' ? (
                    <Stage2RequestState
                        icon="↻"
                        title="Request Running"
                        message="The request was dispatched and the model is actively evaluating the peer responses."
                        accent="#60a5fa"
                    />
                ) : currentStatus === 'paused' ? (
                    <div className="response-pending" style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '20px 0' }}>
                        <Stage2RequestState
                            icon="⏸"
                            title="Request Paused"
                            message="The run is paused before this ranking request starts. Resume the run or trigger it individually."
                            accent="#fbbf24"
                        />
                        {onFireProvider && (
                            <button
                                className="fire-provider-button"
                                onClick={() => onFireProvider(currentRanking.model, 'stage2')}
                                style={stage2FireButtonStyle}
                            >
                                ▶ Run This Request
                            </button>
                        )}
                    </div>
                ) : hasError ? (
                    <div className="response-error" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
                            <div className="error-icon">⚠️</div>
                            <div className="error-details">
                                <div className="error-title">
                                    {currentStatus === 'unaccounted'
                                        ? 'Request Result Missing'
                                        : isEvaluatorRefusal
                                            ? 'Evaluator Refused Task'
                                            : isTruncatedEvaluatorOutput
                                                ? 'Evaluator Output Truncated'
                                                : isRankingFormatError
                                                    ? 'Ranking Missing or Unparseable'
                                                    : isProviderError
                                                        ? 'Provider Request Failed'
                                                        : 'Ranking Request Failed'}
                                </div>
                                <div className="error-message">{currentRanking?.error_message || 'Unknown error'}</div>
                            </div>
                        </div>
                        {(isRankingFormatError || isEvaluatorRefusal) && currentRanking?.ranking && (
                            <details className="raw-evaluations-collapse">
                                <summary className="raw-evaluations-toggle">Show unparsed model response</summary>
                                <MarkdownContent className="ranking-content">
                                    {deAnonymizeText(
                                        typeof currentRanking.ranking === 'string'
                                            ? currentRanking.ranking
                                            : String(currentRanking.ranking),
                                        labelToModel
                                    )}
                                </MarkdownContent>
                            </details>
                        )}
                        {onRetryProvider && !currentRanking.retrying && currentStatus !== 'unaccounted' && (
                            <button
                                className="retry-provider-button"
                                onClick={() => onRetryProvider(currentRanking.model, 'stage2')}
                                style={{
                                    alignSelf: 'flex-start',
                                    background: 'rgba(59,130,246,0.1)',
                                    border: '1px solid rgba(59,130,246,0.4)',
                                    color: '#60a5fa',
                                    padding: '6px 14px',
                                    borderRadius: '6px',
                                    cursor: 'pointer',
                                    fontSize: '12px',
                                    fontWeight: '500',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '6px',
                                    transition: 'all 0.15s ease'
                                }}
                            >
                                ↺ Retry {getShortModelName(currentRanking.model)}
                            </button>
                        )}
                        {currentRanking.retrying && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#60a5fa', fontSize: '13px' }}>
                                <span className="retrying-indicator">↺</span> Retrying {getShortModelName(currentRanking.model)}...
                            </div>
                        )}
                    </div>
                ) : (
                    <>
                        <MarkdownContent className="ranking-content">
                            {(() => {
                                const ranking = currentRanking?.ranking;
                                const rankingText = typeof ranking === 'string' ? ranking : String(ranking || '');
                                return deAnonymizeText(rankingText, labelToModel);
                            })()}
                        </MarkdownContent>

                        {parsedRanking.length > 0 && (
                            <div className="parsed-ranking">
                                <strong>Extracted Ranking:</strong>
                                <span className="info-tooltip-container">
                                    <span className="info-icon">?</span>
                                    <span className="info-tooltip">
                                        This is the ranking parsed from the model's text response.
                                        It's used to calculate the aggregate rankings below.
                                        Compare with the text above to verify the system correctly understood the model's ranking.
                                    </span>
                                </span>
                                <ol>
                                    {parsedRanking.map((label, i) => (
                                        <li key={i}>
                                            {labelToModel && labelToModel[label]
                                                ? getShortModelName(labelToModel[label])
                                                : label}
                                        </li>
                                    ))}
                                </ol>
                            </div>
                        )}
                    </>
                )}
            </div>
        </>
    );
}


function Stage2RequestState({ icon, title, message, accent = '#e5e7eb' }) {
    return (
        <div style={{ display: 'flex', gap: '14px', alignItems: 'center', padding: '20px 0' }} role="status">
            <div style={{ fontSize: '24px', color: accent }}>{icon}</div>
            <div>
                <div style={{ fontSize: '15px', fontWeight: '600', color: accent }}>{title}</div>
                <div style={{ fontSize: '13px', color: '#94a3b8' }}>{message}</div>
            </div>
        </div>
    );
}

const stage2FireButtonStyle = {
    alignSelf: 'flex-start',
    background: 'rgba(16,185,129,0.1)',
    border: '1px solid rgba(16,185,129,0.4)',
    color: '#10b981',
    padding: '6px 14px',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '12px',
    fontWeight: '500',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    transition: 'all 0.15s ease'
};

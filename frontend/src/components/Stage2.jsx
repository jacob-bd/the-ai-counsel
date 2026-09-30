import { useState, useEffect } from 'react';
import Skeleton from './common/Skeleton';
import MarkdownContent from './MarkdownContent';
import { getModelVisuals, getShortModelName } from '../utils/modelHelpers';
import RankingHeatmap from './RankingHeatmap';
import { ClaimCardWithVerdicts } from './ClaimCards';
import './Stage2.css';
import './ClaimCards.css';
import StageTimer from './StageTimer';
import { copyToClipboard } from '../utils/clipboard';
import { useI18n } from '../i18n';

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

export default function Stage2({ rankings, labelToModel, aggregateRankings, startTime, endTime, canonicalClaims, aggregateClaimVerdicts }) {
    const { t } = useI18n();
    const [activeTab, setActiveTab] = useState(0);
    const [viewMode, setViewMode] = useState('leaderboard'); // 'leaderboard' or 'heatmap'

    // Reset activeTab if it becomes out of bounds (e.g., during streaming)
    useEffect(() => {
        if (rankings && rankings.length > 0 && activeTab >= rankings.length) {
            setActiveTab(rankings.length - 1);
        }
    }, [rankings, activeTab]);

    if (!rankings || rankings.length === 0) {
        return null;
    }

    // Ensure activeTab is within bounds
    const safeActiveTab = Math.min(activeTab, rankings.length - 1);
    const currentRanking = rankings[safeActiveTab] || {};
    const hasError = currentRanking?.error || false;

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

    // Copy functionality
    const [isCopied, setIsCopied] = useState(false);

    // Reset copy state when tab changes
    useEffect(() => {
        setIsCopied(false);
    }, [activeTab]);

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
                    {t('Stage 2: Peer Rankings')}
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
                        {t('Show Raw Evaluations ({count} evaluators)', { count: rankings?.length || 0 })}
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
                        />
                    </div>
                </details>
            ) : (
                <>
                    <h4>{t('Raw Evaluations')}</h4>
                    <p className="stage-description">
                        {t('Each model evaluated all responses (anonymized as {labels}) and provided rankings.', { labels: anonymizedLabelText })}
                        {' '}{t('Below, model names are shown in')} <strong>{t('bold')}</strong> {t('for readability, but the original evaluation used anonymous labels.')}
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
                    />
                </>
            )}

            {aggregateRankings && aggregateRankings.length > 0 && (
                <div className="aggregate-rankings">
                    <div className="aggregate-header-row">
                        <div className="aggregate-title-group">
                            <h4>{t('🏆 Stage 2 Results')}</h4>
                            <p className="stage-description">
                                {viewMode === 'leaderboard' || aggregateRankings.length < 3
                                    ? t('Combined results across all peer evaluations. Bar length corresponds to average rank value.')
                                    : t('Detailed matrix of anonymous peer evaluations.')
                                }
                            </p>
                        </div>
                        {aggregateRankings.length >= 3 && (
                            <div className="view-mode-toggle">
                                <button 
                                    className={`toggle-btn ${viewMode === 'leaderboard' ? 'active' : ''}`}
                                    onClick={() => setViewMode('leaderboard')}
                                    title={t('Show Leaderboard List')}
                                >
                                    {t('🏆 Leaderboard')}
                                </button>
                                <button 
                                    className={`toggle-btn ${viewMode === 'heatmap' ? 'active' : ''}`}
                                    onClick={() => setViewMode('heatmap')}
                                    title={t('Show Detailed Matrix')}
                                >
                                    {t('📊 Detail Matrix')}
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
                                                            {visuals.icon}
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
    const { t } = useI18n();
    return (
        <div className="stage-container stage-2 skeleton-mode">
            <div className="stage-header">
                <div className="stage-title">
                    <span className="stage-icon">⚖️</span>
                    {t('Stage 2: Peer Rankings')}
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
    activeTab,
    setActiveTab,
    currentRanking,
    currentVisuals,
    hasError,
    isCopied,
    handleCopy,
    safeActiveTab,
    anonymizedLabelText,
    parsedRanking
}) {
    const { t } = useI18n();
    return (
        <>
            {/* Avatar Tabs */}
            <div className="tabs">
                {rankings.map((rank, index) => {
                    const visuals = getModelVisuals(rank?.model);
                    const shortName = getShortModelName(rank?.model);

                    return (
                        <button
                            key={index}
                            className={`tab ${safeActiveTab === index ? 'active' : ''} ${rank?.error ? 'tab-error' : ''}`}
                            onClick={() => setActiveTab(index)}
                            style={safeActiveTab === index ? { borderColor: visuals.color, color: visuals.color } : {}}
                            title={rank?.model}
                        >
                            <span className="tab-icon" style={{ backgroundColor: safeActiveTab === index ? 'transparent' : 'rgba(255,255,255,0.1)' }}>
                                {visuals.icon}
                            </span>
                            <span className="tab-name">{shortName}</span>
                            {rank?.error && <span className="error-badge">!</span>}
                        </button>
                    );
                })}
            </div>

            <div className="tab-content glass-panel">
                <div className="model-header">
                    <div className="model-identity">
                        <span className="model-avatar" style={{ backgroundColor: hasError ? '#ef4444' : currentVisuals.color }}>
                            {currentVisuals.icon}
                        </span>
                        <div className="model-info">
                            <span className="model-name-large">{currentRanking.model || t('Unknown Model')}</span>
                            <span className="model-provider-badge" style={{ borderColor: currentVisuals.color, color: currentVisuals.color }}>
                                {currentVisuals.name}
                            </span>
                        </div>
                    </div>

                    <div className="header-actions">
                        {!hasError && (
                            <button
                                className={`copy-button ${isCopied ? 'copied' : ''}`}
                                onClick={handleCopy}
                                title={t('Copy to clipboard')}
                            >
                                {isCopied ? (
                                    <>
                                        <span className="icon">✓</span>
                                        <span className="label">{t('Copied')}</span>
                                    </>
                                ) : (
                                    <>
                                        <span className="icon">📋</span>
                                        <span className="label">{t('Copy')}</span>
                                    </>
                                )}
                            </button>
                        )}

                        {hasError ? (
                            <span className="model-status error">{t('Failed')}</span>
                        ) : (
                            <span className="model-status success">{t('Completed')}</span>
                        )}
                    </div>
                </div>

                {hasError ? (
                    <div className="response-error">
                        <div className="error-icon">⚠️</div>
                        <div className="error-details">
                            <div className="error-title">{t('Model Failed to Respond')}</div>
                            <div className="error-message">{currentRanking?.error_message || t('Unknown error')}</div>
                        </div>
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
                                <strong>{t('Extracted Ranking:')}</strong>
                                <span className="info-tooltip-container">
                                    <span className="info-icon">?</span>
                                    <span className="info-tooltip">
                                        {t("This is the ranking parsed from the model's text response. It's used to calculate the aggregate rankings below. Compare with the text above to verify the system correctly understood the model's ranking.")}
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

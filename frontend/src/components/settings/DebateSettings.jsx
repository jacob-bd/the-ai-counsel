import React from 'react';
import { useI18n } from '../../i18n';

export default function DebateSettings({
    critiqueMode,
    setCritiqueMode,
    debateRounds,
    setDebateRounds,
    autoConverge,
    setAutoConverge,
    convergenceThreshold,
    setConvergenceThreshold,
    executionMode,
}) {
    const { t } = useI18n();

    // Deliberation and Cost Meter helpers
    const getMeterInfo = (rounds) => {
        if (rounds === 1) {
            return {
                width: '20%',
                color: '#06b6d4', // Turquoise accent
                label: t('Single Pass / Instant Response'),
                desc: t('Standard one-pass response. Fastest execution, zero debate overhead, and minimal token cost.')
            };
        } else if (rounds <= 3) {
            return {
                width: rounds === 2 ? '40%' : '60%',
                color: '#06b6d4', // Turquoise accent
                label: t('Balanced Deliberation ({rounds} Rounds)', { rounds }),
                desc: t('Highly Recommended. Models engage in peer review & critique, driving optimal analytical depth without excessive token costs.')
            };
        } else {
            return {
                width: rounds === 4 ? '80%' : '100%',
                color: '#f59e0b', // Amber alert color
                label: t('Deep Reasoning ({rounds} Rounds)', { rounds }),
                desc: t('Maximum convergence depth. Warning: Consumes significantly higher API tokens and introduces noticeable latency per model.')
            };
        }
    };

    const meter = getMeterInfo(debateRounds);

    return (
        <section className="debate-settings-section">
            <div className="debate-section-header">
                <div className="debate-title-wrapper">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#06b6d4" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="debate-title-icon">
                        <path d="M17 6.1H3" />
                        <path d="M21 12H3" />
                        <path d="M17 17.9H3" />
                    </svg>
                    <h3>{t('Council Debate Config')}</h3>
                </div>
                <p className="section-description">
                    {t('Configure the multi-round iterative debate pipeline, convergence parameters, and critique formatting for the Council deliberation.')} <em>{t('Note: These settings apply strictly to the main multi-model Council and do not affect the Advisor debate setups.')}</em>
                </p>
            </div>

            <div className="settings-group debate-settings-group">
                <div className="debate-group-title">
                    <h4>{t('Critique Mode')}</h4>
                    <span className="debate-helper-badge">{t('Deliberation Protocol')}</span>
                </div>

                <div className="debate-card-stack">
                    {/* Freeform Card */}
                    <div 
                        className={`debate-mode-list-card ${critiqueMode === 'freeform' ? 'active' : ''}`}
                        onClick={() => setCritiqueMode('freeform')}
                    >
                        <div className="debate-card-header">
                            <div className="debate-card-title-block">
                                <span className="debate-card-icon-wrapper freeform-icon">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                                    </svg>
                                </span>
                                <div className="debate-card-title-text">
                                    <h5>{t('Free-form')}</h5>
                                    <p className="debate-card-concept">{t('Conversational refinement')}</p>
                                </div>
                            </div>
                            <span className="debate-badge fastest">{t('Fastest (1x cost)')}</span>
                        </div>
                        
                        <div className="debate-card-details">
                            <ul className="debate-details-list">
                                <li>
                                    <span className="bullet-label">{t('Round 1:')}</span> {t('Each model answers your question independently — no awareness of the others.')}
                                </li>
                                <li>
                                    <span className="bullet-label">{t('Round 2+:')}</span> {t("Each model receives the Chairman's synthesis from the previous round plus their ranking position, then rewrites their response based on that collective output.")}
                                </li>
                                <li>
                                    <span className="bullet-label">{t('Best for:')}</span> {t('Most questions. Fastest execution, no extra API calls, and the quality improvement per round is already significant.')}
                                </li>
                            </ul>
                        </div>
                    </div>

                    {/* Paragraph-level Card */}
                    <div 
                        className={`debate-mode-list-card ${critiqueMode === 'paragraph' ? 'active' : ''}`}
                        onClick={() => setCritiqueMode('paragraph')}
                    >
                        <div className="debate-card-header">
                            <div className="debate-card-title-block">
                                <span className="debate-card-icon-wrapper paragraph-icon">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <line x1="21" y1="6" x2="9" y2="6" />
                                        <line x1="21" y1="12" x2="9" y2="12" />
                                        <line x1="21" y1="18" x2="9" y2="18" />
                                        <rect x="3" y="5" width="2" height="2" />
                                        <rect x="3" y="11" width="2" height="2" />
                                        <rect x="3" y="17" width="2" height="2" />
                                    </svg>
                                </span>
                                <div className="debate-card-title-text">
                                    <h5>{t('Paragraph-level')}</h5>
                                    <p className="debate-card-concept">{t('Structured citation review')}</p>
                                </div>
                            </div>
                            <span className="debate-badge balanced">{t('Balanced (1.1x cost)')}</span>
                        </div>
                        
                        <div className="debate-card-details">
                            <ul className="debate-details-list">
                                <li>
                                    <span className="bullet-label">{t('Round 1:')}</span> {t('Same as Free-form, but every response is auto-numbered by paragraph ({para1}, {para2}…) before peer review. Reviewers must cite paragraph numbers in their critiques.', { para1: '[Para 1]', para2: '[Para 2]' })}
                                </li>
                                <li>
                                    <span className="bullet-label">{t('Round 2+:')}</span> {t('Each model is shown exactly which of their own paragraphs peers called strong or weak, plus up to 5 top-rated paragraphs from rival models to potentially incorporate.')}
                                </li>
                                <li>
                                    <span className="bullet-label">{t('Best for:')}</span> {t('Structured essays, multi-part answers, legal/policy analysis — any response that naturally breaks into distinct sections worth critiquing individually.')}
                                </li>
                            </ul>
                        </div>
                    </div>

                    {/* Claim-level Card */}
                    <div 
                        className={`debate-mode-list-card ${critiqueMode === 'claim' ? 'active' : ''}`}
                        onClick={() => setCritiqueMode('claim')}
                    >
                        <div className="debate-card-header">
                            <div className="debate-card-title-block">
                                <span className="debate-card-icon-wrapper claim-icon">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                                        <path d="m9 11 2 2 4-4" />
                                    </svg>
                                </span>
                                <div className="debate-card-title-text">
                                    <h5>{t('Claim-level')}</h5>
                                    <p className="debate-card-concept">{t('Factual assertion mapping')}</p>
                                </div>
                            </div>
                            <span className="debate-badge rigorous">{t('Rigorous (1.5x cost)')}</span>
                        </div>
                        
                        <div className="debate-card-details">
                            <ul className="debate-details-list">
                                <li>
                                    <span className="bullet-label">{t('Before review:')}</span> {t('The Chairman runs an extra API call to extract factual claims from all responses into structured JSON. Reviewers verdict each claim as strong, weak, or neutral — not the whole response.')}
                                </li>
                                <li>
                                    <span className="bullet-label">{t('Round 2+:')}</span> {t('Each model sees which of their own claims peers rejected, and the top claims from rivals that got strong agreement — so rewrites are targeted at specific disputed facts, not general impressions.')}
                                </li>
                                <li>
                                    <span className="bullet-label">{t('Best for:')}</span> {t('Fact-heavy queries, technical auditing, or any topic where you care about specific factual accuracy rather than overall argument quality. Adds 1 extra API call per round.')}
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>

                {/* Number of Rounds */}
                <div className="debate-rounds-section" style={{ marginTop: '32px' }}>
                    <div className="debate-group-title">
                        <h4>{t('Number of Rounds')}</h4>
                        <span className="debate-helper-badge">{t('Deliberation Depth')}</span>
                    </div>

                    <div className="rounds-segmented-bar">
                        {[1, 2, 3, 4, 5].map((n) => (
                            <button
                                key={n}
                                type="button"
                                className={`rounds-step-btn ${debateRounds === n ? 'active' : ''}`}
                                onClick={() => setDebateRounds(n)}
                            >
                                <span className="rounds-step-number">{n}</span>
                                <span className="rounds-step-label">
                                    {n === 1 ? t('Single Pass') : t('{count} Rounds', { count: n })}
                                </span>
                            </button>
                        ))}
                    </div>

                    {/* Deliberation & Cost Meter */}
                    <div className="cost-meter-container">
                        <div className="cost-meter-header">
                            <span className="cost-meter-title">{meter.label}</span>
                            <span className="cost-meter-percentage">{debateRounds === 1 ? t('Low Cost') : debateRounds <= 3 ? t('Balanced') : t('High Token Cost')}</span>
                        </div>
                        <div className="cost-meter-track">
                            <div 
                                className="cost-meter-fill animate-width" 
                                style={{ 
                                    width: meter.width, 
                                    backgroundColor: meter.color,
                                    boxShadow: `0 0 10px ${meter.color}40`
                                }}
                            />
                        </div>
                        <p className="cost-meter-description">{meter.desc}</p>
                    </div>
                </div>

                {/* Warnings / Multi-round Drawer */}
                {debateRounds > 1 ? (
                    <div className="convergence-drawer-container">
                        <div className="convergence-card">
                            <div
                                className="convergence-toggle-row"
                                onClick={() => setAutoConverge(!autoConverge)}
                            >
                                <div className="convergence-toggle-left">
                                    <div className="premium-checkbox-wrapper">
                                        <input
                                            type="checkbox"
                                            id="autoConvergeToggle"
                                            className="premium-checkbox"
                                            checked={autoConverge}
                                            onChange={(e) => setAutoConverge(e.target.checked)}
                                            onClick={(e) => e.stopPropagation()}
                                        />
                                        <label
                                            htmlFor="autoConvergeToggle"
                                            className="premium-checkbox-label"
                                            onClick={(e) => e.stopPropagation()}
                                        ></label>
                                    </div>
                                    <div className="convergence-toggle-text">
                                        <h5>{t('Auto-converge')}</h5>
                                        <p className="convergence-toggle-hint">{t('Stop early if peer rankings stabilize')}</p>
                                    </div>
                                </div>
                            </div>

                            {autoConverge && (
                                <div className="convergence-threshold-section animate-slide-down">
                                    <span className="convergence-threshold-label">{t('Required Stable Rounds')}</span>
                                    <div className="threshold-segmented-bar">
                                        {[1, 2, 3].map((n) => (
                                            <button
                                                key={n}
                                                type="button"
                                                className={`threshold-btn ${convergenceThreshold === n ? 'active' : ''}`}
                                                onClick={() => setConvergenceThreshold(n)}
                                            >
                                                {t('Stable Rounds: {count}', { count: n })}
                                            </button>
                                        ))}
                                    </div>
                                    <p className="setting-hint threshold-hint">
                                        {t('Early stopping triggers if the relative rankings of all response drafts remain identical for {count} consecutive rounds. Saves significant API tokens!', { count: convergenceThreshold })}
                                    </p>
                                </div>
                            )}
                        </div>

                        {executionMode === 'chat_only' && (
                            <div className="debate-warning-banner">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="warning-banner-icon">
                                    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                                    <line x1="12" y1="9" x2="12" y2="13" />
                                    <line x1="12" y1="17" x2="12.01" y2="17" />
                                </svg>
                                <span>{t('Multi-round debate is configured but currently not active. Change Execution Mode to')} <strong>{t('Chat + Ranking')}</strong> {t('or')} <strong>{t('Full Deliberation')}</strong> {t('in the main screen to enable it.')}</span>
                            </div>
                        )}
                    </div>
                ) : (
                    executionMode !== 'chat_only' ? null : (
                        <div className="debate-warning-banner" style={{ marginTop: '20px' }}>
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="warning-banner-icon">
                                <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                                <line x1="12" y1="9" x2="12" y2="13" />
                                <line x1="12" y1="17" x2="12.01" y2="17" />
                            </svg>
                            <span>{t('Execution Mode is currently')} <strong>{t('Chat Only')}</strong>. {t('Deliberative peer review stages and synthetic convergence are bypassed.')}</span>
                        </div>
                    )
                )}
            </div>
        </section>
    );
}

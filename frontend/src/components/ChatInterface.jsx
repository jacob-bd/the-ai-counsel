import StageTimer from './StageTimer';
import { useState, useEffect, useLayoutEffect, useRef } from 'react';
import SearchContext from './SearchContext';
import Stage1, { Stage1Skeleton } from './Stage1';
import Stage2, { Stage2Skeleton } from './Stage2';
import Stage3, { Stage3Skeleton } from './Stage3';
import CouncilGrid from './CouncilGrid';
import CouncilSetup from './CouncilSetup';
import ExecutionModeToggle from './ExecutionModeToggle';
import DebateView from './DebateView';
import AdvisorSetup from './AdvisorSetup';
import MarkdownContent from './MarkdownContent';
import Stage4, { Stage4Skeleton } from './Stage4';
import RoundNavigator from './RoundNavigator';
import CostReport from './CostReport';
import './ChatInterface.css';

function hasStage1Results(msg) {
    return Array.isArray(msg.stage1) && msg.stage1.length > 0;
}

function hasStage2Results(msg) {
    return Array.isArray(msg.stage2) && msg.stage2.length > 0;
}

function hasStage2Started(msg) {
    return Boolean(msg.loading?.stage2 || hasStage2Results(msg));
}

function shouldShowStage1CouncilGrid(msg) {
    return msg.loading?.stage1 || (hasStage1Results(msg) && !hasStage2Started(msg));
}

function shouldShowStage1Results(msg) {
    return msg.loading?.stage1 || hasStage1Results(msg);
}

function getDeliberationScrollPhase(msg) {
    if (!msg || msg.role !== 'assistant') return 'idle';
    if (msg.loading?.stage3 || msg.stage3) return 'stage3';
    if (hasStage2Started(msg)) return 'stage2';
    if (msg.loading?.stage1 || hasStage1Results(msg)) return 'stage1';
    if (msg.loading?.search) return 'search';
    return 'idle';
}

function renderStage1Content(msg) {
    if (!shouldShowStage1Results(msg)) return null;
    if (msg.loading?.stage1 && !hasStage1Results(msg)) return <Stage1Skeleton />;
    if (!hasStage1Results(msg)) return null;
    return (
        <Stage1
            responses={msg.stage1}
            startTime={msg.timers?.stage1Start}
            endTime={msg.timers?.stage1End}
        />
    );
}

function isCouncilTurnPending(msg, isActiveTurn, isLoading) {
    if (!isActiveTurn || !isLoading || msg.error || msg.aborted) return false;
    if (msg.loading?.search || msg.loading?.stage1 || msg.loading?.stage2 || msg.loading?.stage3) {
        return false;
    }
    if (hasStage1Results(msg) || hasStage2Results(msg) || msg.stage3) return false;
    if (msg.metadata?.search_context) return false;
    return true;
}

export default function ChatInterface({
    conversation,
    onSendMessage,
    onAbort,
    isLoading,
    councilConfigured,
    onOpenSettings,
    councilModels = [],
    chairmanModel = null,
    executionMode,
    onExecutionModeChange,
    searchProvider = 'duckduckgo',
    availableSearchProviders = [{ id: 'duckduckgo', name: 'DuckDuckGo' }],
    mode = 'council',
    onStartDebate,
    onNewConversation,
    onCouncilChange,
}) {
    const [input, setInput] = useState('');
    const [activeSearchProvider, setActiveSearchProvider] = useState(null);
    const [searchPopoverOpen, setSearchPopoverOpen] = useState(false);
    const searchPopoverRef = useRef(null);
    const messagesEndRef = useRef(null);
    const messagesContainerRef = useRef(null);
    const stage2AnchorRef = useRef(null);
    const stage3AnchorRef = useRef(null);
    const prevScrollPhaseRef = useRef(null);

    useLayoutEffect(() => {
        if (!messagesContainerRef.current || !conversation?.messages?.length) return;

        const container = messagesContainerRef.current;
        const lastMsg = conversation.messages[conversation.messages.length - 1];
        const phase = getDeliberationScrollPhase(lastMsg);
        const prevPhase = prevScrollPhaseRef.current;
        prevScrollPhaseRef.current = phase;

        const scrollAnchors = {
            'stage1->stage2': stage2AnchorRef,
            'stage2->stage3': stage3AnchorRef,
        };
        const anchorRef = scrollAnchors[`${prevPhase}->${phase}`];
        if (anchorRef) {
            requestAnimationFrame(() => {
                anchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
            return;
        }

        const isNearBottom =
            container.scrollHeight - container.scrollTop - container.clientHeight < 150;

        if (isNearBottom) {
            messagesEndRef.current?.scrollIntoView({ behavior: isLoading ? 'auto' : 'smooth' });
        }
    }, [conversation]);

    useEffect(() => {
        const handleClickOutside = (e) => {
            if (searchPopoverRef.current && !searchPopoverRef.current.contains(e.target)) {
                setSearchPopoverOpen(false);
            }
        };
        if (searchPopoverOpen) document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [searchPopoverOpen]);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (input.trim() && !isLoading) {
            onSendMessage(input, activeSearchProvider);
            setInput('');
        }
    };

    const handleKeyDown = (e) => {
        // Submit on Enter (without Shift)
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
        }
    };

    if (!conversation) {
        if (mode === 'advisors') {
            return (
                <div className="chat-interface advisor-mode">
                    <div className="advisor-setup-scroll">
                        <AdvisorSetup
                            onStartDebate={onStartDebate}
                            isLoading={isLoading}
                        />
                    </div>
                </div>
            );
        }
        return (
            <div className="chat-interface">
                <div className="empty-state">
                    <h1>Welcome to The AI <span className="plus-text">Counsel</span></h1>
                    <p className="hero-message">
                        Configure your council below, then start a session or ask your question.
                    </p>
                    <div className="welcome-grid-container">
                        <CouncilSetup
                            councilModels={councilModels}
                            chairmanModel={chairmanModel}
                            executionMode={executionMode}
                            editable
                            onCouncilChange={onCouncilChange}
                            onOpenSettings={onOpenSettings}
                        />
                    </div>
                    <button className="start-session-btn start-session-btn--secondary" onClick={onNewConversation}>
                        <span className="btn-content">
                            <span className="btn-icon">✨</span>
                            Start a New Council Session
                        </span>
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="chat-interface">
            {/* Messages Area */}
            <div className="messages-area" ref={messagesContainerRef}>
                {mode === 'advisors' && conversation.messages.length === 0 ? (
                    <div className="advisor-setup-scroll">
                        <AdvisorSetup
                            onStartDebate={onStartDebate}
                            isLoading={isLoading}
                        />
                    </div>
                ) : (conversation.messages.length === 0) ? (
                    <div className="hero-container">
                        <div className="hero-content">
                            <h1>Welcome to The AI <span className="text-gradient">Counsel</span></h1>
                            <p className="hero-subtitle">
                                Configure your council below, then ask your question.
                            </p>
                            <div className="welcome-grid-container">
                                <CouncilSetup
                                    councilModels={councilModels}
                                    chairmanModel={chairmanModel}
                                    executionMode={executionMode}
                                    editable
                                    onCouncilChange={onCouncilChange}
                                    onOpenSettings={onOpenSettings}
                                />
                            </div>
                        </div>
                    </div>
                ) : (
                    conversation.messages.map((msg, index) => {
                        const isActiveCouncilTurn = msg.role === 'assistant'
                            && index === conversation.messages.length - 1
                            && isLoading;

                        return (
                        <div key={`${conversation.id}-msg-${index}`} className={`message ${msg.role}`}>
                            <div className="message-role" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                <span>
                                    {msg.role === 'user'
                                        ? (mode === 'advisors' ? 'Your Question' : 'Your Question to the Council')
                                        : (mode === 'advisors' ? 'Advisor Panel' : 'LLM Council')}
                                </span>
                                {msg.role === 'assistant' && msg.type !== 'advisor_debate' && (() => {
                                    const knownMode = msg.metadata?.execution_mode
                                        || (index === conversation.messages.length - 1 ? executionMode : null);
                                    if (!knownMode) return null;

                                    const rounds = msg.metadata?.rounds?.length || msg.metadata?.debate_rounds_configured || 1;
                                    const critique = msg.metadata?.critique_mode || 'freeform';
                                    let label;
                                    if (knownMode === 'chat_only') label = '💬 Chat Only';
                                    else if (knownMode === 'chat_ranking') label = '⚖️ Chat + Ranking';
                                    else if (knownMode === 'full') {
                                        if (rounds > 1) {
                                            const capitalizedCritique = critique.charAt(0).toUpperCase() + critique.slice(1);
                                            label = `🏛️ Full Debate (${rounds} Rds • ${capitalizedCritique})`;
                                        } else {
                                            label = '🏛️ Full Deliberation';
                                        }
                                    } else {
                                        label = '🏛️ Deliberation';
                                    }
                                    return <span className="debate-mode-pill">{label}</span>;
                                })()}
                            </div>

                            <div className="message-content">
                                {msg.role === 'user' ? (
                                    <MarkdownContent>{msg.content}</MarkdownContent>
                                ) : (msg.mode === 'advisors' || msg.type === 'advisor_debate') ? (
                                    <DebateView
                                        personas={msg.personas || []}
                                        rounds={msg.rounds || []}
                                        verdict={msg.verdict || null}
                                        tiebreaker={msg.tiebreaker || null}
                                        currentRound={msg.currentRound || msg.rounds?.length || 1}
                                        maxRounds={msg.maxRounds || msg.metadata?.max_rounds || 3}
                                        isRunning={msg.isRunning || false}
                                        question={msg.question || ''}
                                        webSearch={msg.webSearch}
                                        error={msg.error || null}
                                        costReport={msg.metadata?.cost_report}
                                    />
                                ) : (
                                    <CouncilMessageRenderer
                                        msg={msg}
                                        isActiveCouncilTurn={isActiveCouncilTurn}
                                        councilModels={councilModels}
                                        chairmanModel={chairmanModel}
                                        executionMode={executionMode}
                                        availableSearchProviders={availableSearchProviders}
                                        searchProvider={searchProvider}
                                        activeSearchProvider={activeSearchProvider}
                                        isLoading={isLoading}
                                        stage2AnchorRef={stage2AnchorRef}
                                        stage3AnchorRef={stage3AnchorRef}
                                    />
                                )}
                            </div>
                        </div>
                        );
                    })
                )}

                {/* Bottom Spacer for floating input */}
                <div ref={messagesEndRef} style={{ height: '20px' }} />
            </div>

            {/* Floating Command Capsule — hidden for advisor debates */}
            {mode !== 'advisors' && <div className="input-area">
                {!councilConfigured ? (
                    <div className="input-container config-required">
                        <span className="config-message">
                            ⚠️ Council not ready — add at least one member
                            {executionMode === 'full' ? ' and a chairman' : ''}.
                            <button className="config-link" onClick={() => onOpenSettings('llm_keys')}>Configure API Keys</button>
                        </span>
                    </div>
                ) : (
                    <form className="input-container" onSubmit={handleSubmit}>
                        <div className="input-row-top">
                            <div className="search-provider-picker" ref={searchPopoverRef}>
                                <button
                                    type="button"
                                    className={`search-toggle ${activeSearchProvider ? 'active' : ''}`}
                                    onClick={() => !isLoading && setSearchPopoverOpen((v) => !v)}
                                    disabled={isLoading}
                                    title={activeSearchProvider ? `Search: ${availableSearchProviders.find(p => p.id === activeSearchProvider)?.name || activeSearchProvider}` : 'Web Search Off'}
                                    aria-haspopup="listbox"
                                    aria-expanded={searchPopoverOpen}
                                >
                                    <span className="search-icon">🌐</span>
                                    {activeSearchProvider && (
                                        <span className="search-label">
                                            {availableSearchProviders.find(p => p.id === activeSearchProvider)?.name || activeSearchProvider}
                                        </span>
                                    )}
                                </button>
                                {searchPopoverOpen && (
                                    <div className="search-popover" role="listbox">
                                        <button
                                            type="button"
                                            className={`search-popover-option ${!activeSearchProvider ? 'search-popover-option--selected' : ''}`}
                                            onClick={() => { setActiveSearchProvider(null); setSearchPopoverOpen(false); }}
                                        >
                                            <span className="search-popover-option-icon">✕</span>
                                            Off
                                        </button>
                                        {availableSearchProviders.map((p) => (
                                            <button
                                                key={p.id}
                                                type="button"
                                                className={`search-popover-option ${activeSearchProvider === p.id ? 'search-popover-option--selected' : ''}`}
                                                onClick={() => { setActiveSearchProvider(p.id); setSearchPopoverOpen(false); }}
                                            >
                                                <span className="search-popover-option-icon">🌐</span>
                                                {p.name}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>

                            <textarea
                                className="message-input"
                                placeholder={isLoading ? "Consulting..." : "Ask the Council..."}
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                disabled={isLoading}
                                rows={1}
                                style={{ height: 'auto', minHeight: '24px' }}
                            />

                            {isLoading ? (
                                <button type="button" className="send-button stop-button" onClick={onAbort} title="Stop Generation">
                                    ⏹
                                </button>
                            ) : (
                                <button type="submit" className="send-button" disabled={!input.trim()}>
                                    ➤
                                </button>
                            )}
                        </div>

                        <div className="input-row-bottom">
                            <ExecutionModeToggle
                                value={executionMode}
                                onChange={onExecutionModeChange}
                                disabled={isLoading}
                            />
                        </div>
                    </form>
                )}
            </div>}
        </div>
    );
}

function CouncilMessageRenderer({
    msg,
    isActiveCouncilTurn,
    councilModels,
    chairmanModel,
    executionMode,
    availableSearchProviders,
    searchProvider,
    activeSearchProvider,
    isLoading,
    stage2AnchorRef,
    stage3AnchorRef,
}) {
    const [selectedRound, setSelectedRound] = useState(null);

    const hasRounds = Array.isArray(msg.metadata?.rounds) && msg.metadata.rounds.length > 0;
    const totalRounds = hasRounds 
        ? msg.metadata.rounds.length 
        : (msg.metadata?.debate_rounds_configured || 1);
    const currentActiveRound = msg.metadata?.current_round || 1;

    useEffect(() => {
        if (!hasRounds) {
            setSelectedRound(null);
        }
    }, [hasRounds]);

    const activeRoundNum = selectedRound !== null 
        ? selectedRound 
        : (hasRounds ? msg.metadata.rounds.length : currentActiveRound);

    let displayStage1 = msg.stage1;
    let displayStage2 = msg.stage2;
    let displayStage3 = msg.stage3;
    let displayMetadata = msg.metadata || {};

    if (hasRounds && msg.metadata.rounds[activeRoundNum - 1]) {
        const roundData = msg.metadata.rounds[activeRoundNum - 1];
        displayStage1 = roundData.stage1;
        displayStage2 = roundData.stage2;
        displayStage3 = roundData.stage3;
        displayMetadata = { ...msg.metadata, ...(roundData.metadata || {}) };
    }

    const showStage1 = msg.loading?.stage1 || (Array.isArray(displayStage1) && displayStage1.length > 0);
    const showStage2 = msg.loading?.stage2 || (Array.isArray(displayStage2) && displayStage2.length > 0);
    const showStage3 = msg.loading?.stage3 || displayStage3;
    const showStage4 = msg.loading?.stage4 || displayMetadata.stage4;

    return (
        <>
            {msg.error && (
                <div className="council-error">
                    <span className="council-error-icon">⚠️</span>
                    <span className="council-error-text">{msg.error}</span>
                </div>
            )}

            {isCouncilTurnPending(msg, isActiveCouncilTurn, isLoading) && (
                <div className="stage-loading">
                    <div className="spinner"></div>
                    <span>Consulting the council…</span>
                </div>
            )}

            {/* Search Loading */}
            {msg.loading?.search && (
                <div className="stage-loading">
                    <div className="spinner"></div>
                    <span>
                        🔍 Searching the web with {availableSearchProviders.find(p => p.id === (activeSearchProvider || searchProvider))?.name || 'Web'}...
                    </span>
                </div>
            )}

            {/* Search Context */}
            {displayMetadata.search_context && (
                <SearchContext
                    searchQuery={displayMetadata.search_query}
                    extractedQuery={displayMetadata.extracted_query}
                    searchContext={displayMetadata.search_context}
                />
            )}

            {/* Round Navigator */}
            {totalRounds > 1 && (
                <RoundNavigator
                    currentRound={activeRoundNum}
                    totalRounds={totalRounds}
                    converged={displayMetadata.converged}
                    onSelectRound={hasRounds ? setSelectedRound : null}
                />
            )}

            <CostReport
                report={displayMetadata.cost_report}
                title={totalRounds > 1 ? 'Debate Cost' : 'Run Cost'}
            />

            {/* Stage 1: Council Grid (during active round deliberation only) */}
            {shouldShowStage1CouncilGrid(msg) && (
                <div className="stage-container">
                    <div className="stage-header">
                        <h3>Stage 1: Council Deliberation {totalRounds > 1 && `(Round ${activeRoundNum})`}</h3>
                        {msg.timers?.stage1Start && (
                            <StageTimer
                                startTime={msg.timers.stage1Start}
                                endTime={msg.timers.stage1End}
                            />
                        )}
                    </div>
                    <CouncilGrid
                        models={councilModels}
                        chairman={chairmanModel}
                        status={msg.loading?.stage1 ? 'thinking' : 'complete'}
                        progress={{
                            currentModel: msg.progress?.stage1?.currentModel,
                            completed: displayStage1?.map(r => r.model) || []
                        }}
                        showChairman={(displayMetadata.execution_mode || executionMode) === 'full'}
                    />
                </div>
            )}

            {/* Stage 1 Content */}
            {showStage1 && (
                msg.loading?.stage1 && (!displayStage1 || displayStage1.length === 0) ? (
                    <Stage1Skeleton />
                ) : (
                    <Stage1
                        responses={displayStage1 || []}
                        startTime={msg.timers?.stage1Start}
                        endTime={msg.timers?.stage1End}
                    />
                )
            )}

            {/* Stage 2 */}
            <div
                ref={isActiveCouncilTurn ? stage2AnchorRef : null}
                className="stage-scroll-anchor"
            >
                {msg.loading?.stage2 && (!displayStage2 || displayStage2.length === 0) && <Stage2Skeleton />}
                {Array.isArray(displayStage2) && displayStage2.length > 0 && (
                    <Stage2
                        rankings={displayStage2}
                        labelToModel={displayMetadata.label_to_model}
                        aggregateRankings={displayMetadata.aggregate_rankings}
                        canonicalClaims={displayMetadata.canonical_claims}
                        aggregateClaimVerdicts={displayMetadata.aggregate_claim_verdicts}
                        startTime={msg.timers?.stage2Start}
                        endTime={msg.timers?.stage2End}
                    />
                )}
            </div>

            {/* Stage 3 */}
            <div
                ref={isActiveCouncilTurn ? stage3AnchorRef : null}
                className="stage-scroll-anchor"
            >
                {msg.loading?.stage3 && !displayStage3 && <Stage3Skeleton />}
                {displayStage3 && (
                    <Stage3
                        finalResponse={displayStage3}
                        labelToModel={displayMetadata.label_to_model}
                        startTime={msg.timers?.stage3Start}
                        endTime={msg.timers?.stage3End}
                    />
                )}
            </div>

            {/* Stage 4 */}
            {showStage4 && (
                <div className="stage-scroll-anchor">
                    {msg.loading?.stage4 && !displayMetadata.stage4 ? (
                        <Stage4Skeleton />
                    ) : (
                        <Stage4
                            correctedDraft={displayMetadata.stage4}
                            startTime={msg.timers?.stage4Start || msg.timers?.stage3End}
                            endTime={msg.timers?.stage4End}
                        />
                    )}
                </div>
            )}

            {/* Aborted Indicator */}
            {msg.aborted && (
                <div className="aborted-indicator">
                    <span className="aborted-icon">⏹</span>
                    <span className="aborted-text">
                        Generation stopped by user.
                        {displayStage1 && !displayStage3 && ' Partial results shown above.'}
                    </span>
                </div>
            )}
        </>
    );
}

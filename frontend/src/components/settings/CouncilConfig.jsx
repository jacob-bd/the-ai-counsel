import React from 'react';
import { DEFAULT_EXECUTION_MODE } from '../../api';
import SearchableModelSelect from '../SearchableModelSelect';

const DIRECT_PROVIDERS = [
    { id: 'openai', name: 'OpenAI', key: 'openai_api_key' },
    { id: 'anthropic', name: 'Anthropic', key: 'anthropic_api_key' },
    { id: 'google', name: 'Google', key: 'google_api_key' },
    { id: 'mistral', name: 'Mistral', key: 'mistral_api_key' },
    { id: 'deepseek', name: 'DeepSeek', key: 'deepseek_api_key' },
    { id: 'nvidia', name: 'NVIDIA', key: 'nvidia_api_key' },
    { id: 'opencode-zen', name: 'OpenCode Zen', key: 'opencode_api_key' },
    { id: 'opencode-go', name: 'OpenCode Go', key: 'opencode_api_key' },
];

export default function CouncilConfig({
    settings,
    ollamaStatus,
    // State
    enabledProviders,
    setEnabledProviders,
    directProviderToggles,
    setDirectProviderToggles,
    showFreeOnly,
    setShowFreeOnly,
    isLoadingModels,
    rateLimitWarning,
    councilModels,
    councilMemberFilters,
    chairmanModel,
    setChairmanModel,
    chairmanFilter,
    setChairmanFilter,
    councilTemperature,
    setCouncilTemperature,
    chairmanTemperature,
    setChairmanTemperature,
    setActiveSection,
    setActivePromptTab,
    // Debate state
    critiqueMode,
    setCritiqueMode,
    debateRounds,
    setDebateRounds,
    autoConverge,
    setAutoConverge,
    convergenceThreshold,
    setConvergenceThreshold,
    // Data
    allModels, // Result of getAllAvailableModels()
    filteredModels, // Result of getFilteredAvailableModels()
    ollamaAvailableModels,
    customEndpointName,
    customEndpointUrl,
    // Callbacks
    handleFeelingLucky,
    handleMemberFilterChange,
    handleCouncilModelChange,
    handleRemoveCouncilMember,
    handleAddCouncilMember,
    // Validation
    validationErrors = {},
    chairmanSelectRef
}) {
    // Helper: Check if a source is configured (has API key or is connected)
    const isSourceConfigured = (source) => {
        switch (source) {
            case 'openrouter': return !!settings?.openrouter_api_key_set;
            case 'ollama': return ollamaStatus?.connected;
            case 'groq': return !!settings?.groq_api_key_set;
            case 'custom': return !!(settings?.custom_endpoint_url);
            case 'openai': return !!settings?.openai_api_key_set;
            case 'anthropic': return !!settings?.anthropic_api_key_set;
            case 'google': return !!settings?.google_api_key_set;
            case 'mistral': return !!settings?.mistral_api_key_set;
            case 'deepseek': return !!settings?.deepseek_api_key_set;
            case 'nvidia': return !!settings?.nvidia_api_key_set;
            case 'opencode-zen': return !!settings?.opencode_api_key_set;
            case 'opencode-go': return !!settings?.opencode_api_key_set;
            default: return false;
        }
    };

    // Helper: Filter models by remote/local for specific use case
    const filterByRemoteLocal = (models, filter) => {
        if (filter === 'local') {
            // Only Ollama models
            return models.filter(m => m.id.startsWith('ollama:'));
        } else {
            // Remote: OpenRouter + Direct providers (exclude Ollama)
            return models.filter(m => !m.id.startsWith('ollama:'));
        }
    };

    const chairmanDisabled = (settings?.execution_mode || DEFAULT_EXECUTION_MODE) !== 'full';

    const getMemberFilter = (index) => {
        return councilMemberFilters[index] || 'remote';
    };

    return (
        <>
            <section className="settings-section">
                <h3>Available Model Sources</h3>
                <p className="section-description">
                    Toggle which providers are available for LLM Council only — the search generator, council members, and chairman.
                    Advisor debates always use every provider you configure under LLM API Keys, regardless of these toggles.
                    <br /><em style={{ opacity: 0.7, fontSize: '12px' }}>Note: Non-chat models (embeddings, image generation, speech, OCR, etc.) are automatically filtered out.</em>
                </p>

                <div className="hybrid-settings-card">
                    {/* Primary Sources */}
                    <div className="filter-group">
                        <label 
                            className={`toggle-wrapper ${!isSourceConfigured('openrouter') ? 'source-disabled' : ''}`}
                            title={!isSourceConfigured('openrouter') ? 'Not configured — add API key in LLM API Keys' : ''}
                        >
                            <div className="toggle-switch">
                                <input
                                    type="checkbox"
                                    checked={isSourceConfigured('openrouter') && enabledProviders.openrouter}
                                    onChange={(e) => setEnabledProviders(prev => ({ ...prev, openrouter: e.target.checked }))}
                                    disabled={!isSourceConfigured('openrouter')}
                                />
                                <span className="slider"></span>
                            </div>
                            <span className="toggle-text">
                                OpenRouter (Cloud)
                                {!isSourceConfigured('openrouter') && (
                                    <span className="toggle-hint"> · not configured</span>
                                )}
                            </span>
                        </label>

                        <label 
                            className={`toggle-wrapper ${!isSourceConfigured('ollama') ? 'source-disabled' : ''}`}
                            title={!isSourceConfigured('ollama') ? 'Not configured — connect Ollama in LLM API Keys' : ''}
                        >
                            <div className="toggle-switch">
                                <input
                                    type="checkbox"
                                    checked={isSourceConfigured('ollama') && enabledProviders.ollama}
                                    onChange={(e) => setEnabledProviders(prev => ({ ...prev, ollama: e.target.checked }))}
                                    disabled={!isSourceConfigured('ollama')}
                                />
                                <span className="slider"></span>
                            </div>
                            <span className="toggle-text">
                                Local (Ollama)
                                {!isSourceConfigured('ollama') && (
                                    <span className="toggle-hint"> · not configured</span>
                                )}
                            </span>
                        </label>

                        <label 
                            className={`toggle-wrapper ${!isSourceConfigured('groq') ? 'source-disabled' : ''}`}
                            title={!isSourceConfigured('groq') ? 'Not configured — add API key in LLM API Keys' : ''}
                        >
                            <div className="toggle-switch">
                                <input
                                    type="checkbox"
                                    checked={isSourceConfigured('groq') && enabledProviders.groq}
                                    onChange={(e) => setEnabledProviders(prev => ({ ...prev, groq: e.target.checked }))}
                                    disabled={!isSourceConfigured('groq')}
                                />
                                <span className="slider"></span>
                            </div>
                            <span className="toggle-text">
                                Groq (Fast Inference)
                                {!isSourceConfigured('groq') && (
                                    <span className="toggle-hint"> · not configured</span>
                                )}
                            </span>
                        </label>

                        {/* Custom Endpoint Toggle - only show if configured */}
                        {(settings?.custom_endpoint_url || customEndpointUrl) && (
                            <label className="toggle-wrapper">
                                <div className="toggle-switch">
                                    <input
                                        type="checkbox"
                                        checked={enabledProviders.custom}
                                        onChange={(e) => setEnabledProviders(prev => ({ ...prev, custom: e.target.checked }))}
                                    />
                                    <span className="slider"></span>
                                </div>
                                <span className="toggle-text">{settings?.custom_endpoint_name || customEndpointName || 'Custom Endpoint'}</span>
                            </label>
                        )}
                    </div>

                    <div className="filter-divider"></div>

                    {/* Direct Connections Master Toggle */}
                    <div className="filter-group" style={{ marginBottom: '12px' }}>
                        <label className="toggle-wrapper">
                            <div className="toggle-switch">
                                <input
                                    type="checkbox"
                                    checked={enabledProviders.direct}
                                    onChange={(e) => {
                                        const isEnabled = e.target.checked;
                                        setEnabledProviders(prev => ({ ...prev, direct: isEnabled }));
                                        // If master turned off, disable all children
                                        if (!isEnabled) {
                                            setDirectProviderToggles({
                                                openai: false,
                                                anthropic: false,
                                                google: false,
                                                mistral: false,
                                                deepseek: false,
                                                nvidia: false,
                                                'opencode-zen': false,
                                                'opencode-go': false,
                                            });
                                        }
                                    }}
                                />
                                <span className="slider"></span>
                            </div>
                            <span className="toggle-text">Direct Connections</span>
                        </label>
                    </div>

                    {/* Individual Direct Provider Toggles (purple) */}
                    <div className="direct-grid" style={{ opacity: enabledProviders.direct ? 1 : 0.7 }}>
                        {DIRECT_PROVIDERS.map(dp => {
                            const configured = isSourceConfigured(dp.id);
                            return (
                                <label 
                                    key={dp.id} 
                                    className={`toggle-wrapper ${!configured ? 'source-disabled' : ''}`}
                                    title={!configured ? 'SOURCE NOT CONFIGURED - Add API key in LLM API Keys' : ''}
                                >
                                    <div className="toggle-switch direct-toggle">
                                        <input
                                            type="checkbox"
                                            checked={configured && directProviderToggles[dp.id]}
                                            disabled={!configured}
                                            onChange={(e) => {
                                                const isEnabled = e.target.checked;
                                                setDirectProviderToggles(prev => {
                                                    const newState = { ...prev, [dp.id]: isEnabled };

                                                    // Auto-enable master if any child is enabled
                                                    if (isEnabled && !enabledProviders.direct) {
                                                        setEnabledProviders(prevEP => ({ ...prevEP, direct: true }));
                                                    }

                                                    // Auto-disable master if ALL children are disabled
                                                    const hasAnyEnabled = Object.values(newState).some(v => v);
                                                    if (!hasAnyEnabled && enabledProviders.direct) {
                                                        setEnabledProviders(prevEP => ({ ...prevEP, direct: false }));
                                                    }

                                                    return newState;
                                                });
                                            }}
                                        />
                                        <span className="slider"></span>
                                    </div>
                                    <span className="toggle-text" style={{ fontSize: '13px' }}>
                                        {dp.name}
                                    </span>
                                </label>
                            );
                        })}
                    </div>
                </div>
            </section>

            <section className="settings-section">
                <h3>Council Composition</h3>
                <div className="model-options-row">
                    <div className="model-filter-controls">
                        <label className="free-filter-label" style={{ opacity: enabledProviders.openrouter ? 1 : 0.3, cursor: enabledProviders.openrouter ? 'pointer' : 'not-allowed' }}>
                            <input
                                type="checkbox"
                                checked={showFreeOnly}
                                onChange={e => setShowFreeOnly(e.target.checked)}
                                disabled={!enabledProviders.openrouter}
                            />
                            Show free OpenRouter models only
                            <div className="info-tooltip-container">
                                <span className="info-icon">i</span>
                                <div className="info-tooltip">
                                    Free OpenRouter models are limited to 20 requests/minute and 50/day (without credits). Large councils generate many requests at once.
                                </div>
                            </div>
                        </label>
                        {isLoadingModels && <span className="loading-models">Loading models...</span>}
                    </div>
                </div>
                <div className="lucky-button-container">
                    <button
                        type="button"
                        className="lucky-button"
                        onClick={handleFeelingLucky}
                        title="Randomize models from enabled sources"
                    >
                        🎲 I'm Feeling Lucky
                    </button>
                </div>
                {/* Council Members */}
                <div className="subsection" style={{ marginTop: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                        <h4 style={{ margin: 0 }}>Council Members</h4>
                    </div>
                    <div className="council-members">
                        {councilModels.map((modelId, index) => {
                            const memberFilter = getMemberFilter(index);
                            const hasValidationError = validationErrors[`member_${index}`];
                            return (
                                <div key={index} className={`council-member-row ${hasValidationError ? 'validation-error' : ''}`}>
                                    <span className="member-label">Member {index + 1}</span>
                                    <div className="model-type-toggle">
                                        <button
                                            type="button"
                                            className={`type-btn ${memberFilter === 'remote' ? 'active' : ''}`}
                                            onClick={() => handleMemberFilterChange(index, 'remote')}
                                            disabled={!enabledProviders.openrouter && !enabledProviders.direct && !enabledProviders.groq && !enabledProviders.custom}
                                            title={!enabledProviders.openrouter && !enabledProviders.direct && !enabledProviders.groq && !enabledProviders.custom ? 'Enable a remote provider first' : ''}
                                        >
                                            Remote
                                        </button>
                                        <button
                                            type="button"
                                            className={`type-btn ${memberFilter === 'local' ? 'active' : ''}`}
                                            onClick={() => handleMemberFilterChange(index, 'local')}
                                            disabled={!enabledProviders.ollama || ollamaAvailableModels.length === 0}
                                            title={!enabledProviders.ollama || ollamaAvailableModels.length === 0 ? 'Enable and connect Ollama first' : ''}
                                        >
                                            Local
                                        </button>
                                    </div>
                                    <div className={`model-select-wrapper ${hasValidationError ? 'validation-error' : ''}`}>
                                        <SearchableModelSelect
                                            models={filterByRemoteLocal(filteredModels, memberFilter)}
                                            value={modelId}
                                            onChange={(value) => handleCouncilModelChange(index, value)}
                                            placeholder={isLoadingModels && allModels.length === 0 ? "Loading models..." : "Search models..."}
                                            isDisabled={isLoadingModels && allModels.length === 0}
                                            isLoading={isLoadingModels}
                                            allModels={allModels}
                                        />
                                        {hasValidationError && (
                                            <div className="validation-error-message">
                                                ⚠️ Please select a model or remove this member
                                            </div>
                                        )}
                                    </div>
                                    {index >= 1 && (
                                        <button
                                            type="button"
                                            className="remove-member-button"
                                            onClick={() => handleRemoveCouncilMember(index)}
                                            title="Remove member"
                                        >
                                            ×
                                        </button>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                    <button
                        type="button"
                        className="add-member-button"
                        onClick={handleAddCouncilMember}
                        disabled={filteredModels.length === 0 || councilModels.length >= 8}
                    >
                        + Add Council Member
                    </button>
                    <p className="section-description" style={{ marginTop: '8px', marginBottom: '0' }}>
                        Max 8 members. With 6+ members, requests are processed in batches.
                    </p>
                    {councilModels.length >= 6 && (
                        <div className="council-size-warning">
                            ⚠️ <strong>6+ members:</strong> Requests will be processed in batches of 3 to avoid rate limits.
                        </div>
                    )}

                    {/* Rate Limit Warning Banner */}
                    {rateLimitWarning && (
                        <div className={`rate-limit-warning ${rateLimitWarning.type}`}>
                            <span className="warning-icon">
                                {rateLimitWarning.type === 'error' ? '🛑' : '⚠️'}
                            </span>
                            <div>
                                <strong>{rateLimitWarning.title}</strong><br />
                                {rateLimitWarning.message}
                            </div>
                        </div>
                    )}

                    {/* Council Heat Slider */}
                    <div className="subsection" style={{ marginTop: '20px' }}>
                        <div className="heat-slider-header">
                            <h4>Council Heat</h4>
                            <span className="heat-value">{councilTemperature.toFixed(1)}</span>
                        </div>
                        <div className="heat-slider-container">
                            <span className="heat-icon cold">❄️</span>
                            <input
                                type="range"
                                min="0"
                                max="1"
                                step="0.1"
                                value={councilTemperature}
                                onChange={(e) => setCouncilTemperature(parseFloat(e.target.value))}
                                className="heat-slider"
                                disabled={councilModels.every(m => m.includes('gpt-5.1') || m.includes('o1-') || m.includes('o3-'))}
                            />
                            <span className="heat-icon hot">🔥</span>
                        </div>
                        {councilModels.some(m => m.includes('gpt-5.1') || m.includes('o1-') || m.includes('o3-')) && (
                            <div className="heat-warning">
                                ⚠️ Some selected models (e.g. GPT-5.1, o1) enforce fixed temperature and will ignore this setting.
                            </div>
                        )}
                        <p className="heat-note" style={{ fontSize: '11px', color: '#94a3b8', marginTop: '8px' }}>
                            ℹ️ Stage 2 (Peer Ranking) has its own temperature setting.{' '}
                            <button
                                type="button"
                                onClick={() => { setActiveSection('prompts'); setActivePromptTab('stage2'); }}
                                style={{ background: 'none', border: 'none', color: '#3b82f6', cursor: 'pointer', textDecoration: 'underline', padding: 0, fontSize: '11px' }}
                            >
                                Configure in System Prompts → Stage 2
                            </button>
                        </p>
                    </div>
                </div>
                <div className={`subsection ${chairmanDisabled ? 'subsection--disabled' : ''}`} style={{ marginTop: '24px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <h4 style={{ margin: 0 }}>Chairman Model</h4>
                        <div className="model-type-toggle">
                            <button
                                type="button"
                                className={`type-btn ${chairmanFilter === 'remote' ? 'active' : ''}`}
                                onClick={() => {
                                    setChairmanFilter('remote');
                                    setChairmanModel('');
                                }}
                                disabled={chairmanDisabled || (!enabledProviders.openrouter && !enabledProviders.direct && !enabledProviders.groq && !enabledProviders.custom)}
                                title={!enabledProviders.openrouter && !enabledProviders.direct && !enabledProviders.groq && !enabledProviders.custom ? 'Enable a remote provider first' : ''}
                            >
                                Remote
                            </button>
                            <button
                                type="button"
                                className={`type-btn ${chairmanFilter === 'local' ? 'active' : ''}`}
                                onClick={() => {
                                    setChairmanFilter('local');
                                    setChairmanModel('');
                                }}
                                disabled={chairmanDisabled || !enabledProviders.ollama || ollamaAvailableModels.length === 0}
                                title={!enabledProviders.ollama || ollamaAvailableModels.length === 0 ? 'Enable and connect Ollama first' : ''}
                            >
                                Local
                            </button>
                        </div>
                    </div>
                    {chairmanDisabled && (
                        <p className="section-description" style={{ marginBottom: '8px', fontStyle: 'italic' }}>
                            Chairman is only used in Full Deliberation mode.
                        </p>
                    )}
                    <div
                        className={`chairman-selection ${validationErrors.chairman ? 'validation-error' : ''}`}
                        ref={chairmanSelectRef}
                    >
                        <SearchableModelSelect
                            models={filterByRemoteLocal(filteredModels, chairmanFilter)}
                            value={chairmanModel}
                            onChange={(value) => setChairmanModel(value)}
                            placeholder="Search models..."
                            isDisabled={chairmanDisabled}
                            isLoading={isLoadingModels}
                            allModels={allModels}
                        />
                        {validationErrors.chairman && (
                            <div className="validation-error-message">
                                ⚠️ Chairman is required when council members are selected
                            </div>
                        )}
                    </div>

                    {/* Chairman Heat Slider */}
                    <div className="subsection" style={{ marginTop: '16px' }}>
                        <div className="heat-slider-header">
                            <h4>Chairman Heat</h4>
                            <span className="heat-value">{chairmanTemperature.toFixed(1)}</span>
                        </div>
                        <div className="heat-slider-container">
                            <span className="heat-icon cold">❄️</span>
                            <input
                                type="range"
                                min="0"
                                max="1"
                                step="0.1"
                                value={chairmanTemperature}
                                onChange={(e) => setChairmanTemperature(parseFloat(e.target.value))}
                                className="heat-slider"
                                disabled={chairmanDisabled || chairmanModel.includes('gpt-5.1') || chairmanModel.includes('o1-') || chairmanModel.includes('o3-')}
                            />
                            <span className="heat-icon hot">🔥</span>
                        </div>
                        {(chairmanModel.includes('gpt-5.1') || chairmanModel.includes('o1-') || chairmanModel.includes('o3-')) && (
                            <div className="heat-warning">
                                ⚠️ This model enforces fixed temperature and will ignore this setting.
                            </div>
                        )}
                    </div>
                </div>

            </section>
        </>
    );
}

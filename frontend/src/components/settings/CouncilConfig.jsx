import React from 'react';

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

const isFixedTemperatureModel = (modelId = '') => {
    let normalized = String(modelId).toLowerCase();
    const prefixMatch = normalized.match(/^([a-z-]+):(.+)$/);
    if (prefixMatch) normalized = prefixMatch[2];

    if (normalized.includes('/')) {
        normalized = normalized.split('/').slice(1).join('/');
    }

    return (
        normalized.startsWith('gpt-5') ||
        /^o(?:1|3|4)(?:[-.]|$)/.test(normalized) ||
        /^claude-(?:opus|sonnet|haiku|fable)-[4-9](?:[-.]|$)/.test(normalized)
    );
};

export default function CouncilConfig({
    settings,
    ollamaStatus,
    enabledProviders,
    setEnabledProviders,
    directProviderToggles,
    setDirectProviderToggles,
    councilModels,
    chairmanModel,
    councilTemperature,
    setCouncilTemperature,
    chairmanTemperature,
    setChairmanTemperature,
    stage2Temperature,
    setStage2Temperature,
    customEndpointName,
    customEndpointUrl,
    directAvailableModels = [],
}) {
    const hasNotion2ApiModels = directAvailableModels.some(m =>
        m?.source === 'notion2api'
        || m?.provider === 'Notion2API'
        || String(m?.id || '').startsWith('notion2api:')
    );

    const isSourceConfigured = (source) => {
        switch (source) {
            case 'openrouter': return !!settings?.openrouter_api_key_set;
            case 'ollama': return ollamaStatus?.connected;
            case 'groq': return !!settings?.groq_api_key_set;
            case 'custom': return !!(settings?.custom_endpoint_url);
            case 'notion2api': return hasNotion2ApiModels;
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

    return (
        <>
            <section className="settings-section">
                <h3>Available Model Sources</h3>
                <p className="section-description">
                    Toggle which providers are available across all model pickers — Council members, Chairman, and Advisor debates.
                    Disabling a provider here hides its models everywhere.
                    <br /><em style={{ opacity: 0.7, fontSize: '12px' }}>Note: Most non-chat models (embeddings, image generation, speech, OCR, etc.) are automatically filtered out, though some may still appear.</em>
                </p>

                <div className="hybrid-settings-card">
                    {/* Local */}
                    <div className="filter-group">
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
                    </div>

                    <div className="filter-divider"></div>

                    {/* Remote APIs — master toggle */}
                    <div className="filter-group" style={{ marginBottom: '12px' }}>
                        <label className="toggle-wrapper">
                            <div className="toggle-switch">
                                <input
                                    type="checkbox"
                                    checked={enabledProviders.direct}
                                    onChange={(e) => {
                                        const isEnabled = e.target.checked;
                                        setEnabledProviders(prev => ({
                                            ...prev,
                                            direct: isEnabled,
                                            openrouter: isEnabled ? prev.openrouter : false,
                                            groq: isEnabled ? prev.groq : false,
                                            custom: isEnabled ? prev.custom : false,
                                            notion2api: isEnabled ? prev.notion2api : false,
                                        }));
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
                            <span className="toggle-text">Remote APIs</span>
                        </label>
                    </div>

                    <div style={{ opacity: enabledProviders.direct ? 1 : 0.7 }}>
                        {/* Aggregators & Inference */}
                        <div className="filter-group" style={{ marginBottom: '8px' }}>
                            <label 
                                className={`toggle-wrapper ${!isSourceConfigured('openrouter') ? 'source-disabled' : ''}`}
                                title={!isSourceConfigured('openrouter') ? 'Not configured — add API key in LLM API Keys' : ''}
                            >
                                <div className="toggle-switch direct-toggle">
                                    <input
                                        type="checkbox"
                                        checked={isSourceConfigured('openrouter') && enabledProviders.openrouter}
                                        onChange={(e) => {
                                            const on = e.target.checked;
                                            setEnabledProviders(prev => ({
                                                ...prev,
                                                openrouter: on,
                                                ...(on && !prev.direct ? { direct: true } : {}),
                                            }));
                                        }}
                                        disabled={!isSourceConfigured('openrouter')}
                                    />
                                    <span className="slider"></span>
                                </div>
                                <span className="toggle-text" style={{ fontSize: '13px' }}>
                                    OpenRouter
                                    {!isSourceConfigured('openrouter') && (
                                        <span className="toggle-hint"> · not configured</span>
                                    )}
                                </span>
                            </label>

                            <label 
                                className={`toggle-wrapper ${!isSourceConfigured('groq') ? 'source-disabled' : ''}`}
                                title={!isSourceConfigured('groq') ? 'Not configured — add API key in LLM API Keys' : ''}
                            >
                                <div className="toggle-switch direct-toggle">
                                    <input
                                        type="checkbox"
                                        checked={isSourceConfigured('groq') && enabledProviders.groq}
                                        onChange={(e) => {
                                            const on = e.target.checked;
                                            setEnabledProviders(prev => ({
                                                ...prev,
                                                groq: on,
                                                ...(on && !prev.direct ? { direct: true } : {}),
                                            }));
                                        }}
                                        disabled={!isSourceConfigured('groq')}
                                    />
                                    <span className="slider"></span>
                                </div>
                                <span className="toggle-text" style={{ fontSize: '13px' }}>
                                    Groq
                                    {!isSourceConfigured('groq') && (
                                        <span className="toggle-hint"> · not configured</span>
                                    )}
                                </span>
                            </label>

                            {(settings?.custom_endpoint_url || customEndpointUrl) && (
                                <label className="toggle-wrapper">
                                    <div className="toggle-switch direct-toggle">
                                        <input
                                            type="checkbox"
                                            checked={enabledProviders.custom}
                                            onChange={(e) => {
                                                const on = e.target.checked;
                                                setEnabledProviders(prev => ({
                                                    ...prev,
                                                    custom: on,
                                                    ...(on && !prev.direct ? { direct: true } : {}),
                                                }));
                                            }}
                                        />
                                        <span className="slider"></span>
                                    </div>
                                    <span className="toggle-text" style={{ fontSize: '13px' }}>{settings?.custom_endpoint_name || customEndpointName || 'Custom Endpoint'}</span>
                                </label>
                            )}

                            <label
                                className={`toggle-wrapper ${!isSourceConfigured('notion2api') ? 'source-disabled' : ''}`}
                                title={!isSourceConfigured('notion2api') ? 'No Notion2API models found from the backend /api/models/direct endpoint' : ''}
                            >
                                <div className="toggle-switch direct-toggle">
                                    <input
                                        type="checkbox"
                                        checked={isSourceConfigured('notion2api') && !!enabledProviders.notion2api}
                                        disabled={!isSourceConfigured('notion2api')}
                                        onChange={(e) => {
                                            const on = e.target.checked;
                                            setEnabledProviders(prev => ({
                                                ...prev,
                                                notion2api: on,
                                            }));
                                        }}
                                    />
                                    <span className="slider"></span>
                                </div>
                                <span className="toggle-text" style={{ fontSize: '13px' }}>
                                    Notion2API
                                    {!isSourceConfigured('notion2api') && (
                                        <span className="toggle-hint"> - no models found</span>
                                    )}
                                </span>
                            </label>
                        </div>

                        {/* Direct provider grid */}
                        <div className="direct-grid">
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
                                                    setDirectProviderToggles(prev => ({ ...prev, [dp.id]: isEnabled }));
                                                    if (isEnabled && !enabledProviders.direct) {
                                                        setEnabledProviders(prev => ({ ...prev, direct: true }));
                                                    }
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
                </div>
            </section>

            <section className="settings-section">
                <h3>Temperature Controls</h3>
                <p className="section-description">
                    Temperature controls how creative or focused a model's responses are. Lower values produce more predictable, consistent outputs; higher values encourage more diverse, creative answers.
                </p>

                {/* Council Heat (Stage 1) */}
                <div className="subsection">
                    <div className="heat-slider-header">
                        <h4>Council Heat <span style={{ fontWeight: 400, fontSize: '12px', opacity: 0.5 }}>(Stage 1)</span></h4>
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
                            disabled={(councilModels || []).every(isFixedTemperatureModel)}
                        />
                        <span className="heat-icon hot">🔥</span>
                    </div>
                    {(councilModels || []).some(isFixedTemperatureModel) && (
                        <div className="heat-warning">
                            Some selected models enforce fixed temperature and will ignore this setting.
                        </div>
                    )}
                </div>

                {/* Peer Ranking Heat (Stage 2) */}
                <div className="subsection" style={{ marginTop: '20px' }}>
                    <div className="heat-slider-header">
                        <h4>Peer Ranking Heat <span style={{ fontWeight: 400, fontSize: '12px', opacity: 0.5 }}>(Stage 2)</span></h4>
                        <span className="heat-value">{stage2Temperature.toFixed(1)}</span>
                    </div>
                    <div className="heat-slider-container">
                        <span className="heat-icon cold">❄️</span>
                        <input
                            type="range"
                            min="0"
                            max="1"
                            step="0.1"
                            value={stage2Temperature}
                            onChange={(e) => setStage2Temperature(parseFloat(e.target.value))}
                            className="heat-slider"
                        />
                        <span className="heat-icon hot">🔥</span>
                    </div>
                </div>

                {/* Chairman Heat (Stage 3) */}
                <div className="subsection" style={{ marginTop: '20px' }}>
                    <div className="heat-slider-header">
                        <h4>Chairman Heat <span style={{ fontWeight: 400, fontSize: '12px', opacity: 0.5 }}>(Stage 3)</span></h4>
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
                            disabled={isFixedTemperatureModel(chairmanModel)}
                        />
                        <span className="heat-icon hot">🔥</span>
                    </div>
                    {isFixedTemperatureModel(chairmanModel) && (
                        <div className="heat-warning">
                            This model enforces fixed temperature and will ignore this setting.
                        </div>
                    )}
                </div>
            </section>
        </>
    );
}

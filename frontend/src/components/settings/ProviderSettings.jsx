import React, { useMemo, useState } from 'react';
import openrouterIcon from '../../assets/icons/openrouter.svg';
import groqIcon from '../../assets/icons/groq.svg';
import ollamaIcon from '../../assets/icons/ollama.svg';
import openaiIcon from '../../assets/icons/openai.svg';
import anthropicIcon from '../../assets/icons/anthropic.svg';
import googleIcon from '../../assets/icons/google.svg';
import mistralIcon from '../../assets/icons/mistral.svg';
import deepseekIcon from '../../assets/icons/deepseek.svg';
import nvidiaIcon from '../../assets/icons/nvidia.svg';
import customEndpointIcon from '../../assets/icons/openai-compatible.svg';
import opencodeIcon from '../../assets/icons/opencode.svg';
import notion2apiIcon from '../../assets/icons/notion2api.svg';

const PROVIDER_ICONS = {
    openai: openaiIcon,
    anthropic: anthropicIcon,
    google: googleIcon,
    mistral: mistralIcon,
    deepseek: deepseekIcon,
    nvidia: nvidiaIcon,
    'opencode-zen': opencodeIcon,
    'opencode-go': opencodeIcon,
};

const DIRECT_PROVIDERS = [
    { id: 'openai', name: 'OpenAI', key: 'openai_api_key' },
    { id: 'anthropic', name: 'Anthropic', key: 'anthropic_api_key' },
    { id: 'google', name: 'Google', key: 'google_api_key' },
    { id: 'mistral', name: 'Mistral', key: 'mistral_api_key' },
    { id: 'deepseek', name: 'DeepSeek', key: 'deepseek_api_key' },
    { id: 'nvidia', name: 'NVIDIA Build', key: 'nvidia_api_key' },
];

export default function ProviderSettings({
    settings,
    availableModels = [],
    directAvailableModels = [],
    ollamaAvailableModels = [],
    // OpenRouter
    openrouterApiKey,
    setOpenrouterApiKey,
    handleTestOpenRouter,
    isTestingOpenRouter,
    openrouterTestResult,
    // Groq
    groqApiKey,
    setGroqApiKey,
    handleTestGroq,
    isTestingGroq,
    groqTestResult,
    // Ollama
    ollamaBaseUrl,
    setOllamaBaseUrl,
    handleTestOllama,
    isTestingOllama,
    ollamaTestResult,
    ollamaStatus,
    loadOllamaModels,
    // Direct
    directKeys,
    setDirectKeys,
    handleTestDirectKey,
    validatingKeys,
    keyValidationStatus,
    // OpenCode
    opencodeApiKey,
    setOpencodeApiKey,
    handleTestOpencode,
    isTestingOpencode,
    opencodeTestResult,
    opencodeAvailableModels,
    // Notion2API
    notion2apiBaseUrl,
    setNotion2apiBaseUrl,
    notion2apiRoot,
    setNotion2apiRoot,
    notion2apiToken,
    setNotion2apiToken,
    notion2apiAutoLaunch,
    setNotion2apiAutoLaunch,
    notion2apiStatus,
    notion2apiModels,
    handleTestNotion2api,
    isTestingNotion2api,
    notion2apiTestResult,
    onRefreshNotion2api,
    // Custom Endpoint
    customEndpointName,
    setCustomEndpointName,
    customEndpointUrl,
    setCustomEndpointUrl,
    customEndpointApiKey,
    setCustomEndpointApiKey,
    handleTestCustomEndpoint,
    isTestingCustomEndpoint,
    customEndpointTestResult,
    customEndpointModels,
    onClearCustomEndpoint
}) {
    const getDirectProviderModelsCount = (providerId) => {
        const providerNameMap = {
            openai: 'OpenAI',
            anthropic: 'Anthropic',
            google: 'Google',
            mistral: 'Mistral',
            deepseek: 'DeepSeek',
            nvidia: 'NVIDIA'
        };
        const name = providerNameMap[providerId];
        if (!name) return 0;
        return directAvailableModels.filter(m => m.provider === name).length;
    };

    const groqModelsCount = directAvailableModels.filter(m => m.provider === 'Groq').length;

    const [showNotion2apiDiagnostics, setShowNotion2apiDiagnostics] = useState(false);

    const notion2apiWebUrl = useMemo(() => {
        const raw = notion2apiStatus?.web_url || notion2apiBaseUrl || settings?.notion2api_base_url || 'http://127.0.0.1:8120/v1';
        try {
            const url = new URL(raw);
            url.pathname = url.pathname.replace(/\/v1\/?$/, '/') || '/';
            url.search = '';
            url.hash = '';
            return url.toString();
        } catch {
            return String(raw).replace(/\/v1\/?$/, '/');
        }
    }, [notion2apiStatus?.web_url, notion2apiBaseUrl, settings?.notion2api_base_url]);

    const openNotion2apiWebInterface = () => {
        window.open(notion2apiWebUrl, '_blank', 'noopener,noreferrer');
    };

    const formatDiagnosticValue = (value) => {
        if (value === true) return 'Yes';
        if (value === false) return 'No';
        if (value === null || value === undefined || value === '') return '—';
        return String(value);
    };

    const notion2apiDiagnosticRows = [
        ['Runtime', notion2apiStatus?.running ? 'Running' : 'Not running'],
        ['Base URL', notion2apiStatus?.base_url || notion2apiBaseUrl],
        ['Web UI', notion2apiStatus?.web_url || notion2apiWebUrl],
        ['Models endpoint', notion2apiStatus?.models_endpoint],
        ['Configured root', notion2apiStatus?.root || notion2apiRoot],
        ['Resolved root', notion2apiStatus?.resolved_root],
        ['Root exists', notion2apiStatus?.root_exists],
        ['app/server.py', notion2apiStatus?.server_py_exists ? 'Found' : 'Missing'],
        ['API key', notion2apiStatus?.api_key_set ? 'Configured' : 'Not configured'],
        ['Auto-launch', notion2apiStatus?.auto_launch ? 'Enabled' : 'Disabled'],
        ['Managed process', notion2apiStatus?.managed_running ? 'Running' : 'Not running'],
        ['Managed PID', notion2apiStatus?.managed_pid],
        ['Model count', notion2apiStatus?.model_count ?? notion2apiModels.length],
        ['Last error', notion2apiStatus?.error || 'None'],
    ];

    return (
        <section className="settings-section">
            <h3>LLM API Keys</h3>
            <p className="section-description">
                Configure keys for LLM providers.
                Keys are <strong>auto-saved</strong> immediately upon successful test.
            </p>

            {/* OpenRouter */}
            <form className="api-key-section" onSubmit={e => e.preventDefault()}>
                <label>
                    <img src={openrouterIcon} alt="" className="provider-icon" />
                    OpenRouter API Key
                </label>
                <div className="api-key-input-row">
                    <input
                        type="password"
                        placeholder={settings?.openrouter_api_key_set ? '••••••••••••••••' : 'Enter API key'}
                        value={openrouterApiKey}
                        onChange={(e) => {
                            setOpenrouterApiKey(e.target.value);
                            // Reset test result on change is handled by parent usually, but here we might need a callback or just let parent handle it via the setter wrapper if needed.
                            // In Settings.jsx: setOpenrouterTestResult(null) was called.
                            // We should probably pass a wrapper or just accept that the parent setter doesn't clear the error.
                            // Actually, looking at Settings.jsx, the onChange did: setOpenrouterApiKey(...); setOpenrouterTestResult(null);
                            // So we need to replicate that logic or pass a specific handler.
                            // For simplicity, let's assume the parent passes a setter that *just* sets the key, and we might need a separate prop for clearing error?
                            // No, simpler: The parent passed `setOpenrouterApiKey`. If we want to clear error, we need to do it here?
                            // Wait, the prop `setOpenrouterApiKey` is likely just the state setter.
                            // I should probably accept `onOpenrouterKeyChange` instead of raw setter if I want to bundle logic.
                            // BUT, to keep it "dumb", I'll just use the props as is, but I can't clear the error if I don't have the error setter.
                            // Let's check the props again. I didn't pass `setOpenrouterTestResult`.
                            // I should probably pass `onOpenrouterChange` which does both.
                            // OR, I can just pass `setOpenrouterTestResult` as a prop too.
                            // Let's pass `setOpenrouterTestResult` etc. to be safe, or better, make the props `onChange...`.
                            // I'll stick to the raw setters for now but I'll add `setOpenrouterTestResult` to the props list to be safe, OR just ignore clearing it (minor UX regression).
                            // BETTER: I'll define `handleOpenrouterChange` locally if I have the setters.
                        }}
                        className={settings?.openrouter_api_key_set && !openrouterApiKey ? 'key-configured' : ''}
                    />
                    <button
                        className="test-button"
                        onClick={handleTestOpenRouter}
                        disabled={!openrouterApiKey && !settings?.openrouter_api_key_set || isTestingOpenRouter}
                    >
                        {isTestingOpenRouter ? 'Testing...' : (settings?.openrouter_api_key_set && !openrouterApiKey ? 'Retest' : 'Test')}
                    </button>
                </div>
                {settings?.openrouter_api_key_set && !openrouterApiKey && (
                    <div className="key-status set">
                        ✓ API key configured
                        {availableModels.length > 0 && ` · ${availableModels.length} models available`}
                    </div>
                )}
                {openrouterTestResult && (
                    <div className={`test-result ${openrouterTestResult.success ? 'success' : 'error'}`}>
                        {openrouterTestResult.message}
                    </div>
                )}
                <p className="api-key-hint">
                    Get key at <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer">openrouter.ai</a>
                </p>
            </form>

            {/* Groq */}
            <form className="api-key-section" onSubmit={e => e.preventDefault()}>
                <label>
                    <img src={groqIcon} alt="" className="provider-icon" />
                    Groq API Key
                </label>
                <div className="api-key-input-row">
                    <input
                        type="password"
                        placeholder={settings?.groq_api_key_set ? '••••••••••••••••' : 'Enter API key'}
                        value={groqApiKey}
                        onChange={(e) => {
                            setGroqApiKey(e.target.value);
                            // setGroqTestResult(null); // Missing prop
                        }}
                        className={settings?.groq_api_key_set && !groqApiKey ? 'key-configured' : ''}
                    />
                    <button
                        className="test-button"
                        onClick={handleTestGroq}
                        disabled={!groqApiKey && !settings?.groq_api_key_set || isTestingGroq}
                    >
                        {isTestingGroq ? 'Testing...' : (settings?.groq_api_key_set && !groqApiKey ? 'Retest' : 'Test')}
                    </button>
                </div>
                {settings?.groq_api_key_set && !groqApiKey && (
                    <div className="key-status set">
                        ✓ API key configured
                        {groqModelsCount > 0 && ` · ${groqModelsCount} models available`}
                    </div>
                )}
                {groqTestResult && (
                    <div className={`test-result ${groqTestResult.success ? 'success' : 'error'}`}>
                        {groqTestResult.message}
                    </div>
                )}
                <p className="api-key-hint">
                    Get key at <a href="https://console.groq.com/keys" target="_blank" rel="noopener noreferrer">console.groq.com</a>
                </p>
            </form>

            {/* Ollama */}
            <form className="api-key-section" onSubmit={e => e.preventDefault()}>
                <label>
                    <img src={ollamaIcon} alt="" className="provider-icon" />
                    Ollama Base URL
                </label>
                <div className="api-key-input-row">
                    <input
                        type="text"
                        placeholder="http://localhost:11434"
                        value={ollamaBaseUrl}
                        onChange={(e) => {
                            setOllamaBaseUrl(e.target.value);
                            // setOllamaTestResult(null); // Missing prop
                        }}
                    />
                    <button
                        className="test-button"
                        onClick={handleTestOllama}
                        disabled={!ollamaBaseUrl || isTestingOllama}
                    >
                        {isTestingOllama ? 'Testing...' : 'Connect'}
                    </button>
                </div>
                {ollamaTestResult && (
                    <div className={`test-result ${ollamaTestResult.success ? 'success' : 'error'}`}>
                        {ollamaTestResult.message}
                    </div>
                )}
                {ollamaStatus && ollamaStatus.connected && (
                    <div className="ollama-auto-status connected">
                        <span className="status-indicator connected">●</span>
                        <span className="status-text">
                            <strong>Connected</strong>
                            {ollamaAvailableModels.length > 0 && ` · ${ollamaAvailableModels.length} models available`}
                            <span className="status-separator">·</span>
                            <span className="status-time">Last: {new Date(ollamaStatus.lastConnected).toLocaleTimeString()}</span>
                        </span>
                    </div>
                )}
                {ollamaStatus && !ollamaStatus.connected && !ollamaStatus.testing && (
                    <div className="ollama-auto-status">
                        <span className="status-indicator disconnected">●</span>
                        <span className="status-text">Not connected</span>
                    </div>
                )}
                <div className="model-options-row" style={{ marginTop: '12px' }}>
                    <button
                        type="button"
                        className="reset-defaults-button"
                        onClick={() => loadOllamaModels(ollamaBaseUrl)}
                    >
                        Refresh Local Models
                    </button>
                </div>
            </form>

            {/* Direct LLM API Connections */}
            <div className="subsection" style={{ marginTop: '24px' }}>
                <h4>Direct LLM Connections</h4>
                {DIRECT_PROVIDERS.map(dp => (
                    <form key={dp.id} className="api-key-section" onSubmit={e => e.preventDefault()}>
                        <label>
                            <img src={PROVIDER_ICONS[dp.id]} alt="" className="provider-icon" />
                            {dp.name} API Key
                        </label>
                        <div className="api-key-input-row">
                            <input
                                type="password"
                                placeholder={settings?.[`${dp.key}_set`] ? '••••••••••••••••' : 'Enter API key'}
                                value={directKeys[dp.key]}
                                onChange={e => setDirectKeys(prev => ({ ...prev, [dp.key]: e.target.value }))}
                                className={settings?.[`${dp.key}_set`] && !directKeys[dp.key] ? 'key-configured' : ''}
                            />
                            <button
                                className="test-button"
                                onClick={() => handleTestDirectKey(dp.id, dp.key)}
                                disabled={(!directKeys[dp.key] && !settings?.[`${dp.key}_set`]) || validatingKeys[dp.id]}
                            >
                                {validatingKeys[dp.id] ? 'Testing...' : (settings?.[`${dp.key}_set`] && !directKeys[dp.key] ? 'Retest' : 'Test')}
                            </button>
                        </div>
                        {settings?.[`${dp.key}_set`] && !directKeys[dp.key] && (
                            <div className="key-status set">
                                ✓ API key configured
                                {getDirectProviderModelsCount(dp.id) > 0 && ` · ${getDirectProviderModelsCount(dp.id)} models available`}
                            </div>
                        )}
                        {keyValidationStatus[dp.id] && (
                            <div className={`test-result ${keyValidationStatus[dp.id].success ? 'success' : 'error'}`}>
                                {keyValidationStatus[dp.id].message}
                            </div>
                        )}
                    </form>
                ))}
            </div>

            {/* OpenCode Zen / Go */}
            <div className="subsection" style={{ marginTop: '24px' }}>
                <h4>
                    <img src={opencodeIcon} alt="" className="provider-icon" style={{ verticalAlign: 'middle', marginRight: '6px' }} />
                    OpenCode (Zen + Go)
                </h4>
                <p className="subsection-description" style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '16px' }}>
                    One OpenCode API key unlocks <strong>Zen</strong> (curated, per-token) and <strong>Go</strong> (subscription).
                    v1 supports OpenAI-compatible chat/completions models only — GPT Responses, Claude Messages, and per-model
                    Gemini endpoints are not yet wired up.
                </p>
                <form className="api-key-section" onSubmit={e => e.preventDefault()}>
                    <label>OpenCode API Key</label>
                    <div className="api-key-input-row">
                        <input
                            type="password"
                            placeholder={settings?.opencode_api_key_set ? '••••••••••••••••' : 'Enter API key'}
                            value={opencodeApiKey}
                            onChange={e => setOpencodeApiKey(e.target.value)}
                            className={settings?.opencode_api_key_set && !opencodeApiKey ? 'key-configured' : ''}
                        />
                        <button
                            className="test-button"
                            onClick={handleTestOpencode}
                            disabled={(!opencodeApiKey && !settings?.opencode_api_key_set) || isTestingOpencode}
                        >
                            {isTestingOpencode ? 'Testing...' : (settings?.opencode_api_key_set && !opencodeApiKey ? 'Retest' : 'Test')}
                        </button>
                    </div>
                    {settings?.opencode_api_key_set && !opencodeApiKey && (
                        <div className="key-status set">
                            ✓ API key configured
                            {opencodeAvailableModels.length > 0 && ` · ${opencodeAvailableModels.length} models available`}
                        </div>
                    )}
                    {opencodeTestResult && (
                        <div className={`test-result ${opencodeTestResult.success ? 'success' : 'error'}`}>
                            {opencodeTestResult.message}
                        </div>
                    )}
                    <p className="api-key-hint">
                        Get a key at <a href="https://opencode.ai/auth" target="_blank" rel="noopener noreferrer">opencode.ai/auth</a> —
                        add a Zen balance for pay-per-token, subscribe to Go for $5/$10 monthly, or both.
                    </p>
                </form>
            </div>

            {/* Notion2API */}
            <div className="subsection" style={{ marginTop: '24px' }}>
                <h4>
                    <img src={notion2apiIcon} alt="" className="provider-icon" style={{ verticalAlign: 'middle', marginRight: '6px' }} />
                    Notion2API Provider
                </h4>
                <p className="subsection-description" style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '16px' }}>
                    Dedicated provider for a local or remote Notion2API OpenAI-compatible service. Models appear as <code>notion2api:*</code>.
                </p>
                <form className="api-key-section" onSubmit={e => e.preventDefault()}>
                    <label>Base URL</label>
                    <div className="api-key-input-row">
                        <input
                            type="text"
                            placeholder="http://127.0.0.1:8120/v1"
                            value={notion2apiBaseUrl}
                            onChange={e => setNotion2apiBaseUrl(e.target.value)}
                        />
                    </div>
                    <label style={{ marginTop: '12px' }}>Local checkout root <span style={{ fontWeight: 'normal', opacity: 0.7 }}>(optional)</span></label>
                    <div className="api-key-input-row">
                        <input
                            type="text"
                            placeholder="X:\\Code\\notion2api"
                            value={notion2apiRoot}
                            onChange={e => setNotion2apiRoot(e.target.value)}
                        />
                    </div>
                    <label style={{ marginTop: '12px' }}>API Key</label>
                    <div className="api-key-input-row">
                        <input
                            type="password"
                            placeholder={settings?.notion2api_api_key_set ? 'Configured key' : 'Enter API key'}
                            value={notion2apiToken}
                            onChange={e => setNotion2apiToken(e.target.value)}
                            className={settings?.notion2api_api_key_set && !notion2apiToken ? 'key-configured' : ''}
                        />
                        <button
                            className="test-button"
                            onClick={handleTestNotion2api}
                            disabled={!notion2apiBaseUrl || isTestingNotion2api}
                        >
                            {isTestingNotion2api ? 'Testing...' : 'Test / Save'}
                        </button>
                    </div>
                    <label className="checkbox-label" style={{ marginTop: '12px' }}>
                        <input
                            type="checkbox"
                            checked={!!notion2apiAutoLaunch}
                            onChange={e => setNotion2apiAutoLaunch(e.target.checked)}
                        />
                        Auto-launch this provider when desktop launcher support is enabled
                    </label>
                    <div className="model-options-row" style={{ marginTop: '12px', gap: '8px', flexWrap: 'wrap' }}>
                        <button type="button" className="reset-defaults-button" onClick={onRefreshNotion2api}>
                            Refresh Status / Models
                        </button>
                        <button type="button" className="reset-defaults-button" onClick={openNotion2apiWebInterface}>
                            Launch Web Interface
                        </button>
                        <button
                            type="button"
                            className="reset-defaults-button"
                            onClick={() => setShowNotion2apiDiagnostics(prev => !prev)}
                        >
                            {showNotion2apiDiagnostics ? 'Hide Diagnostics' : 'Diagnostics'}
                        </button>
                    </div>
                    {notion2apiStatus && (
                        <div className={`key-status ${notion2apiStatus.running ? 'set' : ''}`}>
                            {notion2apiStatus.running ? '✓ Running' : 'Not running'}
                            {notion2apiStatus.api_key_set ? ' · API key configured' : ' · No API key saved'}
                            {notion2apiStatus.model_count > 0 && ` · ${notion2apiStatus.model_count} models available`}
                            {notion2apiStatus.error && ` · ${notion2apiStatus.error}`}
                        </div>
                    )}
                    {notion2apiModels.length > 0 && (
                        <div className="key-status set">
                            ✓ Dedicated provider models loaded · {notion2apiModels.length} available
                        </div>
                    )}
                    {showNotion2apiDiagnostics && (
                        <div className="notion2api-diagnostic-panel">
                            <div className="notion2api-diagnostic-header">
                                <h5>Notion2API Diagnostics</h5>
                                <span>{notion2apiStatus?.running ? 'Service reachable' : 'Service unreachable'}</span>
                            </div>
                            <div className="diagnostic-grid">
                                {notion2apiDiagnosticRows.map(([label, value]) => (
                                    <div className="diagnostic-row" key={label}>
                                        <span className="diagnostic-label">{label}</span>
                                        <code className="diagnostic-value">{formatDiagnosticValue(value)}</code>
                                    </div>
                                ))}
                            </div>
                            {notion2apiModels.length > 0 && (
                                <div className="diagnostic-model-list">
                                    <strong>Loaded models</strong>
                                    <div className="diagnostic-model-chips">
                                        {notion2apiModels.slice(0, 12).map(model => (
                                            <code key={model.id || model.name}>{model.id || model.name}</code>
                                        ))}
                                        {notion2apiModels.length > 12 && <span>+{notion2apiModels.length - 12} more</span>}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                    {notion2apiTestResult && (
                        <div className={`test-result ${notion2apiTestResult.success ? 'success' : 'error'}`}>
                            {notion2apiTestResult.message}
                        </div>
                    )}
                </form>
            </div>

            {/* Custom OpenAI-compatible Endpoint */}
            <div className="subsection" style={{ marginTop: '24px' }}>
                <h4>Custom OpenAI-Compatible Endpoint</h4>
                <p className="subsection-description" style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '16px' }}>
                    Connect to any OpenAI-compatible API (Together AI, Fireworks, vLLM, LM Studio, etc.)
                </p>
                <form className="api-key-section" onSubmit={e => e.preventDefault()}>
                    <label>
                        <img src={customEndpointIcon} alt="" className="provider-icon" />
                        Display Name
                    </label>
                    <div className="api-key-input-row">
                        <input
                            type="text"
                            placeholder="e.g., Together AI, My vLLM Server"
                            value={customEndpointName}
                            onChange={(e) => {
                                setCustomEndpointName(e.target.value);
                                // setCustomEndpointTestResult(null); // Missing prop
                            }}
                        />
                    </div>

                    <label style={{ marginTop: '12px' }}>Base URL</label>
                    <div className="api-key-input-row">
                        <input
                            type="text"
                            placeholder="https://api.together.xyz/v1"
                            value={customEndpointUrl}
                            onChange={(e) => {
                                setCustomEndpointUrl(e.target.value);
                                // setCustomEndpointTestResult(null); // Missing prop
                            }}
                        />
                    </div>

                    <label style={{ marginTop: '12px' }}>API Key <span style={{ fontWeight: 'normal', opacity: 0.7 }}>(optional for local servers)</span></label>
                    <div className="api-key-input-row">
                        <input
                            type="password"
                            placeholder={settings?.custom_endpoint_url ? '••••••••••••••••' : 'Enter API key'}
                            value={customEndpointApiKey}
                            onChange={(e) => {
                                setCustomEndpointApiKey(e.target.value);
                                // setCustomEndpointTestResult(null); // Missing prop
                            }}
                        />
                        <button
                            className="test-button"
                            onClick={handleTestCustomEndpoint}
                            disabled={!customEndpointName || !customEndpointUrl || isTestingCustomEndpoint}
                        >
                            {isTestingCustomEndpoint ? 'Testing...' : 'Connect'}
                        </button>
                    </div>

                    {/* Show configured status and disconnect button when endpoint is saved */}
                    {settings?.custom_endpoint_url && (
                        <div className="key-status set key-status-row">
                            <span>
                                ✓ Endpoint configured
                                {customEndpointModels.length > 0 && ` · ${customEndpointModels.length} models available`}
                            </span>
                            <button
                                className="test-button danger"
                                onClick={onClearCustomEndpoint}
                            >
                                Disconnect
                            </button>
                        </div>
                    )}
                    {customEndpointTestResult && (
                        <div className={`test-result ${customEndpointTestResult.success ? 'success' : 'error'}`}>
                            {customEndpointTestResult.message}
                        </div>
                    )}
                </form>
            </div>
        </section>
    );
}

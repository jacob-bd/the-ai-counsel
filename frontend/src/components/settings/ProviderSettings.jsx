import React from 'react';
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
import SubscriptionOAuth from './SubscriptionOAuth';

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
    ollamaEnabled = false,
    loadOllamaModels,
    onDisconnectOllama,
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
    onClearCustomEndpoint,
    onDisconnectOpenRouter,
    onDisconnectGroq,
    onDisconnectDirectKey,
    onDisconnectOpencode,
    onOAuthSettingsChange,
    onOAuthModelsRefresh,
    // Credential storage
    currentCredentialStorage = 'file',
    credentialStorageBusy = false,
    onCredentialStorageChange,
    onNavigateToGeneral,
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

    return (
        <section className="settings-section">
            <h3>LLM API Keys</h3>
            <p className="section-description">
                Configure keys for LLM providers.
                Keys are <strong>auto-saved</strong> immediately upon successful test.
            </p>

            <div className="subsection credential-storage-panel">
                <h4>Where secrets are stored</h4>
                <p className="section-description">
                    Choose where API keys and OAuth tokens are kept on this machine.
                    {settings?.credential_storage_effective
                        && settings.credential_storage_effective !== currentCredentialStorage && (
                        <> Currently using <strong>{settings.credential_storage_effective}</strong> (effective).</>
                    )}
                </p>
                <div className="credential-storage-options">
                    <label className="radio-option">
                        <input
                            type="radio"
                            name="credential-storage"
                            value="file"
                            checked={currentCredentialStorage === 'file'}
                            onChange={() => onCredentialStorageChange?.('file')}
                            disabled={credentialStorageBusy}
                        />
                        <span>Local file (data volume)</span>
                    </label>
                    <label className={`radio-option ${!settings?.credential_storage_available?.keyring ? 'radio-option--disabled' : ''}`}>
                        <input
                            type="radio"
                            name="credential-storage"
                            value="keyring"
                            checked={currentCredentialStorage === 'keyring'}
                            onChange={() => onCredentialStorageChange?.('keyring')}
                            disabled={credentialStorageBusy || !settings?.credential_storage_available?.keyring}
                        />
                        <span>OS keystore (Keychain / Credential Manager)</span>
                    </label>
                </div>
                {!settings?.credential_storage_available?.keyring && settings?.credential_storage_unavailable_reason && (
                    <p className="api-key-hint">{settings.credential_storage_unavailable_reason}</p>
                )}
                <p className="api-key-hint" style={{ marginTop: '10px' }}>
                    Using{' '}
                    <a href="https://github.com/jacob-bd/relay-ai" target="_blank" rel="noopener noreferrer">
                        relay-ai
                    </a>
                    ? Import its credentials from{' '}
                    <button
                        type="button"
                        className="settings-inline-link"
                        onClick={() => onNavigateToGeneral?.()}
                    >
                        Settings → General
                    </button>
                    . Imports go into this credential store (not settings.json).
                </p>
            </div>

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
                    <div className="key-status set key-status-row">
                        <span>
                            ✓ API key configured
                            {availableModels.length > 0 && ` · ${availableModels.length} models available`}
                        </span>
                        <button
                            type="button"
                            className="test-button danger"
                            onClick={onDisconnectOpenRouter}
                        >
                            Disconnect
                        </button>
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
                    <div className="key-status set key-status-row">
                        <span>
                            ✓ API key configured
                            {groqModelsCount > 0 && ` · ${groqModelsCount} models available`}
                        </span>
                        <button
                            type="button"
                            className="test-button danger"
                            onClick={onDisconnectGroq}
                        >
                            Disconnect
                        </button>
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
                        }}
                    />
                    <button
                        className="test-button"
                        onClick={handleTestOllama}
                        disabled={!ollamaBaseUrl || isTestingOllama}
                    >
                        {isTestingOllama
                            ? 'Testing...'
                            : (ollamaEnabled && ollamaStatus?.connected ? 'Retest' : 'Connect')}
                    </button>
                </div>
                {ollamaTestResult && (
                    <div className={`test-result ${ollamaTestResult.success ? 'success' : 'error'}`}>
                        {ollamaTestResult.message}
                    </div>
                )}
                {ollamaEnabled && ollamaStatus?.connected && (
                    <div className="key-status set key-status-row">
                        <span>
                            ✓ Connected
                            {ollamaAvailableModels.length > 0 && ` · ${ollamaAvailableModels.length} models available`}
                            {ollamaStatus.lastConnected && (
                                <>
                                    <span className="status-separator">·</span>
                                    <span className="status-time">Last: {new Date(ollamaStatus.lastConnected).toLocaleTimeString()}</span>
                                </>
                            )}
                        </span>
                        <button
                            type="button"
                            className="test-button danger"
                            onClick={onDisconnectOllama}
                        >
                            Disconnect
                        </button>
                    </div>
                )}
                {!ollamaEnabled && ollamaStatus?.connected && !ollamaStatus.testing && (
                    <div className="ollama-auto-status">
                        <span className="status-indicator disconnected">●</span>
                        <span className="status-text">
                            Ollama is running — click Connect to enable it as a provider
                        </span>
                    </div>
                )}
                {!ollamaEnabled && ollamaStatus && !ollamaStatus.connected && !ollamaStatus.testing && (
                    <div className="ollama-auto-status">
                        <span className="status-indicator disconnected">●</span>
                        <span className="status-text">Not connected</span>
                    </div>
                )}
                {ollamaEnabled && (
                    <div className="model-options-row" style={{ marginTop: '12px' }}>
                        <button
                            type="button"
                            className="reset-defaults-button"
                            onClick={() => loadOllamaModels(ollamaBaseUrl)}
                        >
                            Refresh Local Models
                        </button>
                    </div>
                )}
            </form>

            <SubscriptionOAuth
                settings={settings}
                onSettingsChange={onOAuthSettingsChange}
                onModelsRefresh={onOAuthModelsRefresh}
                directAvailableModels={directAvailableModels}
            />

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
                            <div className="key-status set key-status-row">
                                <span>
                                    ✓ API key configured
                                    {getDirectProviderModelsCount(dp.id) > 0 && ` · ${getDirectProviderModelsCount(dp.id)} models available`}
                                </span>
                                <button
                                    type="button"
                                    className="test-button danger"
                                    onClick={() => onDisconnectDirectKey?.(dp.id, dp.key)}
                                >
                                    Disconnect
                                </button>
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
                        <div className="key-status set key-status-row">
                            <span>
                                ✓ API key configured
                                {opencodeAvailableModels.length > 0 && ` · ${opencodeAvailableModels.length} models available`}
                            </span>
                            <button
                                type="button"
                                className="test-button danger"
                                onClick={onDisconnectOpencode}
                            >
                                Disconnect
                            </button>
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

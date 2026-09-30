import React from 'react';
import { useI18n } from '../../i18n';

export const SEARCH_PROVIDERS = [
    {
        id: 'duckduckgo',
        name: 'DuckDuckGo',
        description: 'Hybrid web + news search with smart optimization. Fast and free.',
        requiresKey: false,
        keyType: null,
    },
    {
        id: 'serper',
        name: 'Serper (Google)',
        description: 'Real Google search results. 2,500 free queries. Fast and accurate.',
        requiresKey: true,
        keyType: 'serper',
    },
    {
        id: 'tavily',
        name: 'Tavily',
        description: 'Purpose-built for LLMs. Returns rich, relevant content. Requires API key.',
        requiresKey: true,
        keyType: 'tavily',
    },
    {
        id: 'brave',
        name: 'Brave Search',
        description: 'Privacy-focused search. 2,000 free queries/month. Requires API key.',
        requiresKey: true,
        keyType: 'brave',
    },
    {
        id: 'tinyfish',
        name: 'TinyFish',
        description: 'AI-powered search with free tier (5 req/min). Free API key, no credit card. Includes batch content fetching.',
        requiresKey: true,
        keyType: 'tinyfish',
    },
];

export default function SearchSettings({
    settings,
    selectedSearchProvider,
    setSelectedSearchProvider,
    // Serper (Google)
    serperApiKey,
    setSerperApiKey,
    handleTestSerper,
    isTestingSerper,
    serperTestResult,
    setSerperTestResult,
    // Tavily
    tavilyApiKey,
    setTavilyApiKey,
    handleTestTavily,
    isTestingTavily,
    tavilyTestResult,
    setTavilyTestResult,
    // Brave
    braveApiKey,
    setBraveApiKey,
    handleTestBrave,
    isTestingBrave,
    braveTestResult,
    setBraveTestResult,
    // TinyFish
    tinyfishApiKey,
    setTinyfishApiKey,
    handleTestTinyfish,
    isTestingTinyfish,
    tinyfishTestResult,
    setTinyfishTestResult,
    // Other Settings
    fullContentResults,
    setFullContentResults,
    searchKeywordExtraction,
    setSearchKeywordExtraction,
    // New DuckDuckGo optimization settings
    searchResultCount,
    setSearchResultCount,
    searchHybridMode,
    setSearchHybridMode,
    onDisconnectSearchKey,
}) {
    const { t } = useI18n();

    return (
        <section className="settings-section">
            <h3>{t('Web Search Provider')}</h3>
            <div className="provider-options">
                {SEARCH_PROVIDERS.map(provider => (
                    <div key={provider.id} className={`provider-option-container ${selectedSearchProvider === provider.id ? 'selected' : ''}`}>
                        <label className="provider-option">
                            <input
                                type="radio"
                                name="search_provider"
                                value={provider.id}
                                checked={selectedSearchProvider === provider.id}
                                onChange={() => setSelectedSearchProvider(provider.id)}
                            />
                            <div className="provider-info">
                                <span className="provider-name">{provider.name}</span>
                                <span className="provider-description">{t(provider.description)}</span>
                            </div>
                        </label>

                        {/* Inline API Key Input for Serper (Google) */}
                        {selectedSearchProvider === 'serper' && provider.id === 'serper' && (
                            <div className="inline-api-key-section">
                                <div className="api-key-input-row">
                                    <input
                                        type="password"
                                        placeholder={settings?.serper_api_key_set ? '••••••••••••••••' : t('Enter Serper API key')}
                                        value={serperApiKey}
                                        onChange={e => {
                                            setSerperApiKey(e.target.value);
                                            if (setSerperTestResult) setSerperTestResult(null);
                                        }}
                                        className={settings?.serper_api_key_set && !serperApiKey ? 'key-configured' : ''}
                                    />
                                    <button
                                        type="button"
                                        className="test-button"
                                        onClick={handleTestSerper}
                                        disabled={isTestingSerper || (!serperApiKey && !settings?.serper_api_key_set)}
                                    >
                                        {isTestingSerper ? t('Testing...') : (settings?.serper_api_key_set && !serperApiKey ? t('Retest') : t('Test'))}
                                    </button>
                                </div>
                                {settings?.serper_api_key_set && !serperApiKey && (
                                    <div className="key-status set key-status-row">
                                        <span>✓ {t('API key configured')}</span>
                                        <button
                                            type="button"
                                            className="test-button danger"
                                            onClick={() => onDisconnectSearchKey?.('serper')}
                                        >
                                            {t('Disconnect')}
                                        </button>
                                    </div>
                                )}
                                {serperTestResult && (
                                    <div className={`test-result ${serperTestResult.success ? 'success' : 'error'}`}>
                                        {serperTestResult.success ? '✓' : '✗'} {t(serperTestResult.message)}
                                    </div>
                                )}
                                <a 
                                    href="https://serper.dev" 
                                    target="_blank" 
                                    rel="noopener noreferrer"
                                    className="api-key-link"
                                    style={{ marginTop: '8px', display: 'inline-block', fontSize: 'calc(12px * var(--font-scale))', color: '#60a5fa' }}
                                >
                                    {t('Get API key at')} serper.dev →
                                </a>
                            </div>
                        )}

                        {/* Inline API Key Input for Tavily */}
                        {selectedSearchProvider === 'tavily' && provider.id === 'tavily' && (
                            <div className="inline-api-key-section">
                                <div className="api-key-input-row">
                                    <input
                                        type="password"
                                        placeholder={settings?.tavily_api_key_set ? '••••••••••••••••' : t('Enter Tavily API key')}
                                        value={tavilyApiKey}
                                        onChange={e => {
                                            setTavilyApiKey(e.target.value);
                                            if (setTavilyTestResult) setTavilyTestResult(null);
                                        }}
                                        className={settings?.tavily_api_key_set && !tavilyApiKey ? 'key-configured' : ''}
                                    />
                                    <button
                                        type="button"
                                        className="test-button"
                                        onClick={handleTestTavily}
                                        disabled={isTestingTavily || (!tavilyApiKey && !settings?.tavily_api_key_set)}
                                    >
                                        {isTestingTavily ? t('Testing...') : (settings?.tavily_api_key_set && !tavilyApiKey ? t('Retest') : t('Test'))}
                                    </button>
                                </div>
                                {settings?.tavily_api_key_set && !tavilyApiKey && (
                                    <div className="key-status set key-status-row">
                                        <span>✓ {t('API key configured')}</span>
                                        <button
                                            type="button"
                                            className="test-button danger"
                                            onClick={() => onDisconnectSearchKey?.('tavily')}
                                        >
                                            {t('Disconnect')}
                                        </button>
                                    </div>
                                )}
                                {tavilyTestResult && (
                                    <div className={`test-result ${tavilyTestResult.success ? 'success' : 'error'}`}>
                                        {tavilyTestResult.success ? '✓' : '✗'} {t(tavilyTestResult.message)}
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Inline API Key Input for Brave */}
                        {selectedSearchProvider === 'brave' && provider.id === 'brave' && (
                            <div className="inline-api-key-section">
                                <div className="api-key-input-row">
                                    <input
                                        type="password"
                                        placeholder={settings?.brave_api_key_set ? '••••••••••••••••' : t('Enter Brave API key')}
                                        value={braveApiKey}
                                        onChange={e => {
                                            setBraveApiKey(e.target.value);
                                            if (setBraveTestResult) setBraveTestResult(null);
                                        }}
                                        className={settings?.brave_api_key_set && !braveApiKey ? 'key-configured' : ''}
                                    />
                                    <button
                                        type="button"
                                        className="test-button"
                                        onClick={handleTestBrave}
                                        disabled={isTestingBrave || (!braveApiKey && !settings?.brave_api_key_set)}
                                    >
                                        {isTestingBrave ? t('Testing...') : (settings?.brave_api_key_set && !braveApiKey ? t('Retest') : t('Test'))}
                                    </button>
                                </div>
                                {settings?.brave_api_key_set && !braveApiKey && (
                                    <div className="key-status set key-status-row">
                                        <span>✓ {t('API key configured')}</span>
                                        <button
                                            type="button"
                                            className="test-button danger"
                                            onClick={() => onDisconnectSearchKey?.('brave')}
                                        >
                                            {t('Disconnect')}
                                        </button>
                                    </div>
                                )}
                                {braveTestResult && (
                                    <div className={`test-result ${braveTestResult.success ? 'success' : 'error'}`}>
                                        {braveTestResult.success ? '✓' : '✗'} {t(braveTestResult.message)}
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Inline API Key Input for TinyFish */}
                        {selectedSearchProvider === 'tinyfish' && provider.id === 'tinyfish' && (
                            <div className="inline-api-key-section">
                                <div className="api-key-input-row">
                                    <input
                                        type="password"
                                        placeholder={settings?.tinyfish_api_key_set ? '••••••••••••••••' : t('Enter TinyFish API key')}
                                        value={tinyfishApiKey}
                                        onChange={e => {
                                            setTinyfishApiKey(e.target.value);
                                            if (setTinyfishTestResult) setTinyfishTestResult(null);
                                        }}
                                        className={settings?.tinyfish_api_key_set && !tinyfishApiKey ? 'key-configured' : ''}
                                    />
                                    <button
                                        type="button"
                                        className="test-button"
                                        onClick={handleTestTinyfish}
                                        disabled={isTestingTinyfish || (!tinyfishApiKey && !settings?.tinyfish_api_key_set)}
                                    >
                                        {isTestingTinyfish ? t('Testing...') : (settings?.tinyfish_api_key_set && !tinyfishApiKey ? t('Retest') : t('Test'))}
                                    </button>
                                </div>
                                {settings?.tinyfish_api_key_set && !tinyfishApiKey && (
                                    <div className="key-status set key-status-row">
                                        <span>✓ {t('API key configured')}</span>
                                        <button
                                            type="button"
                                            className="test-button danger"
                                            onClick={() => onDisconnectSearchKey?.('tinyfish')}
                                        >
                                            {t('Disconnect')}
                                        </button>
                                    </div>
                                )}
                                {tinyfishTestResult && (
                                    <div className={`test-result ${tinyfishTestResult.success ? 'success' : 'error'}`}>
                                        {tinyfishTestResult.success ? '✓' : '✗'} {t(tinyfishTestResult.message)}
                                    </div>
                                )}
                                <div className="rate-limit-notice" style={{ marginTop: '8px', fontSize: 'calc(12px * var(--font-scale))', color: '#94a3b8' }}>
                                    ⚠ {t('Free tier: 5 searches/min. Upgrade at')} <a href="https://agent.tinyfish.ai" target="_blank" rel="noopener noreferrer" style={{ color: '#60a5fa' }}>agent.tinyfish.ai</a> {t('for higher limits.')}
                                </div>
                                <a
                                    href="https://agent.tinyfish.ai/api-keys"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="api-key-link"
                                    style={{ marginTop: '8px', display: 'inline-block', fontSize: 'calc(12px * var(--font-scale))', color: '#60a5fa' }}
                                >
                                    {t('Get free API key at')} agent.tinyfish.ai →
                                </a>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            <div className="full-content-section">
                <label>{t('Full Article Fetch (Jina AI)')}</label>
                <p className="setting-description">
                    {t('Uses Jina AI to read the full text of the top search results.')}
                    <strong> {t('Set to 0 to disable.')}</strong>
                </p>
                <div className="full-content-input-row">
                    <input
                        type="range"
                        min="0"
                        max="5"
                        value={fullContentResults}
                        onChange={e => setFullContentResults(parseInt(e.target.value, 10))}
                        className="full-content-slider"
                    />
                    <span className="full-content-value">{t('{count} results', { count: fullContentResults })}</span>
                </div>
            </div>

            {/* DuckDuckGo-specific optimization settings */}
            {selectedSearchProvider === 'duckduckgo' && (
                <div className="ddg-optimization-section" style={{ marginTop: '24px', paddingTop: '20px', borderTop: '1px solid rgba(255, 255, 255, 0.1)' }}>
                    <label>{t('DuckDuckGo Optimization')}</label>
                    <p className="setting-description">
                        {t('DuckDuckGo includes built-in intelligent query processing that automatically:')}
                    </p>
                    <ul className="feature-list" style={{ margin: '8px 0 12px 20px', fontSize: 'calc(12px * var(--font-scale))', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                        <li>{t('Removes conversational fluff from your prompts')}</li>
                        <li>{t('Detects query intent (news, factual, comparison)')}</li>
                        <li>{t('Adds temporal context for current events')}</li>
                        <li>{t('Reranks results by relevance')}</li>
                    </ul>

                    {/* Result Count Slider */}
                    <div className="result-count-section" style={{ marginTop: '16px' }}>
                        <div className="setting-row">
                            <span className="setting-label">{t('Search Result Count')}</span>
                            <span className="setting-value">{t('{count} results', { count: searchResultCount })}</span>
                        </div>
                        <input
                            type="range"
                            min="5"
                            max="15"
                            value={searchResultCount}
                            onChange={e => setSearchResultCount(parseInt(e.target.value, 10))}
                            className="full-content-slider"
                        />
                        <p className="setting-hint">{t('More results = better coverage but slower. Default: 8')}</p>
                    </div>

                    {/* Hybrid Mode Toggle */}
                    <div className="hybrid-mode-section" style={{ marginTop: '16px' }}>
                        <label className="toggle-wrapper">
                            <input
                                type="checkbox"
                                checked={searchHybridMode}
                                onChange={e => setSearchHybridMode(e.target.checked)}
                            />
                            <span className="toggle-label">{t('Hybrid Search (Web + News)')}</span>
                        </label>
                        <p className="setting-hint" style={{ marginTop: '4px', marginLeft: '28px' }}>
                            {t('Combines general web results with recent news for better coverage of current events.')}
                        </p>
                    </div>
                </div>
            )}

            {/* Search Query Processing */}
            <div className="keyword-extraction-section" style={{ marginTop: '24px', paddingTop: '20px', borderTop: '1px solid rgba(255, 255, 255, 0.1)' }}>
                <label>{t('Search Query Processing')}</label>
                <p className="setting-description">
                    {t('Choose how your prompt is sent to the search engine.')}
                    {selectedSearchProvider === 'duckduckgo' && (
                        <span style={{ display: 'block', marginTop: '4px', color: 'var(--text-tertiary)', fontSize: 'calc(12px * var(--font-scale))' }}>
                            {t('ℹ️ DuckDuckGo uses built-in query optimization. Direct mode is recommended.')}
                        </span>
                    )}
                </p>

                <div className="provider-options">
                    <div className={`provider-option-container ${searchKeywordExtraction === 'direct' ? 'selected' : ''}`}>
                        <label className="provider-option">
                            <input
                                type="radio"
                                name="keyword_extraction"
                                value="direct"
                                checked={searchKeywordExtraction === 'direct'}
                                onChange={() => setSearchKeywordExtraction('direct')}
                            />
                            <div className="provider-info">
                                <span className="provider-name">{t('Direct (Recommended)')}</span>
                                <span className="provider-description">
                                    {t('Send your exact query to the search engine. Best for most providers.')}
                                </span>
                            </div>
                        </label>
                    </div>

                    <div className={`provider-option-container ${searchKeywordExtraction === 'yake' ? 'selected' : ''}`}>
                        <label className="provider-option">
                            <input
                                type="radio"
                                name="keyword_extraction"
                                value="yake"
                                checked={searchKeywordExtraction === 'yake'}
                                onChange={() => setSearchKeywordExtraction('yake')}
                            />
                            <div className="provider-info">
                                <span className="provider-name">{t('Smart Keywords (YAKE)')}</span>
                                <span className="provider-description">
                                    {t('Extract key terms from your prompt before searching. Useful if you paste very long prompts that confuse the search engine.')}
                                </span>
                            </div>
                        </label>
                    </div>

                    <div className={`provider-option-container ${searchKeywordExtraction === 'llm' ? 'selected' : ''}`}>
                        <label className="provider-option">
                            <input
                                type="radio"
                                name="keyword_extraction"
                                value="llm"
                                checked={searchKeywordExtraction === 'llm'}
                                onChange={() => setSearchKeywordExtraction('llm')}
                            />
                            <div className="provider-info">
                                <span className="provider-name">{t('LLM Reformulation')}</span>
                                <span className="provider-description">
                                    {t('Use the Chairman model to rephrase your query into an optimal search term. Slower but can improve results for complex questions.')}
                                </span>
                            </div>
                        </label>
                    </div>
                </div>
            </div>
        </section>
    );
}

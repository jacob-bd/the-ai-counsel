import React from 'react';

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
    return (
        <section className="settings-section">
            <h3>Web Search Provider</h3>
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
                                <span className="provider-description">{provider.description}</span>
                            </div>
                        </label>

                        {/* Inline API Key Input for Serper (Google) */}
                        {selectedSearchProvider === 'serper' && provider.id === 'serper' && (
                            <div className="inline-api-key-section">
                                <div className="api-key-input-row">
                                    <input
                                        type="password"
                                        placeholder={settings?.serper_api_key_set ? '••••••••••••••••' : 'Enter Serper API key'}
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
                                        {isTestingSerper ? 'Testing...' : (settings?.serper_api_key_set && !serperApiKey ? 'Retest' : 'Test')}
                                    </button>
                                </div>
                                {settings?.serper_api_key_set && !serperApiKey && (
                                    <div className="key-status set key-status-row">
                                        <span>✓ API key configured</span>
                                        <button
                                            type="button"
                                            className="test-button danger"
                                            onClick={() => onDisconnectSearchKey?.('serper')}
                                        >
                                            Disconnect
                                        </button>
                                    </div>
                                )}
                                {serperTestResult && (
                                    <div className={`test-result ${serperTestResult.success ? 'success' : 'error'}`}>
                                        {serperTestResult.success ? '✓' : '✗'} {serperTestResult.message}
                                    </div>
                                )}
                                <a 
                                    href="https://serper.dev" 
                                    target="_blank" 
                                    rel="noopener noreferrer"
                                    className="api-key-link"
                                    style={{ marginTop: '8px', display: 'inline-block', fontSize: '12px', color: '#60a5fa' }}
                                >
                                    Get API key at serper.dev →
                                </a>
                            </div>
                        )}

                        {/* Inline API Key Input for Tavily */}
                        {selectedSearchProvider === 'tavily' && provider.id === 'tavily' && (
                            <div className="inline-api-key-section">
                                <div className="api-key-input-row">
                                    <input
                                        type="password"
                                        placeholder={settings?.tavily_api_key_set ? '••••••••••••••••' : 'Enter Tavily API key'}
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
                                        {isTestingTavily ? 'Testing...' : (settings?.tavily_api_key_set && !tavilyApiKey ? 'Retest' : 'Test')}
                                    </button>
                                </div>
                                {settings?.tavily_api_key_set && !tavilyApiKey && (
                                    <div className="key-status set key-status-row">
                                        <span>✓ API key configured</span>
                                        <button
                                            type="button"
                                            className="test-button danger"
                                            onClick={() => onDisconnectSearchKey?.('tavily')}
                                        >
                                            Disconnect
                                        </button>
                                    </div>
                                )}
                                {tavilyTestResult && (
                                    <div className={`test-result ${tavilyTestResult.success ? 'success' : 'error'}`}>
                                        {tavilyTestResult.success ? '✓' : '✗'} {tavilyTestResult.message}
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
                                        placeholder={settings?.brave_api_key_set ? '••••••••••••••••' : 'Enter Brave API key'}
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
                                        {isTestingBrave ? 'Testing...' : (settings?.brave_api_key_set && !braveApiKey ? 'Retest' : 'Test')}
                                    </button>
                                </div>
                                {settings?.brave_api_key_set && !braveApiKey && (
                                    <div className="key-status set key-status-row">
                                        <span>✓ API key configured</span>
                                        <button
                                            type="button"
                                            className="test-button danger"
                                            onClick={() => onDisconnectSearchKey?.('brave')}
                                        >
                                            Disconnect
                                        </button>
                                    </div>
                                )}
                                {braveTestResult && (
                                    <div className={`test-result ${braveTestResult.success ? 'success' : 'error'}`}>
                                        {braveTestResult.success ? '✓' : '✗'} {braveTestResult.message}
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
                                        placeholder={settings?.tinyfish_api_key_set ? '••••••••••••••••' : 'Enter TinyFish API key'}
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
                                        {isTestingTinyfish ? 'Testing...' : (settings?.tinyfish_api_key_set && !tinyfishApiKey ? 'Retest' : 'Test')}
                                    </button>
                                </div>
                                {settings?.tinyfish_api_key_set && !tinyfishApiKey && (
                                    <div className="key-status set key-status-row">
                                        <span>✓ API key configured</span>
                                        <button
                                            type="button"
                                            className="test-button danger"
                                            onClick={() => onDisconnectSearchKey?.('tinyfish')}
                                        >
                                            Disconnect
                                        </button>
                                    </div>
                                )}
                                {tinyfishTestResult && (
                                    <div className={`test-result ${tinyfishTestResult.success ? 'success' : 'error'}`}>
                                        {tinyfishTestResult.success ? '✓' : '✗'} {tinyfishTestResult.message}
                                    </div>
                                )}
                                <div className="rate-limit-notice" style={{ marginTop: '8px', fontSize: '12px', color: '#94a3b8' }}>
                                    ⚠ Free tier: 5 searches/min. Upgrade at <a href="https://agent.tinyfish.ai" target="_blank" rel="noopener noreferrer" style={{ color: '#60a5fa' }}>agent.tinyfish.ai</a> for higher limits.
                                </div>
                                <a
                                    href="https://agent.tinyfish.ai/api-keys"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="api-key-link"
                                    style={{ marginTop: '8px', display: 'inline-block', fontSize: '12px', color: '#60a5fa' }}
                                >
                                    Get free API key at agent.tinyfish.ai →
                                </a>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            <div className="full-content-section">
                <label>Full Article Fetch (Jina AI)</label>
                <p className="setting-description">
                    Uses Jina AI to read the full text of the top search results.
                    <strong> Set to 0 to disable.</strong>
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
                    <span className="full-content-value">{fullContentResults} results</span>
                </div>
            </div>

            {/* DuckDuckGo-specific optimization settings */}
            {selectedSearchProvider === 'duckduckgo' && (
                <div className="ddg-optimization-section" style={{ marginTop: '24px', paddingTop: '20px', borderTop: '1px solid rgba(255, 255, 255, 0.1)' }}>
                    <label>DuckDuckGo Optimization</label>
                    <p className="setting-description">
                        DuckDuckGo includes built-in intelligent query processing that automatically:
                    </p>
                    <ul className="feature-list" style={{ margin: '8px 0 12px 20px', fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                        <li>Removes conversational fluff from your prompts</li>
                        <li>Detects query intent (news, factual, comparison)</li>
                        <li>Adds temporal context for current events</li>
                        <li>Reranks results by relevance</li>
                    </ul>

                    {/* Result Count Slider */}
                    <div className="result-count-section" style={{ marginTop: '16px' }}>
                        <div className="setting-row">
                            <span className="setting-label">Search Result Count</span>
                            <span className="setting-value">{searchResultCount} results</span>
                        </div>
                        <input
                            type="range"
                            min="5"
                            max="15"
                            value={searchResultCount}
                            onChange={e => setSearchResultCount(parseInt(e.target.value, 10))}
                            className="full-content-slider"
                        />
                        <p className="setting-hint">More results = better coverage but slower. Default: 8</p>
                    </div>

                    {/* Hybrid Mode Toggle */}
                    <div className="hybrid-mode-section" style={{ marginTop: '16px' }}>
                        <label className="toggle-wrapper">
                            <input
                                type="checkbox"
                                checked={searchHybridMode}
                                onChange={e => setSearchHybridMode(e.target.checked)}
                            />
                            <span className="toggle-label">Hybrid Search (Web + News)</span>
                        </label>
                        <p className="setting-hint" style={{ marginTop: '4px', marginLeft: '28px' }}>
                            Combines general web results with recent news for better coverage of current events.
                        </p>
                    </div>
                </div>
            )}

            {/* Search Query Processing */}
            <div className="keyword-extraction-section" style={{ marginTop: '24px', paddingTop: '20px', borderTop: '1px solid rgba(255, 255, 255, 0.1)' }}>
                <label>Search Query Processing</label>
                <p className="setting-description">
                    Choose how your prompt is sent to the search engine.
                    {selectedSearchProvider === 'duckduckgo' && (
                        <span style={{ display: 'block', marginTop: '4px', color: 'var(--text-tertiary)', fontSize: '12px' }}>
                            ℹ️ DuckDuckGo uses built-in query optimization. Direct mode is recommended.
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
                                <span className="provider-name">Direct (Recommended)</span>
                                <span className="provider-description">
                                    Send your exact query to the search engine. Best for most providers.
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
                                <span className="provider-name">Smart Keywords (YAKE)</span>
                                <span className="provider-description">
                                    Extract key terms from your prompt before searching. Useful if you paste very long prompts that confuse the search engine.
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
                                <span className="provider-name">LLM Reformulation</span>
                                <span className="provider-description">
                                    Use the Chairman model to rephrase your query into an optimal search term. Slower but can improve results for complex questions.
                                </span>
                            </div>
                        </label>
                    </div>
                </div>
            </div>
        </section>
    );
}

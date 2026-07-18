import { useState, useEffect, useMemo, useRef } from 'react';
import { api, DEFAULT_EXECUTION_MODE } from '../api';
import SearchableModelSelect from './SearchableModelSelect';
import ProviderSettings from './settings/ProviderSettings';
import CouncilConfig from './settings/CouncilConfig';
import SearchSettings from './settings/SearchSettings';
import PromptSettings from './settings/PromptSettings';
import DebateSettings from './settings/DebateSettings';
import GeneralSettings, { RESPONSE_LANGUAGE_DEFAULT } from './settings/GeneralSettings';
import { RESPONSE_LANGUAGES_FALLBACK } from '../constants/responseLanguages';
import { countStoredCredentials, filterOAuthModels, OAUTH_PROVIDERS } from '../constants/oauthProviders';
import './Settings.css';

const PROMPT_FIELDS = [
  'stage1_prompt',
  'stage2_prompt',
  'stage3_prompt',
  'stage4_prompt',
  'title_prompt',
  'query_prompt',
  'advisor_round1_prompt',
  'advisor_followup_prompt',
  'advisor_cross_pollination_prompt',
  'advisor_verdict_prompt',
  'advisor_tiebreaker_prompt',
];

const isBlankPrompt = (value) => typeof value !== 'string' || value.trim().length === 0;

const buildPromptValues = (source = {}, fallback = '') => (
  Object.fromEntries(PROMPT_FIELDS.map(key => [key, source[key] ?? fallback]))
);

const hasAnyDirectKey = (data) => !!(
  data?.openai_api_key_set
  || data?.anthropic_api_key_set
  || data?.google_api_key_set
  || data?.mistral_api_key_set
  || data?.deepseek_api_key_set
  || data?.nvidia_api_key_set
  || data?.opencode_api_key_set
);

/** Council toggles cannot be ON for providers that have no credentials. */
const normalizeEnabledProviders = (enabledProviders, data, ollamaConnected) => ({
  openrouter: !!enabledProviders?.openrouter && !!data?.openrouter_api_key_set,
  ollama: !!enabledProviders?.ollama && !!ollamaConnected,
  groq: !!enabledProviders?.groq && !!data?.groq_api_key_set,
  direct: !!enabledProviders?.direct && hasAnyDirectKey(data),
  custom: !!enabledProviders?.custom && !!data?.custom_endpoint_url,
  'xai-oauth': !!enabledProviders?.['xai-oauth'] && !!data?.xai_oauth_connected,
  'openai-oauth': !!enabledProviders?.['openai-oauth'] && !!data?.openai_oauth_connected,
  'github-copilot': !!enabledProviders?.['github-copilot'] && !!data?.github_copilot_connected,
});

const normalizeDirectProviderToggles = (toggles, data) => ({
  openai: !!toggles?.openai && !!data?.openai_api_key_set,
  anthropic: !!toggles?.anthropic && !!data?.anthropic_api_key_set,
  google: !!toggles?.google && !!data?.google_api_key_set,
  mistral: !!toggles?.mistral && !!data?.mistral_api_key_set,
  deepseek: !!toggles?.deepseek && !!data?.deepseek_api_key_set,
  nvidia: !!toggles?.nvidia && !!data?.nvidia_api_key_set,
  'opencode-zen': !!toggles?.['opencode-zen'] && !!data?.opencode_api_key_set,
  'opencode-go': !!toggles?.['opencode-go'] && !!data?.opencode_api_key_set,
});

export default function Settings({ onClose, ollamaStatus, onRefreshOllama, initialSection = 'llm_keys' }) {
  const [activeSection, setActiveSection] = useState(initialSection);

  const [settings, setSettings] = useState(null);
  const [selectedSearchProvider, setSelectedSearchProvider] = useState('duckduckgo');
  const [searchKeywordExtraction, setSearchKeywordExtraction] = useState('direct');
  const [fullContentResults, setFullContentResults] = useState(3);
  const [searchResultCount, setSearchResultCount] = useState(8);
  const [searchHybridMode, setSearchHybridMode] = useState(true);
  const [dateFormat, setDateFormat] = useState('auto');
  const [responseLanguage, setResponseLanguage] = useState(RESPONSE_LANGUAGE_DEFAULT);
  const [responseLanguages, setResponseLanguages] = useState(RESPONSE_LANGUAGES_FALLBACK);

  // OpenRouter State
  const [openrouterApiKey, setOpenrouterApiKey] = useState('');
  const [availableModels, setAvailableModels] = useState([]);
  const [isTestingOpenRouter, setIsTestingOpenRouter] = useState(false);
  const [openrouterTestResult, setOpenrouterTestResult] = useState(null);

  // Groq State
  const [groqApiKey, setGroqApiKey] = useState('');
  const [isTestingGroq, setIsTestingGroq] = useState(false);
  const [groqTestResult, setGroqTestResult] = useState(null);

  // Ollama State
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState('http://localhost:11434');
  const [ollamaAvailableModels, setOllamaAvailableModels] = useState([]);
  const [isTestingOllama, setIsTestingOllama] = useState(false);
  const [ollamaTestResult, setOllamaTestResult] = useState(null);

  // Custom OpenAI-compatible Endpoint State
  const [customEndpointName, setCustomEndpointName] = useState('');
  const [customEndpointUrl, setCustomEndpointUrl] = useState('');
  const [customEndpointApiKey, setCustomEndpointApiKey] = useState('');
  const [customEndpointModels, setCustomEndpointModels] = useState([]);
  const [isTestingCustomEndpoint, setIsTestingCustomEndpoint] = useState(false);
  const [customEndpointTestResult, setCustomEndpointTestResult] = useState(null);

  // Direct Provider State
  const [directKeys, setDirectKeys] = useState({
    openai_api_key: '',
    anthropic_api_key: '',
    google_api_key: '',
    mistral_api_key: '',
    deepseek_api_key: '',
    nvidia_api_key: '',
  });
  const [directAvailableModels, setDirectAvailableModels] = useState([]);

  // OpenCode (Zen + Go) State — single key, shared between products
  const [opencodeApiKey, setOpencodeApiKey] = useState('');
  const [isTestingOpencode, setIsTestingOpencode] = useState(false);
  const [opencodeTestResult, setOpencodeTestResult] = useState(null);
  const [opencodeAvailableModels, setOpencodeAvailableModels] = useState([]);

  // Validation State
  const [validatingKeys, setValidatingKeys] = useState({});
  const [keyValidationStatus, setKeyValidationStatus] = useState({});

  // Search API Keys
  const [serperApiKey, setSerperApiKey] = useState('');
  const [tavilyApiKey, setTavilyApiKey] = useState('');
  const [braveApiKey, setBraveApiKey] = useState('');
  const [isTestingSerper, setIsTestingSerper] = useState(false);
  const [isTestingTavily, setIsTestingTavily] = useState(false);
  const [isTestingBrave, setIsTestingBrave] = useState(false);
  const [serperTestResult, setSerperTestResult] = useState(null);
  const [tavilyTestResult, setTavilyTestResult] = useState(null);
  const [braveTestResult, setBraveTestResult] = useState(null);
  const [tinyfishApiKey, setTinyfishApiKey] = useState('');
  const [isTestingTinyfish, setIsTestingTinyfish] = useState(false);
  const [tinyfishTestResult, setTinyfishTestResult] = useState(null);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [showDisconnectAllConfirm, setShowDisconnectAllConfirm] = useState(false);
  const [disconnectAllBusy, setDisconnectAllBusy] = useState(false);
  const [credentialStorageTarget, setCredentialStorageTarget] = useState(null);
  const [credentialStorageBusy, setCredentialStorageBusy] = useState(false);
  const [relayItems, setRelayItems] = useState([]);
  const [relayDiscoverReason, setRelayDiscoverReason] = useState(null);
  const [relaySelected, setRelaySelected] = useState([]);
  const [relayDiscoverBusy, setRelayDiscoverBusy] = useState(false);
  const [relayImportBusy, setRelayImportBusy] = useState(false);
  const [relayImportMessage, setRelayImportMessage] = useState(null);
  const [relayBannerVisible, setRelayBannerVisible] = useState(false);

  // Enabled Providers (which sources are available)
  const [enabledProviders, setEnabledProviders] = useState({
    openrouter: true,
    ollama: false,
    groq: false,
    direct: false,
    custom: false,
    'xai-oauth': false,
    'openai-oauth': false,
    'github-copilot': false,
  });

  // Individual direct provider toggles
  const [directProviderToggles, setDirectProviderToggles] = useState({
    openai: false,
    anthropic: false,
    google: false,
    mistral: false,
    deepseek: false,
    nvidia: false,
    'opencode-zen': false,
    'opencode-go': false,
  });

  // Council Configuration (unified across all providers)
  const [councilModels, setCouncilModels] = useState([]);
  const [chairmanModel, setChairmanModel] = useState('');
  const [councilTemperature, setCouncilTemperature] = useState(0.5);
  const [chairmanTemperature, setChairmanTemperature] = useState(0.4);
  const [stage2Temperature, setStage2Temperature] = useState(0.3);

  // System Prompts State
  const [prompts, setPrompts] = useState(() => buildPromptValues());
  const [activePromptTab, setActivePromptTab] = useState('stage1');
  const [activeAdvisorPromptTab, setActiveAdvisorPromptTab] = useState('advisor_round1');

  // Debate Settings
  const [critiqueMode, setCritiqueMode] = useState('freeform');
  const [debateRounds, setDebateRounds] = useState(1);
  const [autoConverge, setAutoConverge] = useState(true);
  const [convergenceThreshold, setConvergenceThreshold] = useState(2);

  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [showFreeOnly, setShowFreeOnly] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [successMessage, setSuccessMessage] = useState(null);
  const [validationErrors, setValidationErrors] = useState({});

  

  // Remote/Local filter toggles per model type
  const [councilMemberFilters, setCouncilMemberFilters] = useState({});  // Per-member filters (indexed by member index)
  const [chairmanFilter, setChairmanFilter] = useState('remote');

  useEffect(() => {
    loadSettings();
  }, []);

  // Update activeSection when initialSection prop changes
  useEffect(() => {
    setActiveSection(initialSection);
  }, [initialSection]);

  // Debounced auto-save for all settings (API keys still save on successful test)
  const autoSaveTimerRef = useRef(null);
  const isInitialLoadRef = useRef(true);

  useEffect(() => {
    if (!settings || isInitialLoadRef.current) return;

    const settingsChanged =
      selectedSearchProvider !== (settings.search_provider || 'duckduckgo') ||
      searchKeywordExtraction !== (settings.search_keyword_extraction || 'direct') ||
      fullContentResults !== (settings.full_content_results ?? 3) ||
      searchResultCount !== (settings.search_result_count ?? 8) ||
      searchHybridMode !== (settings.search_hybrid_mode ?? true) ||
      showFreeOnly !== (settings.show_free_only ?? false) ||
      dateFormat !== (settings.date_format || 'auto') ||
      responseLanguage !== (settings.response_language || RESPONSE_LANGUAGE_DEFAULT) ||
      JSON.stringify(enabledProviders) !== JSON.stringify(settings.enabled_providers) ||
      JSON.stringify(directProviderToggles) !== JSON.stringify(settings.direct_provider_toggles) ||
      JSON.stringify(councilModels) !== JSON.stringify(settings.council_models) ||
      chairmanModel !== (settings.chairman_model || '') ||
      councilTemperature !== (settings.council_temperature ?? 0.5) ||
      chairmanTemperature !== (settings.chairman_temperature ?? 0.4) ||
      stage2Temperature !== (settings.stage2_temperature ?? 0.3) ||
      JSON.stringify(councilMemberFilters) !== JSON.stringify(settings.council_member_filters || {}) ||
      chairmanFilter !== (settings.chairman_filter || 'remote') ||
      PROMPT_FIELDS.some((key) => prompts[key] !== settings[key]) ||
      critiqueMode !== (settings.critique_mode || 'freeform') ||
      debateRounds !== (settings.debate_rounds || 1) ||
      autoConverge !== (settings.auto_converge !== undefined ? settings.auto_converge : true) ||
      convergenceThreshold !== (settings.convergence_threshold || 2);

    if (!settingsChanged) return;

    const councilChanged =
      JSON.stringify(councilModels) !== JSON.stringify(settings.council_models) ||
      chairmanModel !== (settings.chairman_model || '');
    const hasValidCouncil = councilModels.some((m) => m && m.length > 0);
    const hasValidChairman = chairmanModel && chairmanModel.length > 0;
    if (councilChanged && !hasValidCouncil && !hasValidChairman) {
      return;
    }

    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
    }

    autoSaveTimerRef.current = setTimeout(async () => {
      setIsSaving(true);
      setError(null);
      try {
        const updates = {
          search_provider: selectedSearchProvider,
          search_keyword_extraction: searchKeywordExtraction,
          full_content_results: fullContentResults,
          search_result_count: searchResultCount,
          search_hybrid_mode: searchHybridMode,
          show_free_only: showFreeOnly,
          date_format: dateFormat,
          response_language: responseLanguage,
          enabled_providers: enabledProviders,
          direct_provider_toggles: directProviderToggles,
          council_models: councilModels,
          chairman_model: chairmanModel,
          council_temperature: councilTemperature,
          chairman_temperature: chairmanTemperature,
          stage2_temperature: stage2Temperature,
          council_member_filters: councilMemberFilters,
          chairman_filter: chairmanFilter,
          critique_mode: critiqueMode,
          debate_rounds: debateRounds,
          auto_converge: autoConverge,
          convergence_threshold: convergenceThreshold,
          ...prompts,
        };
        await api.updateSettings(updates);
        setSettings((prev) => ({ ...prev, ...updates }));
        setSuccess(true);
        setTimeout(() => setSuccess(false), 2000);
      } catch (err) {
        console.error('Failed to auto-save settings:', err);
        setError('Failed to save settings');
      } finally {
        setIsSaving(false);
      }
    }, 1000);

    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current);
      }
    };
  }, [
    settings,
    selectedSearchProvider,
    searchKeywordExtraction,
    fullContentResults,
    searchResultCount,
    searchHybridMode,
    showFreeOnly,
    dateFormat,
    responseLanguage,
    enabledProviders,
    directProviderToggles,
    councilModels,
    chairmanModel,
    councilTemperature,
    chairmanTemperature,
    stage2Temperature,
    councilMemberFilters,
    chairmanFilter,
    prompts,
    critiqueMode,
    debateRounds,
    autoConverge,
    convergenceThreshold,
  ]);

  // Helper to determine if filters need to switch based on availability
  const isRemoteAvailable = enabledProviders.openrouter
    || enabledProviders.direct
    || enabledProviders.groq
    || enabledProviders.custom
    || OAUTH_PROVIDERS.some((p) => enabledProviders[p.id]);
  const isLocalAvailable = enabledProviders.ollama;

  const getNewFilter = (currentFilter) => {
    if (currentFilter === 'remote' && !isRemoteAvailable && isLocalAvailable) return 'local';
    if (currentFilter === 'local' && !isLocalAvailable && isRemoteAvailable) return 'remote';
    return currentFilter;
  };

  // Effect 1: Auto-update Council Member filters when providers change or members are added
  useEffect(() => {
    let changed = false;
    const indicesToClear = [];

    setCouncilMemberFilters(prev => {
      const next = { ...prev };
      // Check all council member indices
      for (let i = 0; i < councilModels.length; i++) {
        const currentFilter = next[i] || 'remote'; // Default is 'remote'
        const newFilter = getNewFilter(currentFilter);
        if (newFilter !== currentFilter) {
          next[i] = newFilter;
          changed = true;
          indicesToClear.push(i);
        }
      }
      return changed ? next : prev;
    });

    // Clear models whose filter changed to force re-selection
    if (indicesToClear.length > 0) {
      setCouncilModels(prev => {
        const updated = [...prev];
        indicesToClear.forEach(i => {
          updated[i] = '';
        });
        return updated;
      });
    }
  }, [enabledProviders, councilModels.length]);

  // Effect 2: Auto-update Chairman and Search filters when providers change
  // Note: We intentionally exclude councilModels.length to prevent resetting these when adding members
  useEffect(() => {
    // Update Chairman
    const newChairmanFilter = getNewFilter(chairmanFilter);
    if (newChairmanFilter !== chairmanFilter) {
      setChairmanFilter(newChairmanFilter);
      setChairmanModel('');
    }

  }, [enabledProviders, chairmanFilter]);

  // Clear validation errors when chairman or council members change
  useEffect(() => {
    if (Object.keys(validationErrors).length > 0) {
      // Check if the validation error condition is now fixed
      const hasEmptyMembers = councilModels.some(m => !m || m.length === 0);
      const hasMemberError = Object.keys(validationErrors).some(k => k.startsWith('member_'));
      const hasChairmanError = validationErrors.chairman;
      
      // Clear member error if all members are now filled
      if (hasMemberError && !hasEmptyMembers) {
        setValidationErrors({});
        setError(null);
      }
      // Clear chairman error if chairman is now selected
      else if (hasChairmanError && chairmanModel && chairmanModel.length > 0) {
        setValidationErrors({});
        setError(null);
      }
    }
  }, [chairmanModel, councilModels, validationErrors]);

  const loadSettings = async () => {
    isInitialLoadRef.current = true;
    try {
      const data = await api.getSettings();
      let defaults = {};
      if (PROMPT_FIELDS.some(key => isBlankPrompt(data[key]))) {
        defaults = await api.getDefaultSettings();
      }
      const normalizedPrompts = Object.fromEntries(
        PROMPT_FIELDS.map(key => [
          key,
          isBlankPrompt(data[key]) ? (defaults[key] || '') : data[key],
        ])
      );
      const normalizedData = { ...data, ...normalizedPrompts };

      // Set settings immediately to show UI
      setSettings(normalizedData);

      setSelectedSearchProvider(data.search_provider || 'duckduckgo');
      setSearchKeywordExtraction(data.search_keyword_extraction || 'direct');
      setFullContentResults(data.full_content_results ?? 3);
      setSearchResultCount(data.search_result_count ?? 8);
      setSearchHybridMode(data.search_hybrid_mode ?? true);
      setShowFreeOnly(data.show_free_only ?? false);
      setDateFormat(data.date_format || 'auto');
      setResponseLanguage(data.response_language || RESPONSE_LANGUAGE_DEFAULT);
      setResponseLanguages(
        Array.isArray(data.valid_response_languages) && data.valid_response_languages.length > 0
          ? data.valid_response_languages
          : RESPONSE_LANGUAGES_FALLBACK
      );

      // Enabled Providers — never show ON for sources that aren't configured
      if (data.enabled_providers) {
        setEnabledProviders(normalizeEnabledProviders(
          data.enabled_providers,
          data,
          ollamaStatus?.connected
        ));
      } else {
        const hasDirectConfigured = hasAnyDirectKey(data);

        setEnabledProviders(normalizeEnabledProviders({
          openrouter: !!data.openrouter_api_key_set || (!hasDirectConfigured && !ollamaStatus?.connected && !data.groq_api_key_set),
          ollama: ollamaStatus?.connected || false,
          groq: !!data.groq_api_key_set,
          direct: hasDirectConfigured,
          custom: !!data.custom_endpoint_url,
        }, data, ollamaStatus?.connected));
      }

      // Individual direct provider toggles - load from saved settings
      if (data.direct_provider_toggles) {
        setDirectProviderToggles(normalizeDirectProviderToggles(
          data.direct_provider_toggles,
          data
        ));
      } else {
        setDirectProviderToggles(normalizeDirectProviderToggles({
          openai: !!data.openai_api_key_set,
          anthropic: !!data.anthropic_api_key_set,
          google: !!data.google_api_key_set,
          mistral: !!data.mistral_api_key_set,
          deepseek: !!data.deepseek_api_key_set,
          nvidia: !!data.nvidia_api_key_set,
          'opencode-zen': !!data.opencode_api_key_set,
          'opencode-go': !!data.opencode_api_key_set,
        }, data));
      }

      // Council Configuration (unified)
      const loadedCouncilModels = data.council_models || [];
      const loadedChairmanModel = data.chairman_model || '';
      setCouncilModels(loadedCouncilModels);
      setChairmanModel(loadedChairmanModel);
      setCouncilTemperature(data.council_temperature ?? 0.5);
      setChairmanTemperature(data.chairman_temperature ?? 0.4);
      setStage2Temperature(data.stage2_temperature ?? 0.3);

      setTimeout(() => {
        isInitialLoadRef.current = false;
      }, 500);

      // Remote/Local filters - load from saved settings
      if (data.council_member_filters) {
        setCouncilMemberFilters(data.council_member_filters);
      }
      if (data.chairman_filter) {
        setChairmanFilter(data.chairman_filter);
      }
      // Ollama Settings
      setOllamaBaseUrl(data.ollama_base_url || 'http://localhost:11434');

      // Custom Endpoint Settings
      if (data.custom_endpoint_name) setCustomEndpointName(data.custom_endpoint_name);
      if (data.custom_endpoint_url) setCustomEndpointUrl(data.custom_endpoint_url);
      // API key is not sent to frontend for security, similar to other keys

      // Prompts
      setPrompts(normalizedPrompts);

      // Debate Settings
      setCritiqueMode(data.critique_mode || 'freeform');
      setDebateRounds(data.debate_rounds || 1);
      setAutoConverge(data.auto_converge !== undefined ? data.auto_converge : true);
      setConvergenceThreshold(data.convergence_threshold || 2);

      // Clear Direct Keys (for security)
      setDirectKeys({
        openai_api_key: '',
        anthropic_api_key: '',
        google_api_key: '',
        mistral_api_key: '',
        deepseek_api_key: '',
        nvidia_api_key: '',
      });
      setGroqApiKey(''); // Clear Groq key too

      // Load available models in background
      loadModels();
      loadOllamaModels(data.ollama_base_url || 'http://localhost:11434');
      if (data.custom_endpoint_url) {
        loadCustomEndpointModels();
      }
      if (data.opencode_api_key_set) {
        loadOpencodeModels();
      }

    } catch (err) {
      console.error("Error loading settings:", err);
      setError('Failed to load settings');
    }
  };

  const loadModels = async () => {
    setIsLoadingModels(true);
    try {
      const data = await api.getModels();
      if (data.models && data.models.length > 0) {
        // Sort models alphabetically
        const sorted = data.models.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
        setAvailableModels(sorted);
      }

      // Fetch direct models from backend
      try {
        const directModels = await api.getDirectModels();
        setDirectAvailableModels(directModels);
      } catch (error) {
        console.error('Failed to fetch direct models:', error);
        // Fallback to empty list or basic models if fetch fails
        setDirectAvailableModels([]);
      }

    } catch (err) {
      console.warn('Failed to load models:', err);
    } finally {
      setIsLoadingModels(false);
    }
  };

  const loadOllamaModels = async (baseUrl) => {
    try {
      const data = await api.getOllamaModels(baseUrl);
      if (data.models && data.models.length > 0) {
        // Sort models alphabetically
        const sorted = data.models.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
        setOllamaAvailableModels(sorted);
      }
    } catch (err) {
      console.warn('Failed to load Ollama models:', err);
    }
  };

  const loadCustomEndpointModels = async () => {
    try {
      const data = await api.getCustomEndpointModels();
      if (data.models && data.models.length > 0) {
        const sorted = data.models.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
        setCustomEndpointModels(sorted);
      }
    } catch (err) {
      console.warn('Failed to load custom endpoint models:', err);
    }
  };

  const handleTestCustomEndpoint = async () => {
    if (!customEndpointName || !customEndpointUrl) {
      setCustomEndpointTestResult({ success: false, message: 'Please enter a name and URL' });
      return;
    }
    setIsTestingCustomEndpoint(true);
    setCustomEndpointTestResult(null);
    try {
      const result = await api.testCustomEndpoint(customEndpointName, customEndpointUrl, customEndpointApiKey);
      setCustomEndpointTestResult(result);

      // Auto-save if connection succeeds
      if (result.success) {
        const nextEnabled = { ...enabledProviders, custom: true };
        await api.updateSettings({
          custom_endpoint_name: customEndpointName,
          custom_endpoint_url: customEndpointUrl,
          custom_endpoint_api_key: customEndpointApiKey || null,
          enabled_providers: nextEnabled
        });
        setEnabledProviders(nextEnabled);
        // Reload settings to get the updated state
        const updatedSettings = await api.getSettings();
        setSettings(updatedSettings);
        // Load models from the new endpoint
        loadCustomEndpointModels();
      }
    } catch (err) {
      setCustomEndpointTestResult({ success: false, message: err.message });
    } finally {
      setIsTestingCustomEndpoint(false);
    }
  };

  const resetCustomEndpointLocalState = () => {
    setCustomEndpointName('');
    setCustomEndpointUrl('');
    setCustomEndpointApiKey('');
    setCustomEndpointModels([]);
    setCustomEndpointTestResult(null);
  };

  const handleDisconnectProviderKey = async ({
    secretField,
    label = 'provider',
    enabledPatch = null,
    directTogglePatch = null,
    extraUpdates = null,
    onLocalClear,
  }) => {
    try {
      setError(null);
      const updates = { [secretField]: '', ...(extraUpdates || {}) };
      if (enabledPatch) {
        updates.enabled_providers = { ...enabledProviders, ...enabledPatch };
      }
      if (directTogglePatch) {
        updates.direct_provider_toggles = { ...directProviderToggles, ...directTogglePatch };
      }
      const result = await api.updateSettings(updates);
      onLocalClear?.();
      if (enabledPatch) {
        setEnabledProviders((prev) => ({ ...prev, ...enabledPatch }));
      }
      if (directTogglePatch) {
        setDirectProviderToggles((prev) => ({ ...prev, ...directTogglePatch }));
      }
      // Prefer server response so UI clears even before a full reload.
      if (result && typeof result === 'object') {
        setSettings((prev) => ({ ...prev, ...result }));
      }
      await loadSettings();
      await loadModels();
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err.message || `Failed to disconnect ${label}`);
    }
  };

  const handleClearCustomEndpoint = async () => {
    try {
      await api.updateSettings({
        custom_endpoint_name: '',
        custom_endpoint_url: '',
        custom_endpoint_api_key: '',
        enabled_providers: { ...enabledProviders, custom: false },
      });
      resetCustomEndpointLocalState();
      setEnabledProviders((prev) => ({ ...prev, custom: false }));
      await loadSettings();
      await loadModels();
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError('Failed to disconnect custom endpoint');
    }
  };

  const handleDisconnectOpenRouter = () => handleDisconnectProviderKey({
    secretField: 'openrouter_api_key',
    label: 'OpenRouter',
    enabledPatch: { openrouter: false },
    onLocalClear: () => {
      setOpenrouterApiKey('');
      setOpenrouterTestResult(null);
    },
  });

  const handleDisconnectGroq = () => handleDisconnectProviderKey({
    secretField: 'groq_api_key',
    label: 'Groq',
    enabledPatch: { groq: false },
    onLocalClear: () => {
      setGroqApiKey('');
      setGroqTestResult(null);
    },
  });

  const handleDisconnectDirectKey = (providerId, keyField) => handleDisconnectProviderKey({
    secretField: keyField,
    label: providerId,
    directTogglePatch: { [providerId]: false },
    onLocalClear: () => {
      setDirectKeys((prev) => ({ ...prev, [keyField]: '' }));
      setKeyValidationStatus((prev) => {
        const next = { ...prev };
        delete next[providerId];
        return next;
      });
    },
  });

  const handleDisconnectOpencode = () => handleDisconnectProviderKey({
    secretField: 'opencode_api_key',
    label: 'OpenCode',
    directTogglePatch: { 'opencode-zen': false, 'opencode-go': false },
    onLocalClear: () => {
      setOpencodeApiKey('');
      setOpencodeTestResult(null);
    },
  });

  const handleDisconnectSearchKey = (providerId) => {
    const field = `${providerId}_api_key`;
    const localClearers = {
      serper: () => { setSerperApiKey(''); setSerperTestResult(null); },
      tavily: () => { setTavilyApiKey(''); setTavilyTestResult(null); },
      brave: () => { setBraveApiKey(''); setBraveTestResult(null); },
      tinyfish: () => { setTinyfishApiKey(''); setTinyfishTestResult(null); },
    };
    return handleDisconnectProviderKey({
      secretField: field,
      label: providerId,
      extraUpdates: selectedSearchProvider === providerId
        ? { search_provider: 'duckduckgo' }
        : null,
      onLocalClear: () => {
        localClearers[providerId]?.();
        if (selectedSearchProvider === providerId) {
          setSelectedSearchProvider('duckduckgo');
        }
      },
    });
  };

  const handleTestSerper = async () => {
    if (!serperApiKey && !settings.serper_api_key_set) {
      setSerperTestResult({ success: false, message: 'Please enter an API key first' });
      return;
    }
    setIsTestingSerper(true);
    setSerperTestResult(null);
    try {
      // If input is empty but key is configured, pass null to test the saved key
      const keyToTest = serperApiKey || null;
      const result = await api.testSerperKey(keyToTest);
      setSerperTestResult(result);

      // Auto-save API key AND provider selection if validation succeeds
      if (result.success && serperApiKey) {
        // Save both the API key and switch provider to Serper
        await api.updateSettings({ 
          serper_api_key: serperApiKey,
          search_provider: 'serper'
        });
        setSerperApiKey(''); // Clear input after save

        // Reload settings (will now have serper as provider)
        await loadSettings();

        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      setSerperTestResult({ success: false, message: 'Test failed' });
    } finally {
      setIsTestingSerper(false);
    }
  };

  const handleTestTavily = async () => {
    if (!tavilyApiKey && !settings.tavily_api_key_set) {
      setTavilyTestResult({ success: false, message: 'Please enter an API key first' });
      return;
    }
    setIsTestingTavily(true);
    setTavilyTestResult(null);
    try {
      // If input is empty but key is configured, pass null to test the saved key
      const keyToTest = tavilyApiKey || null;
      const result = await api.testTavilyKey(keyToTest);
      setTavilyTestResult(result);

      // Auto-save API key AND provider selection if validation succeeds
      if (result.success && tavilyApiKey) {
        // Save both the API key and switch provider to Tavily
        await api.updateSettings({ 
          tavily_api_key: tavilyApiKey,
          search_provider: 'tavily'
        });
        setTavilyApiKey(''); // Clear input after save

        // Reload settings (will now have tavily as provider)
        await loadSettings();

        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      setTavilyTestResult({ success: false, message: 'Test failed' });
    } finally {
      setIsTestingTavily(false);
    }
  };

  const handleTestBrave = async () => {
    if (!braveApiKey && !settings.brave_api_key_set) {
      setBraveTestResult({ success: false, message: 'Please enter an API key first' });
      return;
    }
    setIsTestingBrave(true);
    setBraveTestResult(null);
    try {
      // If input is empty but key is configured, pass null to test the saved key
      const keyToTest = braveApiKey || null;
      const result = await api.testBraveKey(keyToTest);
      setBraveTestResult(result);

      // Auto-save API key AND provider selection if validation succeeds
      if (result.success && braveApiKey) {
        // Save both the API key and switch provider to Brave
        await api.updateSettings({ 
          brave_api_key: braveApiKey,
          search_provider: 'brave'
        });
        setBraveApiKey(''); // Clear input after save

        // Reload settings (will now have brave as provider)
        await loadSettings();

        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      setBraveTestResult({ success: false, message: 'Test failed' });
    } finally {
      setIsTestingBrave(false);
    }
  };

  const handleTestTinyfish = async () => {
    if (!tinyfishApiKey && !settings.tinyfish_api_key_set) {
      setTinyfishTestResult({ success: false, message: 'Please enter an API key first' });
      return;
    }
    setIsTestingTinyfish(true);
    setTinyfishTestResult(null);
    try {
      const keyToTest = tinyfishApiKey || null;
      const result = await api.testTinyfishKey(keyToTest);
      setTinyfishTestResult(result);

      // Auto-save API key AND provider selection if validation succeeds
      if (result.success && tinyfishApiKey) {
        await api.updateSettings({
          tinyfish_api_key: tinyfishApiKey,
          search_provider: 'tinyfish'
        });
        setTinyfishApiKey('');
        await loadSettings();
        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      setTinyfishTestResult({ success: false, message: 'Test failed' });
    } finally {
      setIsTestingTinyfish(false);
    }
  };

  const handleTestOpenRouter = async () => {
    if (!openrouterApiKey && !settings.openrouter_api_key_set) {
      setOpenrouterTestResult({ success: false, message: 'Please enter an API key first' });
      return;
    }
    setIsTestingOpenRouter(true);
    setOpenrouterTestResult(null);
    try {
      // If input is empty but key is configured, pass null to test the saved key
      const keyToTest = openrouterApiKey || null;
      const result = await api.testOpenRouterKey(keyToTest);
      setOpenrouterTestResult(result);

      // Auto-save API key if validation succeeds and a new key was provided
      if (result.success && openrouterApiKey) {
        const nextEnabled = { ...enabledProviders, openrouter: true };
        await api.updateSettings({
          openrouter_api_key: openrouterApiKey,
          enabled_providers: nextEnabled
        });
        setOpenrouterApiKey(''); // Clear input after save
        setEnabledProviders(nextEnabled);

        // Reload settings
        await loadSettings();

        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      setOpenrouterTestResult({ success: false, message: 'Test failed' });
    } finally {
      setIsTestingOpenRouter(false);
    }
  };

  const handleTestGroq = async () => {
    if (!groqApiKey && !settings.groq_api_key_set) {
      setGroqTestResult({ success: false, message: 'Please enter an API key first' });
      return;
    }
    setIsTestingGroq(true);
    setGroqTestResult(null);
    try {
      // If input is empty but key is configured, test with saved key via generic provider test
      // Note: backend/providers/groq.py must be registered with id 'groq'
      // Pass empty string if using stored key, backend will handle it
      const result = await api.testProviderKey('groq', groqApiKey || "");
      setGroqTestResult(result);

      // Auto-save API key if validation succeeds and a new key was provided
      if (result.success && groqApiKey) {
        const nextEnabled = { ...enabledProviders, groq: true };
        await api.updateSettings({
          groq_api_key: groqApiKey,
          enabled_providers: nextEnabled
        });
        setGroqApiKey(''); // Clear input after save
        setEnabledProviders(nextEnabled);

        // Reload settings
        await loadSettings();

        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      setGroqTestResult({ success: false, message: 'Test failed' });
    } finally {
      setIsTestingGroq(false);
    }
  };

  const handleTestOllama = async () => {
    setIsTestingOllama(true);
    setOllamaTestResult(null);
    try {
      const result = await api.testOllamaConnection(ollamaBaseUrl);
      setOllamaTestResult(result);

      // Always refresh parent component's ollama status (success or failure)
      if (onRefreshOllama) {
        onRefreshOllama(ollamaBaseUrl);
      }

      if (result.success) {
        // Auto-save base URL if connection succeeds
        const nextEnabled = { ...enabledProviders, ollama: true };
        await api.updateSettings({
          ollama_base_url: ollamaBaseUrl,
          enabled_providers: nextEnabled
        });
        setEnabledProviders(nextEnabled);

        // Reload settings
        await loadSettings();

        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      setOllamaTestResult({ success: false, message: 'Connection failed' });

      // Refresh parent status on exception too
      if (onRefreshOllama) {
        onRefreshOllama(ollamaBaseUrl);
      }
    } finally {
      setIsTestingOllama(false);
    }
  };

  const handleDisconnectOllama = async () => {
    try {
      setError(null);
      const nextEnabled = { ...enabledProviders, ollama: false };
      await api.updateSettings({ enabled_providers: nextEnabled });
      setEnabledProviders(nextEnabled);
      setOllamaTestResult(null);
      setOllamaAvailableModels([]);
      await loadSettings();
      await loadModels();
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err.message || 'Failed to disconnect Ollama');
    }
  };

  const handlePromptChange = (key, value) => {
    setPrompts(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const handleResetPrompt = async (key) => {
    try {
      const defaults = await api.getDefaultSettings();
      console.log('Defaults fetched:', defaults);
      if (defaults[key] !== undefined) {
        handlePromptChange(key, defaults[key]);
        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      } else {
        console.warn(`Default for key ${key} not found in defaults`, defaults);
      }
    } catch (err) {
      console.error("Failed to fetch default prompt", err);
      setError("Failed to reset prompt");
    }
  };

  const handleDateFormatChange = (newFormat) => setDateFormat(newFormat);

  const handleResponseLanguageChange = (newLanguage) => setResponseLanguage(newLanguage);

  const handleResetToDefaults = () => {
    setShowResetConfirm(true);
  };

  const confirmDisconnectAllProviders = async () => {
    setDisconnectAllBusy(true);
    setError(null);
    try {
      const result = await api.disconnectAllProviders();
      setShowDisconnectAllConfirm(false);
      setKeyValidationStatus({});
      setOpenrouterTestResult(null);
      setGroqTestResult(null);
      setOpencodeTestResult(null);
      setTavilyTestResult(null);
      setBraveTestResult(null);
      setSerperTestResult(null);
      setTinyfishTestResult(null);
      setRelayImportMessage(null);
      resetCustomEndpointLocalState();
      setOpenrouterApiKey('');
      setGroqApiKey('');
      setOpencodeApiKey('');
      setDirectKeys({
        openai_api_key: '',
        anthropic_api_key: '',
        google_api_key: '',
        mistral_api_key: '',
        deepseek_api_key: '',
        nvidia_api_key: '',
      });
      await loadSettings();
      await loadModels();
      setSuccessMessage(
        result?.message
        || `Disconnected all providers (${result?.cleared ?? 0} credentials cleared).`
      );
      setSuccess(true);
      setTimeout(() => {
        setSuccess(false);
        setSuccessMessage(null);
      }, 4000);
    } catch (err) {
      setError(err.message || 'Failed to disconnect all providers');
      setShowDisconnectAllConfirm(false);
    } finally {
      setDisconnectAllBusy(false);
    }
  };

  const confirmResetToDefaults = async () => {
    setShowResetConfirm(false);

    try {
      // 1. Disable all providers
      setEnabledProviders({
        openrouter: false,
        ollama: false,
        groq: false,
        direct: false,
        custom: false,
        'xai-oauth': false,
        'openai-oauth': false,
        'github-copilot': false,
      });
      resetCustomEndpointLocalState();

      setDirectProviderToggles({
        openai: false,
        anthropic: false,
        google: false,
        mistral: false,
        deepseek: false,
        nvidia: false
      });

      // 2. Reset Models to "Blank Slate" (User must select)
      // Initialize with 2 empty slots for council
      setCouncilModels(['', '']);
      setChairmanModel('');
      setCouncilTemperature(0.5);
      setChairmanTemperature(0.4);
      setStage2Temperature(0.3);

      // Reset filters to 'remote' default
      setCouncilMemberFilters({ 0: 'remote', 1: 'remote' });
      setChairmanFilter('remote');

      // 3. General Settings Defaults
      setSelectedSearchProvider('duckduckgo');
      setSearchKeywordExtraction('direct');
      setFullContentResults(3);
      setShowFreeOnly(false);
      setDateFormat('auto');
      setResponseLanguage(RESPONSE_LANGUAGE_DEFAULT);
      setOllamaBaseUrl('http://localhost:11434');

      // Reset debate settings
      setCritiqueMode('freeform');
      setDebateRounds(1);
      setAutoConverge(true);
      setConvergenceThreshold(2);

      // 4. Reset Prompts to System Defaults (keep these useful)
      const defaults = await api.getDefaultSettings();
      const defaultPrompts = buildPromptValues(defaults);
      setPrompts(defaultPrompts);

      // 5. Save the reset settings to backend
      const updates = {
        search_provider: 'duckduckgo',
        full_content_results: 3,
        enabled_providers: {
          openrouter: false,
          ollama: false,
          groq: false,
          direct: false,
          custom: false,
          'xai-oauth': false,
          'openai-oauth': false,
          'github-copilot': false,
        },
        custom_endpoint_name: '',
        custom_endpoint_url: '',
        custom_endpoint_api_key: '',
        direct_provider_toggles: {
          openai: false,
          anthropic: false,
          google: false,
          mistral: false,
          deepseek: false,
          nvidia: false,
          'opencode-zen': false,
          'opencode-go': false,
        },
        council_models: ['', ''],
        chairman_model: '',
        council_temperature: 0.5,
        chairman_temperature: 0.4,
        stage2_temperature: 0.3,
        search_query_model: '',
        council_member_filters: { 0: 'remote', 1: 'remote' },
        chairman_filter: 'remote',
        search_query_filter: 'remote',
        critique_mode: 'freeform',
        debate_rounds: 1,
        auto_converge: true,
        convergence_threshold: 2,
        date_format: 'auto',
        response_language: RESPONSE_LANGUAGE_DEFAULT,
        ...defaultPrompts,
      };
      await api.updateSettings(updates);

      await loadSettings();
      setSuccess(true);
      setActiveSection('council');

      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError('Failed to reset settings');
    }
  };

  const handleTestOpencode = async () => {
    const apiKey = opencodeApiKey;
    if (!apiKey && !settings?.opencode_api_key_set) return;

    setIsTestingOpencode(true);
    setOpencodeTestResult(null);

    try {
      const result = await api.testOpencodeKey(apiKey || '');
      // result is either { success, message } (single product) or { success, results: {zen, go} }
      if (result?.results) {
        const zenOk = result.results.zen?.success;
        const goOk = result.results.go?.success;
        const summary = [
          zenOk ? '✓ Zen' : '✗ Zen',
          goOk ? '✓ Go' : '✗ Go',
        ].join(' · ');
        const messages = [result.results.zen?.message, result.results.go?.message]
          .filter(Boolean)
          .join(' / ');
        setOpencodeTestResult({
          success: result.success,
          message: `${summary} — ${messages}`,
        });
      } else {
        setOpencodeTestResult({
          success: !!result?.success,
          message: result?.message || 'No response from OpenCode',
        });
      }

      if (result?.success && apiKey) {
        const nextEnabled = { ...enabledProviders, direct: true };
        const nextDirectToggles = { ...directProviderToggles, 'opencode-zen': true, 'opencode-go': true };
        await api.updateSettings({
          opencode_api_key: apiKey,
          enabled_providers: nextEnabled,
          direct_provider_toggles: nextDirectToggles
        });
        setOpencodeApiKey('');
        setEnabledProviders(nextEnabled);
        setDirectProviderToggles(nextDirectToggles);
        await loadSettings();
        await loadOpencodeModels();
        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      setOpencodeTestResult({
        success: false,
        message: err?.response?.data?.detail || err?.message || 'Test failed',
      });
    } finally {
      setIsTestingOpencode(false);
    }
  };

  const loadOpencodeModels = async () => {
    try {
      const all = await api.getDirectModels();
      const opencodeOnly = (all || []).filter(m => {
        const name = m.provider || '';
        return name === 'OpenCode Zen' || name === 'OpenCode Go';
      });
      setOpencodeAvailableModels(opencodeOnly);
    } catch (err) {
      console.error('Failed to load OpenCode models:', err);
      setOpencodeAvailableModels([]);
    }
  };

  const handleTestDirectKey = async (providerId, keyField) => {
    const apiKey = directKeys[keyField];
    // Allow if key is entered OR if it's already set (Retest mode)
    if (!apiKey && !settings?.[`${keyField}_set`]) return;

    setValidatingKeys(prev => ({ ...prev, [providerId]: true }));
    setKeyValidationStatus(prev => ({ ...prev, [providerId]: null }));

    try {
      // Pass empty string if using stored key, backend will handle it
      const result = await api.testProviderKey(providerId, apiKey || "");
      setKeyValidationStatus(prev => ({
        ...prev,
        [providerId]: {
          success: result.success,
          message: result.message
        }
      }));

      // Auto-save API key if validation succeeds AND it was a new key
      if (result.success && apiKey) {
        const nextEnabled = { ...enabledProviders, direct: true };
        const nextDirectToggles = { ...directProviderToggles, [providerId]: true };
        await api.updateSettings({
          [keyField]: apiKey,
          enabled_providers: nextEnabled,
          direct_provider_toggles: nextDirectToggles
        });
        setDirectKeys(prev => ({ ...prev, [keyField]: '' })); // Clear input after save
        setEnabledProviders(nextEnabled);
        setDirectProviderToggles(nextDirectToggles);

        // Reload settings
        await loadSettings();

        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      setKeyValidationStatus(prev => ({
        ...prev,
        [providerId]: {
          success: false,
          message: err.message
        }
      }));
    } finally {
      setValidatingKeys(prev => ({ ...prev, [providerId]: false }));
    }
  };



  const handleExportCouncil = () => {
    const config = {
      // General
      search_provider: selectedSearchProvider,
      search_keyword_extraction: searchKeywordExtraction,
      full_content_results: fullContentResults,
      search_result_count: searchResultCount,
      search_hybrid_mode: searchHybridMode,
      show_free_only: showFreeOnly,

      // Enabled Providers
      enabled_providers: enabledProviders,
      direct_provider_toggles: directProviderToggles,

      // Council Configuration (unified)
      council_models: councilModels,
      chairman_model: chairmanModel,

      // Temperature Settings
      council_temperature: councilTemperature,
      chairman_temperature: chairmanTemperature,
      stage2_temperature: stage2Temperature,

      // Filters
      council_member_filters: councilMemberFilters,
      chairman_filter: chairmanFilter,

      // Ollama Base URL
      ollama_base_url: ollamaBaseUrl,

      // Display
      date_format: dateFormat,
      response_language: responseLanguage,

      // Prompts
      prompts: prompts
    };

    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(config, null, 2));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", "council_config.json");
    document.body.appendChild(downloadAnchorNode); // required for firefox
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
  };

  const handleImportCouncil = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const config = JSON.parse(e.target.result);

        // Apply General Settings
        if (config.search_provider) setSelectedSearchProvider(config.search_provider);
        if (config.search_keyword_extraction) setSearchKeywordExtraction(config.search_keyword_extraction);
        if (config.full_content_results !== undefined) setFullContentResults(config.full_content_results);
        if (config.search_result_count !== undefined) setSearchResultCount(config.search_result_count);
        if (config.search_hybrid_mode !== undefined) setSearchHybridMode(config.search_hybrid_mode);
        if (config.show_free_only !== undefined) setShowFreeOnly(config.show_free_only);

        // Apply Enabled Providers
        if (config.enabled_providers && settings) {
          setEnabledProviders(normalizeEnabledProviders(
            config.enabled_providers,
            settings,
            ollamaStatus?.connected
          ));
        }
        if (config.direct_provider_toggles && settings) {
          setDirectProviderToggles(normalizeDirectProviderToggles(
            config.direct_provider_toggles,
            settings
          ));
        }

        // Apply Council Configuration (unified)
        if (config.council_models) setCouncilModels(config.council_models);
        if (config.chairman_model) setChairmanModel(config.chairman_model);

        // Apply Temperature Settings
        if (config.council_temperature !== undefined) setCouncilTemperature(config.council_temperature);
        if (config.chairman_temperature !== undefined) setChairmanTemperature(config.chairman_temperature);
        if (config.stage2_temperature !== undefined) setStage2Temperature(config.stage2_temperature);

        // Apply Filters
        if (config.council_member_filters) setCouncilMemberFilters(config.council_member_filters);
        if (config.chairman_filter) setChairmanFilter(config.chairman_filter);

        // Apply Ollama Base URL
        if (config.ollama_base_url) setOllamaBaseUrl(config.ollama_base_url);

        // Apply Display Preferences
        if (config.date_format) setDateFormat(config.date_format);
        if (config.response_language) setResponseLanguage(config.response_language);

        // Apply Prompts
        if (config.prompts) {
          setPrompts(prev => ({ ...prev, ...config.prompts }));
        }

        // Validate imported models against all available models
        const allModels = allAvailableModels;
        const missingModels = (config.council_models || []).filter(id =>
          !allModels.find(m => m.id === id)
        );

        if (missingModels.length > 0) {
          setError(`Imported with warnings: Models not found: ${missingModels.join(', ')}`);
        } else {
          setSuccess(true);
          setTimeout(() => setSuccess(false), 3000);
        }

      } catch (err) {
        setError(`Import failed: ${err.message}`);
      }
    };
    reader.readAsText(file);
    // Reset input
    event.target.value = '';
  };

  const currentCredentialStorage = settings?.credential_storage_preferred
    ?? settings?.credential_storage
    ?? 'file';

  const handleCredentialStorageChange = (mode) => {
    if (mode === currentCredentialStorage) return;
    setCredentialStorageTarget(mode);
  };

  const confirmCredentialStorageMigration = async () => {
    if (!credentialStorageTarget) return;
    setCredentialStorageBusy(true);
    setError(null);
    try {
      const result = await api.setCredentialStorage(credentialStorageTarget);
      setCredentialStorageTarget(null);
      await loadSettings();
      const moved = result.moved ?? 0;
      setSuccess(true);
      if (moved > 0) {
        setError(null);
      }
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err.message || 'Failed to migrate credentials');
      setCredentialStorageTarget(null);
    } finally {
      setCredentialStorageBusy(false);
    }
  };

  const handleDiscoverRelayAi = async () => {
    setRelayDiscoverBusy(true);
    setRelayDiscoverReason(null);
    setRelayImportMessage(null);
    try {
      const data = await api.discoverRelayAi();
      const items = data.items || [];
      setRelayItems(items);
      setRelayDiscoverReason(data.reason || data.hint || null);
      setRelaySelected(items.filter((i) => !i.already_configured_in_counsel).map((i) => i.relay_id));
      if (items.length > 0 && !settings?.relay_ai_import_dismissed) {
        setRelayBannerVisible(true);
      }
    } catch (err) {
      setRelayDiscoverReason(err.message);
      setRelayItems([]);
    } finally {
      setRelayDiscoverBusy(false);
    }
  };

  const handleImportRelayAi = async () => {
    if (relaySelected.length === 0) return;
    setRelayImportBusy(true);
    setError(null);
    setRelayImportMessage(null);
    try {
      const selected = [...relaySelected];
      const result = await api.importRelayAi(selected, true);
      // Clear stale Retest errors from before import (keys were in store, not settings.json).
      setKeyValidationStatus({});
      setOpenrouterTestResult(null);
      setGroqTestResult(null);
      setOpencodeTestResult(null);
      setTavilyTestResult(null);
      setBraveTestResult(null);
      setSerperTestResult(null);
      setTinyfishTestResult(null);
      await loadSettings();
      await loadModels();
      // Update local list — do not re-discover (avoids another macOS Keychain prompt storm).
      setRelayItems((prev) => prev.map((item) => (
        selected.includes(item.relay_id)
          ? { ...item, already_configured_in_counsel: true }
          : item
      )));
      setRelaySelected([]);

      const importedCount = Array.isArray(result?.imported) ? result.imported.length : selected.length;
      const skippedCount = Array.isArray(result?.skipped) ? result.skipped.length : 0;
      const errorCount = result?.errors ? Object.keys(result.errors).length : 0;
      let message = `✓ Imported successfully — ${importedCount} credential${importedCount === 1 ? '' : 's'} added.`;
      if (skippedCount > 0) {
        message += ` ${skippedCount} skipped.`;
      }
      if (errorCount > 0) {
        message += ` ${errorCount} failed.`;
      }
      setRelayImportMessage({
        tone: errorCount > 0 && importedCount === 0 ? 'error' : 'success',
        text: message,
      });
      setSuccess(true);
      setTimeout(() => setSuccess(false), 4000);
    } catch (err) {
      setRelayImportMessage({
        tone: 'error',
        text: err.message || 'Failed to import credentials',
      });
      setError(err.message || 'Failed to import credentials');
    } finally {
      setRelayImportBusy(false);
    }
  };

  const handleDismissRelayBanner = async () => {
    try {
      await api.dismissRelayImport();
      setRelayBannerVisible(false);
      setSettings((prev) => ({ ...prev, relay_ai_import_dismissed: true }));
    } catch (err) {
      setError(err.message || 'Failed to dismiss banner');
    }
  };

  const handleOAuthSettingsChange = (data) => {
    setSettings(data);
    setEnabledProviders(normalizeEnabledProviders(
      data.enabled_providers || enabledProviders,
      data,
      ollamaStatus?.connected
    ));
  };

  // Helper function to check if a direct provider is configured
  const isDirectProviderConfigured = (providerName) => {
    switch (providerName) {
      case 'OpenAI': return !!(directKeys.openai_api_key || settings?.openai_api_key_set);
      case 'Anthropic': return !!(directKeys.anthropic_api_key || settings?.anthropic_api_key_set);
      case 'Google': return !!(directKeys.google_api_key || settings?.google_api_key_set);
      case 'Mistral': return !!(directKeys.mistral_api_key || settings?.mistral_api_key_set);
      case 'DeepSeek': return !!(directKeys.deepseek_api_key || settings?.deepseek_api_key_set);
      case 'NVIDIA': return !!(directKeys.nvidia_api_key || settings?.nvidia_api_key_set);
      case 'OpenCode Zen': return !!settings?.opencode_api_key_set;
      case 'OpenCode Go': return !!settings?.opencode_api_key_set;
      default: return false;
    }
  };

  // Get all available models from all sources
  const allAvailableModels = useMemo(() => {
    const models = [];

    // Add OpenRouter models if enabled
    if (enabledProviders.openrouter) {
      models.push(...availableModels);
    }

    // Add Ollama models if enabled
    if (enabledProviders.ollama) {
      models.push(...ollamaAvailableModels.map(m => ({
        ...m,
        id: `ollama:${m.id}`,
        name: `${m.name || m.id} (Local)`,
        provider: 'Ollama'
      })));
    }

    // Add Groq models if enabled
    if (enabledProviders.groq) {
      const groqModels = directAvailableModels.filter(m => m.provider === 'Groq');
      models.push(...groqModels);
    }

    // Add direct provider models if master toggle is enabled AND individual provider is enabled
    if (enabledProviders.direct) {
      const filteredDirectModels = directAvailableModels.filter(m => {
        if (m.provider === 'Groq') return false; // Handled separately above
        const providerKey = m.provider.toLowerCase().replace(/\s+/g, '-');
        const individualToggleEnabled = directProviderToggles[providerKey];
        const providerConfigured = isDirectProviderConfigured(m.provider);
        return individualToggleEnabled && providerConfigured;
      });
      models.push(...filteredDirectModels);
    }

    // Add custom endpoint models if enabled and configured
    if (enabledProviders.custom && customEndpointModels.length > 0) {
      models.push(...customEndpointModels);
    }

    if (settings) {
      models.push(...filterOAuthModels(directAvailableModels, {
        ...settings,
        enabled_providers: enabledProviders,
      }));
    }

    // Deduplicate by model ID
    // Since direct models are added last, always set to overwrite earlier entries
    const uniqueModels = new Map();
    models.forEach(model => {
      uniqueModels.set(model.id, model);
    });

    return Array.from(uniqueModels.values()).sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  }, [
    enabledProviders,
    availableModels,
    ollamaAvailableModels,
    directAvailableModels,
    customEndpointModels,
    directProviderToggles,
    directKeys,
    settings
  ]);




  if (!settings) {
    return (
      <div className="settings-overlay" onClick={onClose}>
        <div className="settings-modal" onClick={e => e.stopPropagation()}>
          <div className="settings-header">
            <h2>Settings</h2>
            <button className="close-button" onClick={onClose}>&times;</button>
          </div>
          <div className="settings-body" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '200px' }}>
            {error ? (
              <div className="settings-error">{error}</div>
            ) : (
              <div className="settings-loading">Loading settings...</div>
            )}
          </div>
        </div>
      </div>
    );
  }





  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="settings-header">
          <div>
            <h2>Settings</h2>
            <p className="settings-header-subtitle">Changes save automatically</p>
          </div>
          <button className="close-button" onClick={onClose}>&times;</button>
        </div>

        <div className="settings-body">
          {/* Sidebar Navigation */}
          <div className="settings-sidebar">
            <button
              className={`sidebar-nav-item ${activeSection === 'general' ? 'active' : ''}`}
              onClick={() => setActiveSection('general')}
            >
              General
            </button>
            <button
              className={`sidebar-nav-item ${activeSection === 'llm_keys' ? 'active' : ''}`}
              onClick={() => setActiveSection('llm_keys')}
            >
              LLM API Keys
            </button>
            <button
              className={`sidebar-nav-item ${activeSection === 'council' ? 'active' : ''}`}
              onClick={() => setActiveSection('council')}
            >
              Council Config
            </button>
            <button
              className={`sidebar-nav-item ${activeSection === 'debate' ? 'active' : ''}`}
              onClick={() => setActiveSection('debate')}
            >
              Council Debate Config
            </button>
            <button
              className={`sidebar-nav-item ${activeSection === 'prompts' ? 'active' : ''}`}
              onClick={() => setActiveSection('prompts')}
            >
              Council System Prompts
            </button>
            <button
              className={`sidebar-nav-item ${activeSection === 'advisor_prompts' ? 'active' : ''}`}
              onClick={() => setActiveSection('advisor_prompts')}
            >
              Advisor System Prompts
            </button>
            <button
              className={`sidebar-nav-item ${activeSection === 'search' ? 'active' : ''}`}
              onClick={() => setActiveSection('search')}
            >
              Search Providers
            </button>
            <button
              className={`sidebar-nav-item ${activeSection === 'import_export' ? 'active' : ''}`}
              onClick={() => setActiveSection('import_export')}
            >
              Backup & Reset
            </button>
          </div>

          {/* Main Content Area */}
          <div className="settings-main-panel">

            {activeSection === 'general' && (
              <GeneralSettings
                dateFormat={dateFormat}
                onDateFormatChange={handleDateFormatChange}
                responseLanguage={responseLanguage}
                onResponseLanguageChange={handleResponseLanguageChange}
                responseLanguages={responseLanguages}
                settings={settings}
                relayItems={relayItems}
                relaySelected={relaySelected}
                setRelaySelected={setRelaySelected}
                relayBannerVisible={relayBannerVisible}
                relayDiscoverBusy={relayDiscoverBusy}
                relayImportBusy={relayImportBusy}
                relayImportMessage={relayImportMessage}
                relayDiscoverReason={relayDiscoverReason}
                onDiscoverRelayAi={handleDiscoverRelayAi}
                onImportRelayAi={handleImportRelayAi}
                onDismissRelayBanner={handleDismissRelayBanner}
              />
            )}

            {/* API KEYS (LLM API Keys) */}
            {activeSection === 'llm_keys' && (
              <ProviderSettings
                settings={settings}
                availableModels={availableModels}
                directAvailableModels={directAvailableModels}
                // OpenRouter
                openrouterApiKey={openrouterApiKey}
                setOpenrouterApiKey={(val) => { setOpenrouterApiKey(val); setOpenrouterTestResult(null); }}
                handleTestOpenRouter={handleTestOpenRouter}
                isTestingOpenRouter={isTestingOpenRouter}
                openrouterTestResult={openrouterTestResult}
                // Groq
                groqApiKey={groqApiKey}
                setGroqApiKey={(val) => { setGroqApiKey(val); setGroqTestResult(null); }}
                handleTestGroq={handleTestGroq}
                isTestingGroq={isTestingGroq}
                groqTestResult={groqTestResult}
                // Ollama
                ollamaBaseUrl={ollamaBaseUrl}
                ollamaAvailableModels={ollamaAvailableModels}
                setOllamaBaseUrl={(val) => { setOllamaBaseUrl(val); setOllamaTestResult(null); }}
                handleTestOllama={handleTestOllama}
                isTestingOllama={isTestingOllama}
                ollamaTestResult={ollamaTestResult}
                ollamaStatus={ollamaStatus}
                ollamaEnabled={!!enabledProviders.ollama}
                loadOllamaModels={loadOllamaModels}
                onDisconnectOllama={handleDisconnectOllama}
                // Direct
                directKeys={directKeys}
                setDirectKeys={setDirectKeys}
                handleTestDirectKey={handleTestDirectKey}
                validatingKeys={validatingKeys}
                keyValidationStatus={keyValidationStatus}
                // OpenCode
                opencodeApiKey={opencodeApiKey}
                setOpencodeApiKey={setOpencodeApiKey}
                handleTestOpencode={handleTestOpencode}
                isTestingOpencode={isTestingOpencode}
                opencodeTestResult={opencodeTestResult}
                opencodeAvailableModels={opencodeAvailableModels}
                // Custom Endpoint
                customEndpointName={customEndpointName}
                setCustomEndpointName={(val) => { setCustomEndpointName(val); setCustomEndpointTestResult(null); }}
                customEndpointUrl={customEndpointUrl}
                setCustomEndpointUrl={(val) => { setCustomEndpointUrl(val); setCustomEndpointTestResult(null); }}
                customEndpointApiKey={customEndpointApiKey}
                setCustomEndpointApiKey={(val) => { setCustomEndpointApiKey(val); setCustomEndpointTestResult(null); }}
                handleTestCustomEndpoint={handleTestCustomEndpoint}
                isTestingCustomEndpoint={isTestingCustomEndpoint}
                customEndpointTestResult={customEndpointTestResult}
                customEndpointModels={customEndpointModels}
                onClearCustomEndpoint={handleClearCustomEndpoint}
                onDisconnectOpenRouter={handleDisconnectOpenRouter}
                onDisconnectGroq={handleDisconnectGroq}
                onDisconnectDirectKey={handleDisconnectDirectKey}
                onDisconnectOpencode={handleDisconnectOpencode}
                onOAuthSettingsChange={handleOAuthSettingsChange}
                onOAuthModelsRefresh={loadModels}
                currentCredentialStorage={currentCredentialStorage}
                credentialStorageBusy={credentialStorageBusy}
                onCredentialStorageChange={handleCredentialStorageChange}
                onNavigateToGeneral={() => setActiveSection('general')}
              />
            )}

            {/* COUNCIL CONFIGURATION */}
            {activeSection === 'council' && (
              <CouncilConfig
                settings={settings}
                ollamaStatus={ollamaStatus}
                enabledProviders={enabledProviders}
                setEnabledProviders={setEnabledProviders}
                directProviderToggles={directProviderToggles}
                setDirectProviderToggles={setDirectProviderToggles}
                councilModels={councilModels}
                chairmanModel={chairmanModel}
                councilTemperature={councilTemperature}
                setCouncilTemperature={setCouncilTemperature}
                chairmanTemperature={chairmanTemperature}
                setChairmanTemperature={setChairmanTemperature}
                stage2Temperature={stage2Temperature}
                setStage2Temperature={setStage2Temperature}
                customEndpointName={customEndpointName}
                customEndpointUrl={customEndpointUrl}
              />
            )}

            {/* DEBATE CONFIGURATION */}
            {activeSection === 'debate' && (
              <DebateSettings
                critiqueMode={critiqueMode}
                setCritiqueMode={setCritiqueMode}
                debateRounds={debateRounds}
                setDebateRounds={setDebateRounds}
                autoConverge={autoConverge}
                setAutoConverge={setAutoConverge}
                convergenceThreshold={convergenceThreshold}
                setConvergenceThreshold={setConvergenceThreshold}
                executionMode={settings?.execution_mode || 'full'}
              />
            )}

            {/* SYSTEM PROMPTS */}
            {activeSection === 'prompts' && (
              <PromptSettings
                variant="council"
                prompts={prompts}
                handlePromptChange={handlePromptChange}
                handleResetPrompt={handleResetPrompt}
                activePromptTab={activePromptTab}
                setActivePromptTab={setActivePromptTab}
              />
            )}

            {/* ADVISOR SYSTEM PROMPTS */}
            {activeSection === 'advisor_prompts' && (
              <PromptSettings
                variant="advisor"
                prompts={prompts}
                handlePromptChange={handlePromptChange}
                handleResetPrompt={handleResetPrompt}
                activePromptTab={activeAdvisorPromptTab}
                setActivePromptTab={setActiveAdvisorPromptTab}
              />
            )}

            {/* SEARCH PROVIDERS (New Section) */}
            {activeSection === 'search' && (
              <SearchSettings
                settings={settings}
                selectedSearchProvider={selectedSearchProvider}
                setSelectedSearchProvider={setSelectedSearchProvider}
                // Serper (Google)
                serperApiKey={serperApiKey}
                setSerperApiKey={setSerperApiKey}
                handleTestSerper={handleTestSerper}
                isTestingSerper={isTestingSerper}
                serperTestResult={serperTestResult}
                setSerperTestResult={setSerperTestResult}
                // Tavily
                tavilyApiKey={tavilyApiKey}
                setTavilyApiKey={setTavilyApiKey}
                handleTestTavily={handleTestTavily}
                isTestingTavily={isTestingTavily}
                tavilyTestResult={tavilyTestResult}
                setTavilyTestResult={setTavilyTestResult}
                // Brave
                braveApiKey={braveApiKey}
                setBraveApiKey={setBraveApiKey}
                handleTestBrave={handleTestBrave}
                isTestingBrave={isTestingBrave}
                braveTestResult={braveTestResult}
                setBraveTestResult={setBraveTestResult}
                // TinyFish
                tinyfishApiKey={tinyfishApiKey}
                setTinyfishApiKey={setTinyfishApiKey}
                handleTestTinyfish={handleTestTinyfish}
                isTestingTinyfish={isTestingTinyfish}
                tinyfishTestResult={tinyfishTestResult}
                setTinyfishTestResult={setTinyfishTestResult}
                // Other Settings
                fullContentResults={fullContentResults}
                setFullContentResults={setFullContentResults}
                searchKeywordExtraction={searchKeywordExtraction}
                setSearchKeywordExtraction={setSearchKeywordExtraction}
                searchResultCount={searchResultCount}
                setSearchResultCount={setSearchResultCount}
                searchHybridMode={searchHybridMode}
                setSearchHybridMode={setSearchHybridMode}
                onDisconnectSearchKey={handleDisconnectSearchKey}
              />
            )}

            {/* IMPORT & EXPORT (New Section) */}
            {activeSection === 'import_export' && (
              <section className="settings-section">
                <h3>Backup & Reset</h3>

                <div className="subsection">
                  <h4>Import / Export</h4>
                  <p className="section-description">
                    Save or restore your council configuration (models, prompts, settings).
                    <br /><em>Note: API keys are NOT exported for security.</em>
                  </p>
                </div>

                <div className="subsection">
                  <div className="council-actions" style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
                    <input
                      type="file"
                      id="import-council"
                      style={{ display: 'none' }}
                      accept=".json"
                      onChange={handleImportCouncil}
                    />
                    <button
                      className="action-btn"
                      onClick={() => document.getElementById('import-council').click()}
                      title="Import Configuration"
                    >
                      Import Config
                    </button>
                    <button
                      className="action-btn"
                      onClick={handleExportCouncil}
                      title="Export Configuration"
                    >
                      Export Config
                    </button>
                  </div>
                </div>

                <div className="subsection" style={{ marginTop: '32px', paddingTop: '20px', borderTop: '1px solid rgba(255, 255, 255, 0.1)' }}>
                  <h4 style={{ color: '#f87171' }}>Danger Zone</h4>
                  <p className="section-description">
                    Disconnect every LLM API key, search key, and subscription OAuth login.
                    Council models, prompts, and other settings are left alone. Env-provided keys
                    are ignored until you save a new key.
                  </p>
                  <button
                    className="reset-button"
                    type="button"
                    onClick={() => setShowDisconnectAllConfirm(true)}
                    style={{ marginTop: '10px' }}
                    disabled={disconnectAllBusy}
                  >
                    {disconnectAllBusy ? 'Disconnecting…' : 'Disconnect All Providers'}
                  </button>

                  <p className="section-description" style={{ marginTop: '24px' }}>
                    Reset all settings to their default values. This will clear your council selection and custom prompts.
                    API keys will be preserved.
                  </p>
                  <button
                    className="reset-button"
                    type="button"
                    onClick={handleResetToDefaults}
                    style={{ marginTop: '10px' }}
                  >
                    Reset to Defaults
                  </button>
                </div>
              </section>
            )}

          </div>
        </div>

        <div className="settings-footer">
          {error && <div className="settings-error">{error}</div>}
          {success && (
            <div className="settings-success">
              {successMessage
                || (activeSection === 'general' && relayImportMessage?.tone === 'success'
                  ? relayImportMessage.text
                  : activeSection === 'llm_keys' && !settings?.openrouter_api_key_set && !ollamaStatus?.connected
                    ? 'Defaults loaded. Please configure an API Key.'
                    : 'Settings saved!')}
            </div>
          )}

          <div className="footer-actions">
            <button className="cancel-button" onClick={onClose}>
              Close
            </button>
            {isSaving && <span className="settings-autosave-status">Saving…</span>}
            {!isSaving && success && (
              <span className="settings-autosave-status saved">Saved</span>
            )}
          </div>
        </div>
      </div>

      {
        credentialStorageTarget && (
          <div className="settings-overlay confirmation-overlay" onClick={() => !credentialStorageBusy && setCredentialStorageTarget(null)}>
            <div className="settings-modal confirmation-modal" onClick={e => e.stopPropagation()}>
              <div className="settings-header">
                <h2>Move credentials?</h2>
              </div>
              <div className="settings-content confirmation-content" style={{ padding: '20px 24px' }}>
                <p style={{ marginBottom: '16px' }}>
                  Move {countStoredCredentials(settings)} stored credential{countStoredCredentials(settings) === 1 ? '' : 's'} from{' '}
                  <strong>{currentCredentialStorage === 'file' ? 'encrypted file' : 'OS keystore'}</strong> to{' '}
                  <strong>{credentialStorageTarget === 'file' ? 'encrypted file' : 'OS keystore'}</strong>?
                </p>
                <p className="api-key-hint">Existing credentials are removed from the old location after a successful copy.</p>
              </div>
              <div className="settings-footer">
                <div className="footer-actions" style={{ width: '100%', justifyContent: 'flex-end' }}>
                  <button className="cancel-button" onClick={() => setCredentialStorageTarget(null)} disabled={credentialStorageBusy}>
                    Cancel
                  </button>
                  <button className="action-btn" onClick={confirmCredentialStorageMigration} disabled={credentialStorageBusy}>
                    {credentialStorageBusy ? 'Moving…' : 'Move credentials'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )
      }

      {
        showDisconnectAllConfirm && (
          <div className="settings-overlay confirmation-overlay" onClick={() => !disconnectAllBusy && setShowDisconnectAllConfirm(false)}>
            <div className="settings-modal confirmation-modal" onClick={e => e.stopPropagation()}>
              <div className="settings-header">
                <h2>Disconnect all providers?</h2>
              </div>
              <div className="settings-content confirmation-content" style={{ padding: '20px 24px' }}>
                <p style={{ marginBottom: '16px' }}>
                  This removes every stored API key and OAuth login from the credential store.
                </p>
                <div className="confirmation-details" style={{ padding: '16px 20px' }}>
                  <p><strong>This will clear:</strong></p>
                  <ul style={{ margin: '12px 0', lineHeight: '1.8' }}>
                    <li>OpenRouter, Groq, OpenCode, and direct provider keys</li>
                    <li>Search provider keys (Tavily, Brave, Serper, TinyFish)</li>
                    <li>Subscription OAuth (xAI, ChatGPT, Copilot)</li>
                    <li>Custom endpoint URL / name</li>
                    <li>Provider toggles → all disabled</li>
                  </ul>
                  <p className="confirmation-safe" style={{ marginTop: '14px' }}>
                    ✓ Council models, prompts, and other settings are kept
                  </p>
                </div>
              </div>
              <div className="settings-footer">
                <div className="footer-actions" style={{ width: '100%', justifyContent: 'flex-end' }}>
                  <button
                    className="cancel-button"
                    onClick={() => setShowDisconnectAllConfirm(false)}
                    disabled={disconnectAllBusy}
                  >
                    Cancel
                  </button>
                  <button
                    className="reset-button"
                    onClick={confirmDisconnectAllProviders}
                    disabled={disconnectAllBusy}
                  >
                    {disconnectAllBusy ? 'Disconnecting…' : 'Disconnect All'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )
      }

      {
        showResetConfirm && (
          <div className="settings-overlay confirmation-overlay" onClick={() => setShowResetConfirm(false)}>
            <div className="settings-modal confirmation-modal" onClick={e => e.stopPropagation()}>
              <div className="settings-header">
                <h2>Confirm Reset</h2>
              </div>
              <div className="settings-content confirmation-content" style={{ padding: '20px 24px' }}>
                <p style={{ marginBottom: '16px' }}>Are you sure you want to reset to defaults?</p>
                <div className="confirmation-details" style={{ padding: '16px 20px' }}>
                  <p><strong>This will reset:</strong></p>
                  <ul style={{ margin: '12px 0', lineHeight: '1.8' }}>
                    <li>Provider toggles → All disabled</li>
                    <li>Model selections → Cleared</li>
                    <li>Council size → Reset to 2 members</li>
                    <li>Temperatures → Defaults (0.5 / 0.4 / 0.3)</li>
                    <li>System prompts → Defaults</li>
                    <li>Search provider → DuckDuckGo</li>
                    <li>Jina fetch count → 3</li>
                    <li>Ollama URL → localhost:11434</li>
                  </ul>
                  <p className="confirmation-safe" style={{ marginTop: '14px' }}>✓ API keys will be PRESERVED</p>
                </div>
              </div>
              <div className="settings-footer">
                <div className="footer-actions" style={{ width: '100%', justifyContent: 'flex-end' }}>
                  <button className="cancel-button" onClick={() => setShowResetConfirm(false)}>Cancel</button>
                  <button className="reset-button" onClick={confirmResetToDefaults}>Confirm Reset</button>
                </div>
              </div>
            </div>
          </div>
        )
      }
    </div >
  );
}

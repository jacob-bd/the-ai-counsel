import { Suspense, lazy, useState, useEffect, useRef, useCallback, Component } from 'react';
import Sidebar from './components/Sidebar';
import { api, DEFAULT_EXECUTION_MODE, buildAvailableSearchProviders } from './api';
import './App.css';
import './components/StageCopyButtons.css';
import './ModeToggle.css';

const ChatInterface = lazy(() => import('./components/ChatInterface'));
const Settings = lazy(() => import('./components/Settings'));
const LandingPage = lazy(() => import('./components/LandingPage'));

/** Stop any stage timers still missing an end timestamp. */
function finalizeTimers(timers = {}) {
  const now = Date.now();
  const next = { ...timers };
  if (next.stage1Start && !next.stage1End) next.stage1End = now;
  if (next.stage2Start && !next.stage2End) next.stage2End = now;
  if (next.stage3Start && !next.stage3End) next.stage3End = now;
  if (next.stage4Start && !next.stage4End) next.stage4End = now;
  return next;
}

const isDefaultConversationTitle = (title) =>
  !title || title === 'New Conversation' || title === 'Untitled Conversation';

const deriveConversationTitle = (content) => {
  if (!content || typeof content !== 'string') return 'Untitled Conversation';

  let title = content.trim().replace(/\s+/g, ' ');
  if (!title) return 'Untitled Conversation';

  title = title.replace(/^["']+|["']+$/g, '');

  if (title.length > 50) {
    title = `${title.substring(0, 47)}...`;
  }
  return title;
};

const IDLE_LOADING = {
  search: false,
  stage1: false,
  stage2: false,
  stage3: false,
  stage4: false,
};

function AppLoadingFallback() {
  return (
    <div className="app-loading" role="status" aria-live="polite">
      Loading...
    </div>
  );
}

class AppErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="app-loading" role="alert">
          Failed to load. Please refresh the page.
        </div>
      );
    }
    return this.props.children;
  }
}

const getConversationMode = (conversation) => (
  conversation?.mode === 'advisors' ? 'advisors' : 'council'
);

const isAdvisorMessage = (message) => (
  message?.mode === 'advisors' || message?.type === 'advisor_debate'
);

const normalizeAdvisorRound = (roundData = {}, index = 0) => {
  const roundNumber = roundData.round || roundData.round_number || index + 1;
  return {
    ...roundData,
    round: roundNumber,
    round_number: roundNumber,
    responses: Array.isArray(roundData.responses) ? roundData.responses : [],
    complete: Boolean(roundData.complete || roundData.consensus_reached),
  };
};

const buildAdvisorProgressMessage = (progress, existing = {}) => {
  const metadata = {
    ...(existing.metadata || {}),
    ...(progress.metadata || {}),
  };

  return {
    role: 'assistant',
    type: 'advisor_debate',
    mode: 'advisors',
    isRunning: true,
    phase: progress.stage || existing.phase || 'initializing',
    currentRound: progress.current_round || existing.currentRound || 0,
    maxRounds: progress.max_rounds || existing.maxRounds || metadata.max_rounds || 3,
    question: progress.question || existing.question || '',
    webSearch: progress.search_provider || progress.web_search || existing.webSearch || null,
    personas: progress.personas || existing.personas || [],
    rounds: (progress.rounds || existing.rounds || []).map(normalizeAdvisorRound),
    verdict: progress.verdict || existing.verdict || null,
    tiebreaker: progress.tiebreaker || existing.tiebreaker || null,
    consensusReached: progress.consensus_reached ?? existing.consensusReached ?? false,
    error: progress.error || existing.error || null,
    metadata,
    externalRun: true,
  };
};

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [settingsInitialSection, setSettingsInitialSection] = useState('llm_keys');
  const [ollamaStatus, setOllamaStatus] = useState({
    connected: false,
    lastConnected: null,
    testing: false
  });
  const [councilConfigured, setCouncilConfigured] = useState(true); // Assume configured until checked
  const [councilModels, setCouncilModels] = useState([]);
  const [chairmanModel, setChairmanModel] = useState(null);
  const [searchProvider, setSearchProvider] = useState('duckduckgo');
  const [availableSearchProviders, setAvailableSearchProviders] = useState([{ id: 'duckduckgo', name: 'DuckDuckGo' }]);
  const [executionMode, setExecutionMode] = useState(DEFAULT_EXECUTION_MODE);
  const [critiqueMode, setCritiqueMode] = useState('freeform');
  const [debateRounds, setDebateRounds] = useState(1);
  const [autoConverge, setAutoConverge] = useState(true);
  const [convergenceThreshold, setConvergenceThreshold] = useState(2);
  const [dateFormat, setDateFormat] = useState('auto');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [appMode, setAppMode] = useState(null); // null shows landing page
  const abortControllerRef = useRef(null);
  const advisorAbortControllerRef = useRef(null);
  const progressPollRef = useRef(null);
  const requestIdRef = useRef(0);
  const isInitialMount = useRef(true);
  const conversationVersionRef = useRef(0);
  const skipLoadForIdRef = useRef(null);

  const computeCouncilConfigured = useCallback((models) => {
    const members = (models || []).filter((m) => m && m.trim());
    return members.length >= 1;
  }, []);

  const handleCouncilChange = useCallback(async ({ councilModels: nextModels, chairmanModel: nextChairman }) => {
    const filtered = (nextModels || []).filter((m) => m && m.trim());
    const chairman = nextChairman || '';
    setCouncilModels(filtered);
    setChairmanModel(chairman);
    setCouncilConfigured(computeCouncilConfigured(filtered));
    try {
      await api.updateSettings({
        council_models: filtered,
        chairman_model: chairman,
      });
    } catch (err) {
      console.error('Failed to save council lineup:', err);
    }
  }, [computeCouncilConfigured]);

  useEffect(() => {
    setCouncilConfigured(computeCouncilConfigured(councilModels));
  }, [councilModels, computeCouncilConfigured]);

  useEffect(() => {
    if (executionMode === 'full' && (!chairmanModel || !chairmanModel.trim())) {
      const memberCount = (councilModels || []).filter(m => m && m.trim()).length;
      setExecutionMode(memberCount <= 1 ? 'chat_only' : 'chat_ranking');
    }
  }, [chairmanModel, executionMode, councilModels]);

  // Check initial configuration on mount
  useEffect(() => {
    checkInitialSetup();
  }, []);

  const checkInitialSetup = async () => {
    try {
      // 1. Get Settings to check for API keys
      const settings = await api.getSettings();

      // Load execution mode preference
      setExecutionMode(settings.execution_mode || DEFAULT_EXECUTION_MODE);
      setSearchProvider(settings.search_provider || 'duckduckgo');

      setCritiqueMode(settings.critique_mode || 'freeform');
      setDebateRounds(settings.debate_rounds || 1);
      setAutoConverge(settings.auto_converge !== undefined ? settings.auto_converge : true);
      setConvergenceThreshold(settings.convergence_threshold || 2);
      setDateFormat(settings.date_format || 'auto');

      setAvailableSearchProviders(buildAvailableSearchProviders(settings));

      const hasApiKey = settings.openrouter_api_key_set ||
        settings.groq_api_key_set ||
        settings.openai_api_key_set ||
        settings.anthropic_api_key_set ||
        settings.google_api_key_set ||
        settings.mistral_api_key_set ||
        settings.deepseek_api_key_set;

      // 2. Test Ollama Connection
      // We do this regardless to update the status indicator
      const ollamaUrl = settings.ollama_base_url || 'http://localhost:11434';
      setOllamaStatus(prev => ({ ...prev, testing: true }));

      let isOllamaConnected = false;
      try {
        const result = await api.testOllamaConnection(ollamaUrl);
        isOllamaConnected = result.success;

        if (result.success) {
          setOllamaStatus({
            connected: true,
            lastConnected: new Date().toLocaleString(),
            testing: false
          });
        } else {
          setOllamaStatus({ connected: false, lastConnected: null, testing: false });
        }
      } catch (err) {
        console.error('Ollama initial test failed:', err);
        setOllamaStatus({ connected: false, lastConnected: null, testing: false });
      }

      // 3. Check if council is configured (has models selected)
      const models = (settings.council_models || []).filter((m) => m && m.trim());
      const chairman = settings.chairman_model || '';

      setCouncilModels(models);
      setChairmanModel(chairman);

      setCouncilConfigured(computeCouncilConfigured(models));

      // 4. If no providers are configured, open settings
      if (!hasApiKey && !isOllamaConnected) {
        setShowSettings(true);
      }

    } catch (error) {
      console.error('Failed to check initial setup:', error);
    }
  };

  // Re-check council configuration when settings close
  const handleSettingsClose = async () => {
    setShowSettings(false);
    try {
      const settings = await api.getSettings();
      const models = (settings.council_models || []).filter((m) => m && m.trim());
      const chairman = settings.chairman_model || '';

      setCouncilModels(models);
      setChairmanModel(chairman);
      setSearchProvider(settings.search_provider || 'duckduckgo');
      setAvailableSearchProviders(buildAvailableSearchProviders(settings));
      setExecutionMode(settings.execution_mode || DEFAULT_EXECUTION_MODE);

      setCritiqueMode(settings.critique_mode || 'freeform');
      setDebateRounds(settings.debate_rounds || 1);
      setAutoConverge(settings.auto_converge !== undefined ? settings.auto_converge : true);
      setConvergenceThreshold(settings.convergence_threshold || 2);
      setDateFormat(settings.date_format || 'auto');

      setCouncilConfigured(computeCouncilConfigured(models));
    } catch (error) {
      console.error('Error after closing settings:', error);
    }
  };

  const handleOpenSettings = (section = 'council') => {
    setSettingsInitialSection(section || 'council');
    setShowSettings(true);
  };

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
  }, []);

  // Periodically refresh the conversation list so MCP/API-created conversations
  // appear in the sidebar without requiring a page reload.
  useEffect(() => {
    const tick = () => { if (document.visibilityState === 'visible') loadConversations(); };
    const interval = setInterval(tick, 30000);
    document.addEventListener('visibilitychange', tick);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', tick);
    };
  }, []);

  // Auto-save execution mode preference when changed
  useEffect(() => {
    // Skip saving on initial mount
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }

    const saveExecutionMode = async () => {
      try {
        await api.updateSettings({ execution_mode: executionMode });
      } catch (error) {
        console.error('Failed to save execution mode:', error);
      }
    };

    saveExecutionMode();
  }, [executionMode]);

  const testOllamaConnection = async (customUrl = null) => {
    try {
      setOllamaStatus(prev => ({ ...prev, testing: true }));

      // Use custom URL if provided, otherwise get from settings
      let urlToTest = customUrl;
      if (!urlToTest) {
        const settings = await api.getSettings();
        urlToTest = settings.ollama_base_url;
      }

      if (!urlToTest) {
        setOllamaStatus({ connected: false, lastConnected: null, testing: false });
        return;
      }

      const result = await api.testOllamaConnection(urlToTest);

      if (result.success) {
        setOllamaStatus({
          connected: true,
          lastConnected: new Date().toLocaleString(),
          testing: false
        });
      } else {
        setOllamaStatus({ connected: false, lastConnected: null, testing: false });
      }
    } catch (error) {
      console.error('Ollama connection test failed:', error);
      setOllamaStatus({ connected: false, lastConnected: null, testing: false });
    }
  };

  // Load conversation details when selected, then check for active runs
  useEffect(() => {
    if (currentConversationId && currentConversationId !== 'draft') {
      if (skipLoadForIdRef.current === currentConversationId) {
        skipLoadForIdRef.current = null;
        return;
      }
      // Capture the current version — if an optimistic update bumps it
      // before the fetch resolves, the stale response is discarded.
      // This is StrictMode-safe: double-invocation just fires two loads,
      // both of which will be stale if a debate was started.
      const versionAtStart = conversationVersionRef.current;
      const convId = currentConversationId;
      loadConversation(convId, versionAtStart).then(() => {
        checkForActiveRun(convId);
      });
    }
  }, [currentConversationId]);

  const loadConversations = async (retryCount = 0) => {
    try {
      const convs = await api.listConversations();
      setConversations((prev) =>
        convs.map((conv) => {
          const local = prev.find((item) => item.id === conv.id);

          const updated = {
            ...conv,
            mode: getConversationMode(conv),
          };

          if (
            local &&
            isDefaultConversationTitle(conv.title) &&
            !isDefaultConversationTitle(local.title)
          ) {
            updated.title = local.title;
          }

          return updated;
        })
      );
    } catch (error) {
      console.error('Failed to load conversations:', error);
      // Retry up to 3 times with increasing delays (1s, 2s, 3s)
      if (retryCount < 3) {
        setTimeout(() => loadConversations(retryCount + 1), (retryCount + 1) * 1000);
      }
    }
  };

  const loadConversation = async (id, expectedVersion) => {
    try {
      const conv = await api.getConversation(id);
      // Only apply if no newer optimistic update has occurred since we started
      if (conversationVersionRef.current === expectedVersion) {
        const normalized = { ...conv, mode: getConversationMode(conv) };
        setCurrentConversation(normalized);
        setAppMode(getConversationMode(normalized));
      }
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };

  const stopProgressPolling = () => {
    if (progressPollRef.current) {
      clearInterval(progressPollRef.current);
      progressPollRef.current = null;
    }
  };

  const abortAllStreams = () => {
    stopProgressPolling();
    if (advisorAbortControllerRef.current) {
      advisorAbortControllerRef.current.abort();
      advisorAbortControllerRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  };

  const loadingFlagsFromStage = (stage) => ({
    search: stage === 'search',
    stage1: stage === 'stage1' || stage === 'initializing',
    stage2: stage === 'stage2',
    stage3: stage === 'stage3',
    stage4: stage === 'stage4',
  });

  const applyAdvisorProgress = (conversationId, progress) => {
    setAppMode('advisors');
    setIsLoading(true);
    setCurrentConversation(prev => {
      if (!prev || prev.id !== conversationId) return prev;
      const messages = [...(prev.messages || [])];
      const lastIdx = messages.length - 1;
      const lastMsg = messages[lastIdx];
      const liveMessage = buildAdvisorProgressMessage(progress, isAdvisorMessage(lastMsg) ? lastMsg : {});

      if (isAdvisorMessage(lastMsg)) {
        messages[lastIdx] = liveMessage;
      } else {
        if (lastMsg?.role !== 'user' && progress.question) {
          messages.push({ role: 'user', content: progress.question });
        }
        messages.push(liveMessage);
      }

      return { ...prev, mode: 'advisors', messages };
    });
  };

  const checkForActiveRun = async (conversationId) => {
    stopProgressPolling();
    try {
      const progress = await api.getConversationProgress(conversationId);
      if (!progress.active) return;

      if (progress.mode === 'advisors') {
        applyAdvisorProgress(conversationId, progress);
      } else {
        setAppMode('council');
        setIsLoading(true);

        setCurrentConversation(prev => {
          if (!prev || prev.id !== conversationId) return prev;
          const messages = [...prev.messages];
          const lastMsg = messages[messages.length - 1];
          if (lastMsg?.role === 'user') {
            messages.push({
              role: 'assistant',
              stage1: progress.stage1 || null,
              stage2: progress.stage2 || null,
              stage3: progress.stage3 || null,
              loading: loadingFlagsFromStage(progress.stage),
              progress: progress.progress || {},
              metadata: {
                execution_mode: progress.execution_mode,
                stage4: progress.stage4 || null,
              },
              externalRun: true,
            });
          }
          return { ...prev, mode: 'council', messages };
        });
      }

      let inFlight = false;
      progressPollRef.current = setInterval(async () => {
        if (inFlight) return;
        inFlight = true;
        try {
          const p = await api.getConversationProgress(conversationId);
          if (!p.active) {
            stopProgressPolling();
            setIsLoading(false);
            const versionAtReload = conversationVersionRef.current;
            await loadConversation(conversationId, versionAtReload);
            loadConversations();
            return;
          }
          if (p.mode === 'advisors') {
            applyAdvisorProgress(conversationId, p);
          } else {
            setCurrentConversation(prev => {
              if (!prev || prev.id !== conversationId) return prev;
              const messages = [...prev.messages];
              const lastIdx = messages.length - 1;
              if (lastIdx >= 0 && messages[lastIdx]?.externalRun) {
                messages[lastIdx] = {
                  ...messages[lastIdx],
                  stage1: p.stage1 || messages[lastIdx].stage1,
                  stage2: p.stage2 || messages[lastIdx].stage2,
                  stage3: p.stage3 || messages[lastIdx].stage3,
                  loading: loadingFlagsFromStage(p.stage),
                  progress: p.progress || messages[lastIdx].progress,
                  metadata: {
                    ...messages[lastIdx].metadata,
                    stage4: p.stage4 || messages[lastIdx].metadata?.stage4,
                  }
                };
              }
              return { ...prev, mode: 'council', messages };
            });
          }
        } catch {
          // Poll errors are expected during network blips
        } finally {
          inFlight = false;
        }
      }, 3000);
    } catch {
      // Progress endpoint unavailable — no-op
    }
  };

  const handleNewConversation = async () => {
    abortAllStreams();
    setIsLoading(false);
    setAppMode('council');

    // Reset current states to indicate we are in a fresh Client-Side Draft
    setCurrentConversationId('draft');
    setCurrentConversation({
      id: 'draft',
      mode: 'council',
      title: 'New Conversation',
      messages: []
    });
  };

  const handleSelectConversation = (id) => {
    stopProgressPolling();
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
    setCurrentConversationId(id);
    // Auto-switch mode based on conversation mode
    const conv = conversations.find(c => c.id === id);
    if (getConversationMode(conv) === 'advisors') {
      setAppMode('advisors');
    } else {
      setAppMode('council');
    }
  };

  const handleDeleteConversation = async (id) => {
    try {
      await api.deleteConversation(id);
      // Remove from local state
      setConversations(conversations.filter(c => c.id !== id));
      // If we deleted the current conversation, clear it
      if (id === currentConversationId) {
        setCurrentConversationId(null);
        setCurrentConversation(null);
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

  const handleAbort = () => {
    stopProgressPolling();
    if (advisorAbortControllerRef.current) {
      advisorAbortControllerRef.current.abort();
      setIsLoading(false);
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      // Don't set to null here - let the request handler clean up
      // This prevents race conditions with rapid clicks
      setIsLoading(false);
    }
  };

  const handleStartDebate = async (options) => {
    stopProgressPolling();
    const currentRequestId = ++requestIdRef.current;

    setIsLoading(true);
    let activeConversationId = currentConversationId;

    try {
      // Lazily create the conversation if it is a Client-Side Draft
      if (activeConversationId === 'draft' || !activeConversationId) {
        try {
          const newConv = await api.createConversation({ mode: 'advisors' });
          activeConversationId = newConv.id;
          
          // Pre-populate index states so it appears immediately in the sidebar list
          setConversations((prev) => [
            { id: newConv.id, created_at: newConv.created_at, message_count: 0, mode: 'advisors', title: 'New Conversation' },
            ...prev,
          ]);
          
          // Update draft references safely
          conversationVersionRef.current++;
          skipLoadForIdRef.current = newConv.id;
          setCurrentConversationId(newConv.id);
        } catch (createErr) {
          console.error('Lazy creation of conversation failed:', createErr);
          setIsLoading(false);
          return;
        }
      }

      setAppMode('advisors');

      const userMessage = { role: 'user', content: options.question };
      const debateMessage = {
        role: 'assistant',
        type: 'advisor_debate',
        mode: 'advisors',
        isRunning: true,
        currentRound: 0,
        maxRounds: options.maxRounds || 3,
        question: options.question,
        webSearch: options.searchProvider || null,
        personas: [],
        rounds: [],
        verdict: null,
        tiebreaker: null,
        consensusReached: false,
        error: null,
      };

      setCurrentConversation({
        id: activeConversationId,
        mode: 'advisors',
        title: 'New Conversation',
        messages: [userMessage, debateMessage],
      });

      advisorAbortControllerRef.current = new AbortController();

      const updateAdvisorMessage = (updater) => {
        setCurrentConversation((prev) => {
          if (!prev || prev.id !== activeConversationId) return prev;
          const messages = [...(prev.messages || [])];
          const lastIdx = messages.length - 1;
          const lastMsg = messages[lastIdx];
          if (!isAdvisorMessage(lastMsg)) return prev;
          messages[lastIdx] = updater(lastMsg);
          return { ...prev, mode: 'advisors', messages };
        });
      };

      await api.sendDebateStream(
        activeConversationId,
        options,
        (eventType, event) => {
          switch (eventType) {
            case 'advisor_debate_start':
              updateAdvisorMessage((lastMsg) => ({
                ...lastMsg,
                personas: event.data?.personas || [],
                maxRounds: event.data?.max_rounds || lastMsg.maxRounds,
              }));
              break;

            case 'advisor_round_start':
              updateAdvisorMessage((lastMsg) => {
                const roundNumber = event.round || event.data?.round_number || lastMsg.currentRound || 1;
                const rounds = [...(lastMsg.rounds || [])];
                const roundIndex = roundNumber - 1;
                if (!rounds[roundIndex]) {
                  rounds[roundIndex] = { round: roundNumber, round_number: roundNumber, responses: [], complete: false };
                }
                rounds[roundIndex] = {
                  ...rounds[roundIndex],
                  order: event.data?.order || rounds[roundIndex].order || [],
                };
                return {
                  ...lastMsg,
                  phase: 'round',
                  currentRound: roundNumber,
                  rounds,
                };
              });
              break;

            case 'advisor_response':
              updateAdvisorMessage((lastMsg) => {
                const rounds = [...(lastMsg.rounds || [])];
                const roundIndex = (event.round || 1) - 1;
                if (!rounds[roundIndex]) {
                  rounds[roundIndex] = { round: event.round, responses: [], complete: false };
                }
                rounds[roundIndex] = {
                  ...rounds[roundIndex],
                  responses: [...rounds[roundIndex].responses, event.data],
                };
                return { ...lastMsg, phase: 'round', rounds };
              });
              break;

            case 'advisor_round_complete':
              updateAdvisorMessage((lastMsg) => {
                const rounds = [...(lastMsg.rounds || [])];
                const roundNumber = event.round || event.data?.round_number || 1;
                const roundIndex = roundNumber - 1;
                if (!rounds[roundIndex]) {
                  rounds[roundIndex] = { round: roundNumber, responses: [], complete: false };
                }
                rounds[roundIndex] = {
                  ...rounds[roundIndex],
                  responses: event.data?.responses || rounds[roundIndex].responses,
                  complete: true,
                  consensusReached: event.data?.consensus_reached || false,
                  averageConsensusScore: event.data?.average_consensus_score,
                };
                return {
                  ...lastMsg,
                  phase: 'round_complete',
                  rounds,
                  consensusReached: event.data?.consensus_reached || false,
                };
              });
              break;

            case 'advisor_tiebreaker_start':
              updateAdvisorMessage((lastMsg) => ({
                ...lastMsg,
                phase: 'tiebreaker',
              }));
              break;

            case 'advisor_verdict':
              updateAdvisorMessage((lastMsg) => ({
                ...lastMsg,
                phase: 'verdict',
                verdict: event.data || event,
              }));
              break;

            case 'advisor_tiebreaker':
              updateAdvisorMessage((lastMsg) => ({
                ...lastMsg,
                phase: 'tiebreaker',
                tiebreaker: event.data || event,
              }));
              break;

            case 'advisor_verdict_start':
              updateAdvisorMessage((lastMsg) => ({
                ...lastMsg,
                phase: 'verdict',
              }));
              break;

            case 'advisor_complete':
              updateAdvisorMessage((lastMsg) => ({
                  ...lastMsg,
                  isRunning: false,
                  phase: 'complete',
                  personas: event.data?.personas || lastMsg.personas,
                  rounds: (event.data?.rounds || lastMsg.rounds || []).map(normalizeAdvisorRound),
                  verdict: event.data?.verdict || lastMsg.verdict,
                  tiebreaker: event.data?.tiebreaker || lastMsg.tiebreaker,
                  consensusReached: event.data?.consensus_reached ?? lastMsg.consensusReached,
                  metadata: {
                    ...lastMsg.metadata,
                    cost_report: event.data?.cost_report,
                  },
                }));
              setIsLoading(false);
              break;

            case 'advisor_error':
              updateAdvisorMessage((lastMsg) => ({
                  ...lastMsg,
                  isRunning: false,
                  phase: 'error',
                  error: event.message || 'Advisor debate failed',
                }));
              setIsLoading(false);
              break;

            case 'title_complete':
              loadConversations();
              setCurrentConversation((prev) => {
                if (!prev || prev.id !== activeConversationId) return prev;
                return { ...prev, title: event.data?.title || prev.title };
              });
              break;

            default:
              break;
          }
        },
        advisorAbortControllerRef.current.signal
      );
    } catch (error) {
      if (error.name === 'AbortError') {
        setCurrentConversation((prev) => {
          if (!prev || prev.id !== activeConversationId || prev.messages.length < 2) return prev;
          const messages = [...prev.messages];
          const lastMsg = messages[messages.length - 1];
          if (lastMsg.type === 'advisor_debate') {
            messages[messages.length - 1] = { ...lastMsg, isRunning: false, aborted: true };
          }
          return { ...prev, messages };
        });
        setIsLoading(false);
        return;
      }
      console.error('Failed to start debate:', error);
      // Surface the error to the user instead of showing a blank screen
      setCurrentConversation((prev) => {
        if (!prev?.messages?.length || prev.id !== activeConversationId) return prev;
        const messages = [...prev.messages];
        const lastMsg = messages[messages.length - 1];
        if (lastMsg.type === 'advisor_debate') {
          messages[messages.length - 1] = {
            ...lastMsg,
            isRunning: false,
            error: error.message || 'Failed to start debate. Please try again.',
          };
        }
        return { ...prev, messages };
      });
      setIsLoading(false);
    } finally {
      advisorAbortControllerRef.current = null;
      loadConversations();
    }
  };

  const handleSendMessage = async (content, searchProvider) => {
    if (!currentConversationId) return;

    let effectiveMode = executionMode;
    if (effectiveMode === 'full' && (!chairmanModel || !chairmanModel.trim())) {
      const memberCount = (councilModels || []).filter(m => m && m.trim()).length;
      effectiveMode = memberCount <= 1 ? 'chat_only' : 'chat_ranking';
    }

    stopProgressPolling();
    const currentRequestId = ++requestIdRef.current;

    // Create new AbortController for this request
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    let activeConversationId = currentConversationId;

    try {
      // Lazily create the conversation if it is a Client-Side Draft
      if (activeConversationId === 'draft') {
        try {
          const newConv = await api.createConversation({ mode: 'council' });
          activeConversationId = newConv.id;
          
          // Pre-populate index states so it appears immediately in the sidebar list
          setConversations((prev) => [
            { id: newConv.id, created_at: newConv.created_at, message_count: 0, mode: 'council', title: 'New Conversation' },
            ...prev,
          ]);
          
          // Update draft references safely
          conversationVersionRef.current++;
          skipLoadForIdRef.current = newConv.id;
          setCurrentConversationId(newConv.id);
        } catch (createErr) {
          console.error('Lazy creation of conversation failed:', createErr);
          setIsLoading(false);
          return;
        }
      }

      activeConversationIdRef.current = activeConversationId;

      // Optimistically update conversation title in list and current state if it is a new/untitled conversation
      const currentConvInList = conversations.find(c => c.id === activeConversationId);
      const currentTitle = currentConvInList?.title || currentConversation?.title;
      const hasNoTitle = isDefaultConversationTitle(currentTitle);

      if (hasNoTitle) {
        const optimisticTitle = deriveConversationTitle(content);
        setConversations(prev => prev.map(c =>
          c.id === activeConversationId ? { ...c, title: optimisticTitle } : c
        ));
        setCurrentConversation(prev =>
          prev && prev.id === activeConversationId ? { ...prev, title: optimisticTitle } : prev
        );
      }

      // Optimistically add user message to UI
      const userMessage = { role: 'user', content };
      setCurrentConversation((prev) => ({
        ...prev,
        id: activeConversationId, // transition draft ID to actual database UUID
        messages: [...prev.messages, userMessage],
      }));

      // Create a partial assistant message that will be updated progressively
      const assistantMessage = {
        role: 'assistant',
        stage1: null,
        stage2: null,
        stage3: null,
        metadata: null,
        loading: {
          search: false,
          stage1: false,
          stage2: false,
          stage3: false,
          stage4: false,
        },
        timers: {
          stage1Start: null,
          stage1End: null,
          stage2Start: null,
          stage2End: null,
          stage3Start: null,
          stage3End: null,
          stage4Start: null,
          stage4End: null,
        },
        progress: {
          stage1: { count: 0, total: 0, currentModel: null },
          stage2: { count: 0, total: 0, currentModel: null }
        }
      };

      // Add the partial assistant message
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
      }));

      // Send message with streaming
      const isDebate = debateRounds > 1 || critiqueMode !== 'freeform';
      const streamMethod = isDebate ? api.streamDebateMessage.bind(api) : api.sendMessageStream.bind(api);
      const streamOptions = {
        content,
        searchProvider,
        executionMode: effectiveMode,
        councilModels,
        chairmanModel: effectiveMode === 'full' ? chairmanModel : undefined,
      };
      if (isDebate) {
        streamOptions.debateRounds = debateRounds;
        streamOptions.critiqueMode = critiqueMode;
        streamOptions.autoConverge = autoConverge;
        streamOptions.convergenceThreshold = convergenceThreshold;
      }

      await streamMethod(
        activeConversationId,
        streamOptions,
        (eventType, event) => {
          switch (eventType) {
            case 'search_start':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                const updatedLastMsg = {
                  ...lastMsg,
                  loading: {
                    ...lastMsg.loading,
                    search: true
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'search_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                const updatedLastMsg = {
                  ...lastMsg,
                  loading: {
                    ...lastMsg.loading,
                    search: false
                  },
                  metadata: {
                    ...lastMsg.metadata,
                    search_query: event.data.search_query,
                    extracted_query: event.data.extracted_query,
                    search_context: event.data.search_context,
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'stage1_start':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                const updatedLastMsg = {
                  ...lastMsg,
                  loading: {
                    ...lastMsg.loading,
                    stage1: true
                  },
                  timers: {
                    ...lastMsg.timers,
                    stage1Start: Date.now()
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'stage1_init':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                const updatedLastMsg = {
                  ...lastMsg,
                  progress: {
                    ...lastMsg.progress,
                    stage1: {
                      count: 0,
                      total: event.total,
                      currentModel: null
                    }
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'stage1_progress':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                // Immutable update for stage1
                const updatedStage1 = lastMsg.stage1 ? [...lastMsg.stage1, event.data] : [event.data];
                const updatedLastMsg = {
                  ...lastMsg,
                  progress: {
                    ...lastMsg.progress,
                    stage1: {
                      count: event.count,
                      total: event.total,
                      currentModel: event.data.model
                    }
                  },
                  stage1: updatedStage1
                };

                messages[messages.length - 1] = updatedLastMsg;

                return { ...prev, messages };
              });
              break;

            case 'stage1_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                // Immutable update to prevent React rendering issues
                const updatedLastMsg = {
                  ...lastMsg,
                  stage1: event.data,
                  loading: {
                    ...lastMsg.loading,
                    stage1: false
                  },
                  timers: {
                    ...lastMsg.timers,
                    stage1End: Date.now()
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'stage2_start':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                const updatedLastMsg = {
                  ...lastMsg,
                  loading: {
                    ...lastMsg.loading,
                    stage2: true
                  },
                  timers: {
                    ...lastMsg.timers,
                    stage2Start: Date.now()
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'stage2_init':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                const updatedLastMsg = {
                  ...lastMsg,
                  progress: {
                    ...lastMsg.progress,
                    stage2: {
                      count: 0,
                      total: event.total,
                      currentModel: null
                    }
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'stage2_progress':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                // Immutable update for stage2
                const updatedStage2 = lastMsg.stage2 ? [...lastMsg.stage2, event.data] : [event.data];
                const updatedLastMsg = {
                  ...lastMsg,
                  progress: {
                    ...lastMsg.progress,
                    stage2: {
                      count: event.count,
                      total: event.total,
                      currentModel: event.data.model
                    }
                  },
                  stage2: updatedStage2
                };

                messages[messages.length - 1] = updatedLastMsg;

                return { ...prev, messages };
              });
              break;

            case 'stage2_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                // Immutable update to prevent React rendering issues
                const updatedLastMsg = {
                  ...lastMsg,
                  stage2: event.data,
                  loading: {
                    ...lastMsg.loading,
                    stage2: false
                  },
                  timers: {
                    ...lastMsg.timers,
                    stage2End: Date.now()
                  },
                  metadata: {
                    ...lastMsg.metadata,
                    ...event.metadata
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'stage3_start':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                const updatedLastMsg = {
                  ...lastMsg,
                  loading: {
                    ...lastMsg.loading,
                    stage3: true
                  },
                  timers: {
                    ...lastMsg.timers,
                    stage3Start: Date.now(),
                    stage2End: lastMsg.timers?.stage2Start && !lastMsg.timers?.stage2End
                      ? Date.now()
                      : lastMsg.timers?.stage2End,
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'stage3_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                // Immutable update to prevent React rendering issues
                const updatedLastMsg = {
                  ...lastMsg,
                  stage3: event.data,
                  loading: {
                    ...lastMsg.loading,
                    stage3: false
                  },
                  timers: {
                    ...lastMsg.timers,
                    stage3End: Date.now()
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'round_start':
              if (event.round > 1) {
                setIsLoading(true);
              }
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];
                const round = event.round;

                const updatedLastMsg = {
                  ...lastMsg,
                  stage1: round > 1 ? null : lastMsg.stage1,
                  stage2: round > 1 ? null : lastMsg.stage2,
                  stage3: round > 1 ? null : lastMsg.stage3,
                  loading: {
                    ...lastMsg.loading,
                    stage1: false,
                    stage2: false,
                    stage3: false,
                    stage4: false,
                  },
                  timers: {
                    ...lastMsg.timers,
                    stage1Start: round > 1 ? null : lastMsg.timers?.stage1Start,
                    stage1End: round > 1 ? null : lastMsg.timers?.stage1End,
                    stage2Start: round > 1 ? null : lastMsg.timers?.stage2Start,
                    stage2End: round > 1 ? null : lastMsg.timers?.stage2End,
                    stage3Start: round > 1 ? null : lastMsg.timers?.stage3Start,
                    stage3End: round > 1 ? null : lastMsg.timers?.stage3End,
                  },
                  metadata: {
                    ...lastMsg.metadata,
                    current_round: round,
                    debate_rounds_configured: event.total_rounds,
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'round_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];
                
                const currentRoundData = {
                  round_number: event.round,
                  stage1: lastMsg.stage1,
                  stage2: lastMsg.stage2,
                  stage3: lastMsg.stage3,
                  metadata: {
                    label_to_model: lastMsg.metadata?.label_to_model,
                    aggregate_rankings: lastMsg.metadata?.aggregate_rankings,
                    canonical_claims: lastMsg.metadata?.canonical_claims,
                    aggregate_claim_verdicts: lastMsg.metadata?.aggregate_claim_verdicts,
                    cost_report: lastMsg.metadata?.cost_report,
                  }
                };

                const existingRounds = lastMsg.metadata?.rounds || [];
                const updatedRounds = [...existingRounds];
                const existingIdx = updatedRounds.findIndex(r => r.round_number === event.round);
                if (existingIdx >= 0) {
                  updatedRounds[existingIdx] = currentRoundData;
                } else {
                  updatedRounds.push(currentRoundData);
                }

                const updatedLastMsg = {
                  ...lastMsg,
                  metadata: {
                    ...lastMsg.metadata,
                    rounds: updatedRounds,
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'convergence':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                const updatedLastMsg = {
                  ...lastMsg,
                  metadata: {
                    ...lastMsg.metadata,
                    converged: true,
                    convergence_message: event.message,
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'stage4_start':
              setIsLoading(true);
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                const updatedLastMsg = {
                  ...lastMsg,
                  loading: {
                    ...lastMsg.loading,
                    stage4: true
                  },
                  timers: {
                    ...lastMsg.timers,
                    stage4Start: Date.now(),
                    stage3End: lastMsg.timers?.stage3Start && !lastMsg.timers?.stage3End
                      ? Date.now()
                      : lastMsg.timers?.stage3End,
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'stage4_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];

                const updatedLastMsg = {
                  ...lastMsg,
                  loading: {
                    ...lastMsg.loading,
                    stage4: false
                  },
                  timers: {
                    ...lastMsg.timers,
                    stage4End: Date.now()
                  },
                  metadata: {
                    ...lastMsg.metadata,
                    stage4: event.data
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'debate_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];
                const rounds = event.rounds || [];
                const lastRound = rounds[rounds.length - 1] || {};

                const updatedLastMsg = {
                  ...lastMsg,
                  stage1: lastRound.stage1 || lastMsg.stage1,
                  stage2: lastRound.stage2 || lastMsg.stage2,
                  stage3: lastRound.stage3 || lastMsg.stage3,
                  loading: IDLE_LOADING,
                  timers: finalizeTimers(lastMsg.timers),
                  metadata: {
                    ...lastMsg.metadata,
                    rounds: rounds,
                    stage4: event.stage4 || lastMsg.metadata?.stage4,
                    cost_report: event.cost_report || lastMsg.metadata?.cost_report,
                    converged: event.converged || lastMsg.metadata?.converged,
                    critique_mode: event.critique_mode || lastMsg.metadata?.critique_mode,
                    label_to_model: lastRound.metadata?.label_to_model || lastMsg.metadata?.label_to_model,
                    aggregate_rankings: lastRound.metadata?.aggregate_rankings || lastMsg.metadata?.aggregate_rankings,
                    canonical_claims: lastRound.metadata?.canonical_claims || lastMsg.metadata?.canonical_claims,
                    aggregate_claim_verdicts: lastRound.metadata?.aggregate_claim_verdicts || lastMsg.metadata?.aggregate_claim_verdicts,
                  }
                };

                messages[messages.length - 1] = updatedLastMsg;
                return { ...prev, messages };
              });
              break;

            case 'title_complete':
              // Update with final generated title optimistically
              if (event.data && event.data.title) {
                const finalTitle = event.data.title;
                setConversations(prev => prev.map(c =>
                  c.id === activeConversationId ? { ...c, title: finalTitle } : c
                ));
                setCurrentConversation(prev => prev && prev.id === activeConversationId ? { ...prev, title: finalTitle } : prev);
              }
              // Reload conversations to get updated title
              loadConversations();
              break;

            case 'complete':
              setCurrentConversation((prev) => {
                if (!prev || prev.messages.length === 0) return prev;
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];
                if (lastMsg.role === 'assistant') {
                  messages[messages.length - 1] = {
                    ...lastMsg,
                    loading: IDLE_LOADING,
                    timers: finalizeTimers(lastMsg.timers),
                    metadata: {
                      ...lastMsg.metadata,
                      ...(event.metadata || {}),
                    },
                  };
                }
                return { ...prev, messages };
              });
              // Stream complete, reload conversations list
              loadConversations();
              setIsLoading(false);
              break;

            case 'error':
              console.error('Stream error:', event.message);
              setCurrentConversation((prev) => {
                if (!prev || prev.messages.length === 0) return prev;
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];
                if (lastMsg.role === 'assistant') {
                  messages[messages.length - 1] = {
                    ...lastMsg,
                    error: event.message || 'The council request failed.',
                    loading: IDLE_LOADING,
                    timers: finalizeTimers(lastMsg.timers),
                  };
                }
                return { ...prev, messages };
              });
              setIsLoading(false);
              break;

            default:
              console.log('Unknown event type:', eventType);
          }
        }, abortControllerRef.current?.signal);
    } catch (error) {
      // Handle aborted requests - mark message as aborted
      if (error.name === 'AbortError') {
        console.log('Request aborted');
        // Mark the assistant message as aborted and stop timers
        setCurrentConversation((prev) => {
          if (!prev || prev.messages.length < 2) return prev;
          const messages = [...prev.messages];
          const lastMsg = messages[messages.length - 1];
          if (lastMsg.role === 'assistant') {
            messages[messages.length - 1] = {
              ...lastMsg,
              aborted: true,
              loading: IDLE_LOADING,
              timers: finalizeTimers(lastMsg.timers),
            };
          }
          return { ...prev, messages };
        });
        setIsLoading(false);
        return;
      }
      console.error('Failed to send message:', error);
      // Remove optimistic messages on error
      setCurrentConversation((prev) => ({
        ...prev,
        messages: prev.messages.slice(0, -2),
      }));
      setIsLoading(false);
    } finally {
      // Only clear the controller if this is still the current request
      // This prevents race conditions if user rapidly sends multiple messages
      if (requestIdRef.current === currentRequestId) {
        abortControllerRef.current = null;
      }
      // Reload conversations to ensure title/messages are synced, even if aborted
      loadConversations();
    }
  };

  // Mobile sidebar handlers
  const handleMobileSelectConversation = (id) => {
    handleSelectConversation(id);
    setSidebarOpen(false); // Close sidebar on mobile after selection
  };

  const handleMobileNewConversation = async () => {
    await handleNewConversation();
    setSidebarOpen(false); // Close sidebar on mobile after creating new conversation
  };

  const resetAppState = (mode) => {
    abortAllStreams();
    setIsLoading(false);
    
    if (mode === 'advisors') {
      setCurrentConversationId('draft');
      setCurrentConversation({
        id: 'draft',
        mode: 'advisors',
        title: 'New Conversation',
        messages: []
      });
    } else {
      setCurrentConversationId(null);
      setCurrentConversation(null);
    }
    
    setAppMode(mode);
    setSidebarOpen(false);
  };

  const handleMobileNewAdvisors = () => resetAppState('advisors');

  const handleMobileOpenSettings = () => {
    setShowSettings(true);
    setSidebarOpen(false); // Close sidebar on mobile
  };

  return (
    <div className="app">
      {/* Mobile hamburger menu button */}
      <button
        className="mobile-menu-btn"
        onClick={() => setSidebarOpen(true)}
        aria-label="Open menu"
      >
        <span className="hamburger-icon"></span>
      </button>

      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleMobileSelectConversation}
        onNewConversation={handleMobileNewConversation}
        onNewAdvisors={handleMobileNewAdvisors}
        onDeleteConversation={handleDeleteConversation}
        onOpenSettings={handleMobileOpenSettings}
        isLoading={isLoading}
        onAbort={handleAbort}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onGoHome={() => resetAppState(null)}
        dateFormat={dateFormat}
      />

      <div className="main-area">
        <AppErrorBoundary>
          <Suspense fallback={<AppLoadingFallback />}>
            {appMode === null && !currentConversationId ? (
              <LandingPage onSelectMode={(m) => setAppMode(m)} />
            ) : (
              <ChatInterface
                conversation={currentConversation}
                onSendMessage={handleSendMessage}
                onAbort={handleAbort}
                isLoading={isLoading}
                councilConfigured={councilConfigured}
                councilModels={councilModels}
                chairmanModel={chairmanModel}
                searchProvider={searchProvider}
                availableSearchProviders={availableSearchProviders}
                onOpenSettings={handleOpenSettings}
                executionMode={executionMode}
                onExecutionModeChange={setExecutionMode}
                mode={appMode}
                onStartDebate={handleStartDebate}
                onNewConversation={handleNewConversation}
                onCouncilChange={handleCouncilChange}
                critiqueMode={critiqueMode}
                debateRounds={debateRounds}
                autoConverge={autoConverge}
                convergenceThreshold={convergenceThreshold}
              />
            )}
          </Suspense>
        </AppErrorBoundary>
      </div>

      {showSettings && (
        <AppErrorBoundary>
          <Suspense fallback={<AppLoadingFallback />}>
            <Settings
              onClose={handleSettingsClose}
              ollamaStatus={ollamaStatus}
              onRefreshOllama={testOllamaConnection}
              initialSection={settingsInitialSection}
            />
          </Suspense>
        </AppErrorBoundary>
      )}
    </div>
  );
}

export default App;

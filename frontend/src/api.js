/**
 * API client for The AI Counsel backend.
 */

// Dynamically determine API base URL based on current hostname
// This allows the app to work on both localhost and network IPs
const getApiBase = () => {
  if (window.__AI_COUNSEL_CONFIG__?.apiUrl) {
    return window.__AI_COUNSEL_CONFIG__.apiUrl;
  }
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  const hostname = window.location.hostname;
  return `http://${hostname}:8001`;
};

const API_BASE = getApiBase();

export function buildAvailableSearchProviders(settings) {
  const providers = [{ id: 'duckduckgo', name: 'DuckDuckGo' }];
  if (settings.serper_api_key_set) providers.push({ id: 'serper', name: 'Serper (Google)' });
  if (settings.tavily_api_key_set) providers.push({ id: 'tavily', name: 'Tavily' });
  if (settings.brave_api_key_set) providers.push({ id: 'brave', name: 'Brave Search' });
  if (settings.tinyfish_api_key_set) providers.push({ id: 'tinyfish', name: 'TinyFish' });
  return providers;
}

export const DEFAULT_EXECUTION_MODE = 'full';

async function _consumeSSEStream(body, onEvent) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  try {
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop();
      for (const block of parts) {
        for (const line of block.split('\n')) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              onEvent(event.type, event);
            } catch (e) {
              console.error('Failed to parse SSE event:', e);
            }
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export const api = {
  /**
   * List all conversations.
   */
  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) {
      throw new Error('Failed to list conversations');
    }
    return response.json();
  },

  /**
   * Create a new conversation.
   */
  async createConversation(options = {}) {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(options),
    });
    if (!response.ok) {
      throw new Error('Failed to create conversation');
    }
    return response.json();
  },

  /**
   * Get a specific conversation.
   */
  async getConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`
    );
    if (!response.ok) {
      throw new Error('Failed to get conversation');
    }
    return response.json();
  },

  /**
   * Get live progress for an active streaming run (council or debate).
   * Returns {active: false} when no run is active for this conversation.
   */
  async getConversationProgress(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/progress`
    );
    if (!response.ok) {
      throw new Error('Failed to get conversation progress');
    }
    return response.json();
  },

  /**
   * Delete a conversation.
   */
  async deleteConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`,
      { method: 'DELETE' }
    );
    if (!response.ok) {
      throw new Error('Failed to delete conversation');
    }
    return response.json();
  },

  /**
   * Send a message in a conversation.
   */
  async sendMessage(conversationId, content, webSearch = false) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content, web_search: webSearch }),
      }
    );
    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    return response.json();
  },

  /**
   * Get application settings.
   */
  async getSettings() {
    const response = await fetch(`${API_BASE}/api/settings`);
    if (!response.ok) {
      throw new Error('Failed to get settings');
    }
    return response.json();
  },

  /**
   * Test Tavily API key.
   */
  async testTavilyKey(apiKey) {
    const response = await fetch(`${API_BASE}/api/settings/test-tavily`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ api_key: apiKey }),
    });
    if (!response.ok) {
      throw new Error('Failed to test API key');
    }
    return response.json();
  },

  /**
   * Test OpenRouter API key.
   */
  async testOpenRouterKey(apiKey) {
    const response = await fetch(`${API_BASE}/api/settings/test-openrouter`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ api_key: apiKey }),
    });
    if (!response.ok) {
      throw new Error('Failed to test API key');
    }
    return response.json();
  },

  /**
   * Test Brave API key.
   */
  async testBraveKey(apiKey) {
    const response = await fetch(`${API_BASE}/api/settings/test-brave`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ api_key: apiKey }),
    });
    if (!response.ok) {
      throw new Error('Failed to test API key');
    }
    return response.json();
  },

  /**
   * Test TinyFish API key.
   */
  async testTinyfishKey(apiKey) {
    const response = await fetch(`${API_BASE}/api/settings/test-tinyfish`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ api_key: apiKey }),
    });
    if (!response.ok) {
      throw new Error('Failed to test API key');
    }
    return response.json();
  },

  /**
   * Test Serper API key.
   */
  async testSerperKey(apiKey) {
    const response = await fetch(`${API_BASE}/api/settings/test-serper`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ api_key: apiKey }),
    });
    if (!response.ok) {
      throw new Error('Failed to test API key');
    }
    return response.json();
  },

  /**
   * Test a specific provider's API key.
   */
  async testProviderKey(providerId, apiKey) {
    const response = await fetch(`${API_BASE}/api/settings/test-provider`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ provider_id: providerId, api_key: apiKey }),
    });
    if (!response.ok) {
      throw new Error('Failed to test API key');
    }
    return response.json();
  },

  /**
   * Test the OpenCode API key (against Zen and/or Go).
   * Pass product='zen' or 'go' to test a single product; omit to test both.
   */
  async testOpencodeKey(apiKey, product = null) {
    const response = await fetch(`${API_BASE}/api/settings/test-opencode`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ api_key: apiKey, product }),
    });
    if (!response.ok) {
      throw new Error('Failed to test OpenCode key');
    }
    return response.json();
  },

  /**
   * Test Ollama connection.
   */
  async testOllamaConnection(baseUrl) {
    const response = await fetch(`${API_BASE}/api/settings/test-ollama`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ base_url: baseUrl }),
    });
    if (!response.ok) {
      throw new Error('Failed to test Ollama connection');
    }
    return response.json();
  },

  /**
   * Test custom OpenAI-compatible endpoint.
   */
  async testCustomEndpoint(name, url, apiKey) {
    const response = await fetch(`${API_BASE}/api/settings/test-custom-endpoint`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name, url, api_key: apiKey }),
    });
    if (!response.ok) {
      throw new Error('Failed to test custom endpoint');
    }
    return response.json();
  },

  /**
   * Get available models from custom endpoint.
   */
  async getCustomEndpointModels() {
    const response = await fetch(`${API_BASE}/api/custom-endpoint/models`);
    if (!response.ok) {
      throw new Error('Failed to get custom endpoint models');
    }
    return response.json();
  },

  /**
   * Get available models from OpenRouter.
   */
  async getModels() {
    const response = await fetch(`${API_BASE}/api/models`);
    if (!response.ok) {
      throw new Error('Failed to get models');
    }
    return response.json();
  },

  /**
   * Get available models from Ollama.
   */
  async getOllamaModels(baseUrl) {
    let url = `${API_BASE}/api/ollama/tags`;
    if (baseUrl) {
      url += `?base_url=${encodeURIComponent(baseUrl)}`;
    }
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error('Failed to get Ollama models');
    }
    return response.json();
  },

  /**
   * Get available models from direct providers.
   */
  async getDirectModels() {
    const response = await fetch(`${API_BASE}/api/models/direct`);
    if (!response.ok) {
      throw new Error('Failed to get direct models');
    }
    return response.json();
  },

  /**
   * Get default model settings.
   */
  async getDefaultSettings() {
    const response = await fetch(`${API_BASE}/api/settings/defaults`);
    if (!response.ok) {
      throw new Error('Failed to get default settings');
    }
    return response.json();
  },

  /**
   * Update application settings.
   */
  async updateSettings(settings) {
    const response = await fetch(`${API_BASE}/api/settings`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(settings),
    });
    if (!response.ok) {
      throw new Error('Failed to update settings');
    }
    return response.json();
  },

  async getPersonas() {
    const response = await fetch(`${API_BASE}/api/personas`);
    if (!response.ok) throw new Error('Failed to fetch personas');
    return response.json();
  },

  async updatePersona(personaId, overrides) {
    const response = await fetch(`${API_BASE}/api/personas/${personaId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(overrides),
    });
    if (!response.ok) throw new Error('Failed to update persona');
    return response.json();
  },

  async resetPersona(personaId) {
    const response = await fetch(`${API_BASE}/api/personas/${personaId}/override`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to reset persona');
    return response.json();
  },

  async extractDocuments(files) {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    const response = await fetch(`${API_BASE}/api/documents/extract`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to extract documents');
    }
    return response.json();
  },

  async sendDebateStream(conversationId, options, onEvent, signal) {
    const body = {
      question: options.question,
      persona_ids: options.personaIds,
      model_assignments: options.modelAssignments || null,
      default_model: options.defaultModel || null,
      tiebreaker_model: options.tiebreakerModel || null,
      max_rounds: options.maxRounds || 3,
      search_provider: options.searchProvider || null,
    };
    if (options.documents && options.documents.length > 0) {
      body.documents = options.documents;
    }

    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/debate/stream?_t=${Date.now()}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache',
        },
        body: JSON.stringify(body),
        signal,
        cache: 'no-store',
      }
    );

    if (!response.ok) {
      throw new Error('Failed to start debate stream');
    }

    await _consumeSSEStream(response.body, onEvent);
  },

  /**
   * Send a message and receive streaming updates.
   * @param {string} conversationId - The conversation ID
   * @param {Object} options - Message options
   * @param {string} options.content - The message content
   * @param {boolean} options.webSearch - Whether to use web search
   * @param {string} options.executionMode - Execution mode: 'chat_only', 'chat_ranking', or 'full'
   * @param {function} onEvent - Callback function for each event: (eventType, data) => void
   * @param {AbortSignal} signal - Optional AbortSignal to cancel the request
   * @returns {Promise<void>}
   */
  async sendMessageStream(conversationId, options, onEvent, signal) {
    const {
      content,
      searchProvider = null,
      executionMode = 'full',
      councilModels = null,
      chairmanModel = null,
      documents = null,
    } = options;
    const body = {
      content,
      search_provider: searchProvider,
      execution_mode: executionMode,
    };
    if (councilModels && councilModels.length > 0) {
      body.council_models = councilModels;
    }
    if (chairmanModel) {
      body.chairman_model = chairmanModel;
    }
    if (documents && documents.length > 0) {
      body.documents = documents;
    }
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/stream?_t=${Date.now()}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache',
        },
        body: JSON.stringify(body),
        signal,
        cache: 'no-store',
      }
    );

    if (!response.ok) {
      throw new Error('Failed to send message');
    }

    await _consumeSSEStream(response.body, onEvent);
  },

  /**
   * Send a message and stream the multi-round iterative debate process.
   */
  async streamDebateMessage(conversationId, options, onEvent, signal) {
    const {
      content,
      searchProvider = null,
      executionMode = 'full',
      councilModels = null,
      chairmanModel = null,
      debateRounds = null,
      documents = null,
    } = options;
    const body = {
      content,
      search_provider: searchProvider,
      execution_mode: executionMode,
      debate_rounds: debateRounds,
    };
    if (councilModels && councilModels.length > 0) {
      body.council_models = councilModels;
    }
    if (chairmanModel) {
      body.chairman_model = chairmanModel;
    }
    if (documents && documents.length > 0) {
      body.documents = documents;
    }
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/debate?_t=${Date.now()}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache',
        },
        body: JSON.stringify(body),
        signal,
        cache: 'no-store',
      }
    );

    if (!response.ok) {
      throw new Error('Failed to start debate stream');
    }

    await _consumeSSEStream(response.body, onEvent);
  },

  async startOAuth(providerId) {
    const response = await fetch(`${API_BASE}/api/oauth/${encodeURIComponent(providerId)}/start`, {
      method: 'POST',
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to start OAuth');
    }
    return response.json();
  },

  async oauthStatus(providerId, sessionId) {
    const params = new URLSearchParams({ session_id: sessionId });
    const response = await fetch(
      `${API_BASE}/api/oauth/${encodeURIComponent(providerId)}/status?${params}`
    );
    if (!response.ok) {
      throw new Error('Failed to get OAuth status');
    }
    return response.json();
  },

  async disconnectOAuth(providerId) {
    const response = await fetch(`${API_BASE}/api/oauth/${encodeURIComponent(providerId)}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to disconnect OAuth');
    }
    return response.json();
  },

  async disconnectAllProviders() {
    const response = await fetch(`${API_BASE}/api/settings/disconnect-all-providers`, {
      method: 'POST',
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to disconnect all providers');
    }
    return response.json();
  },

  async setCredentialStorage(mode) {
    const response = await fetch(`${API_BASE}/api/settings/credential-storage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to change credential storage');
    }
    return response.json();
  },

  async discoverRelayAi() {
    const response = await fetch(`${API_BASE}/api/credentials/import/relay-ai/discover`);
    if (!response.ok) {
      throw new Error('Failed to discover relay-ai credentials');
    }
    return response.json();
  },

  async importRelayAi(ids, replaceExisting = false) {
    const response = await fetch(`${API_BASE}/api/credentials/import/relay-ai`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, replace_existing: replaceExisting }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to import relay-ai credentials');
    }
    return response.json();
  },

  async dismissRelayImport() {
    const response = await fetch(`${API_BASE}/api/settings/relay-ai-import-dismissed`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw new Error('Failed to dismiss relay-ai import');
    }
    return response.json();
  },
};

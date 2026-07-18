/** Subscription OAuth providers (device-code login). */
export const OAUTH_PROVIDERS = [
  {
    id: 'xai-oauth',
    connectedKey: 'xai_oauth_connected',
    label: 'xAI SuperGrok',
    description: 'Use your SuperGrok subscription via OAuth device login.',
  },
  {
    id: 'openai-oauth',
    connectedKey: 'openai_oauth_connected',
    label: 'ChatGPT Plus/Pro',
    description: 'Use ChatGPT Plus or Pro models via OAuth device login.',
  },
  {
    id: 'github-copilot',
    connectedKey: 'github_copilot_connected',
    label: 'GitHub Copilot',
    description: 'Use GitHub Copilot models via OAuth device login.',
  },
];

export const OAUTH_PREFIXES = ['xai-oauth:', 'openai-oauth:', 'github-copilot:'];

export function isOAuthModel(model) {
  const id = model?.id || '';
  const source = model?.source || '';
  return OAUTH_PREFIXES.some((p) => id.startsWith(p) || source === p.slice(0, -1));
}

export function filterOAuthModels(directModels, settings) {
  const ep = settings.enabled_providers || {};
  return (directModels || []).filter((model) => {
    const prefix = OAUTH_PREFIXES.find((p) => model.id?.startsWith(p));
    if (!prefix) return false;
    const providerId = prefix.slice(0, -1);
    const meta = OAUTH_PROVIDERS.find((p) => p.id === providerId);
    if (!meta) return false;
    return ep[providerId] !== false && settings[meta.connectedKey];
  });
}

export function countStoredCredentials(settings) {
  if (!settings) return 0;
  const flags = [
    'serper_api_key_set', 'tavily_api_key_set', 'brave_api_key_set', 'tinyfish_api_key_set',
    'openrouter_api_key_set', 'openai_api_key_set', 'anthropic_api_key_set', 'google_api_key_set',
    'mistral_api_key_set', 'deepseek_api_key_set', 'groq_api_key_set', 'nvidia_api_key_set',
    'opencode_api_key_set', 'custom_endpoint_api_key_set',
    'xai_oauth_connected', 'openai_oauth_connected', 'github_copilot_connected',
  ];
  return flags.filter((k) => settings[k]).length;
}

/** True when at least one LLM source is usable (API key, OAuth, custom endpoint, or Ollama). */
export function hasConfiguredProviders(settings, { ollamaConnected = false } = {}) {
  const ep = settings?.enabled_providers || {};
  // Reachable Ollama only counts when the provider is enabled (Connect), not merely detected.
  if (ollamaConnected && ep.ollama) return true;
  if (settings?.custom_endpoint_url) return true;
  if (!settings) return false;
  const llmFlags = [
    'openrouter_api_key_set', 'openai_api_key_set', 'anthropic_api_key_set', 'google_api_key_set',
    'mistral_api_key_set', 'deepseek_api_key_set', 'groq_api_key_set', 'nvidia_api_key_set',
    'opencode_api_key_set', 'custom_endpoint_api_key_set',
    'xai_oauth_connected', 'openai_oauth_connected', 'github_copilot_connected',
  ];
  return llmFlags.some((k) => settings[k]);
}

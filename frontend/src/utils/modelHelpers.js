// Helper to get visual properties for models

export const getModelVisuals = (modelId) => {
  if (!modelId) return { name: 'Unknown', color: '#94a3b8', short: '?' };

  const id = modelId.toLowerCase();

  // Ollama - CHECK FIRST because "ollama" contains "llama" substring
  if (id.startsWith('ollama:')) {
    return { name: 'Ollama', color: '#f1f5f9', short: 'Local', icon: '🦙' };
  }

  // OpenAI
  if (id.includes('openai') || id.includes('gpt')) {
    return { name: 'OpenAI', color: '#10a37f', short: 'GPT', icon: '🤖' };
  }

  // Anthropic
  if (id.includes('anthropic') || id.includes('claude')) {
    return { name: 'Anthropic', color: '#d97757', short: 'Claude', icon: '🧠' };
  }

  // Google
  if (id.includes('google') || id.includes('gemini')) {
    return { name: 'Google', color: '#4285f4', short: 'Gemini', icon: '✨' };
  }

  // Mistral
  if (id.includes('mistral')) {
    return { name: 'Mistral', color: '#5a4bda', short: 'Mistral', icon: '🌪️' };
  }

  // Groq (Provider, often Llama or Mixtral)
  // Check this BEFORE Meta/Mistral because Groq hosts those models
  if (id.includes('groq') || id.includes('versatile') || id.includes('instant')) {
    return { name: 'Groq', color: '#f97316', short: 'Groq', icon: '⚡' };
  }

  // Meta / Llama
  if (id.includes('meta') || id.includes('llama')) {
    return { name: 'Meta', color: '#0668e1', short: 'Llama', icon: '🦙' };
  }

  // DeepSeek
  if (id.includes('deepseek')) {
    return { name: 'DeepSeek', color: '#4e80ee', short: 'DeepSeek', icon: '🐋' };
  }

  // Kimi / Moonshot
  if (id.includes('kimi') || id.includes('moonshot')) {
    return { name: 'Kimi', color: '#111827', short: 'Kimi', icon: '月' };
  }

  // Local (fallback for models without provider prefix or slash)
  if (!id.includes('/') && !id.includes(':')) {
    return { name: 'Local', color: '#f1f5f9', short: 'Local', icon: '💻' };
  }

  // Default
  return { name: 'Model', color: '#94a3b8', short: 'AI', icon: '🤖' };
};

export const getShortModelName = (modelId) => {
  if (!modelId) return 'Unknown';

  const formatVersionSuffix = (value) => {
    return value
      .replace(/(\d(?:\.\d+)*)(pro|flash|turbo|mini|nano|opus|sonnet|haiku)\b/gi, '$1 $2')
      .replace(/\b(pro|flash|turbo|mini|nano|opus|sonnet|haiku)(\d(?:\.\d+)*)\b/gi, '$1 $2');
  };

  const titleCaseWords = (value) =>
    value
      .split(' ')
      .filter(Boolean)
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');

  const cleanModelId = String(modelId)
    .trim()
    .replace(/^custom:/i, '')
    .replace(/^ollama:/i, '')
    .replace(/^groq:/i, '')
    .replace(/^openai:/i, '')
    .replace(/^anthropic:/i, '')
    .replace(/^google:/i, '')
    .replace(/^mistral:/i, '')
    .replace(/^deepseek:/i, '');

  // Handle "provider/model-name" format
  const rawName = cleanModelId.includes('/') ? cleanModelId.split('/').pop() : cleanModelId;
  const id = rawName.toLowerCase();

  if (id.startsWith('gpt-')) {
    return rawName.replace(/^gpt-/i, 'GPT ').replace(/-/g, ' ');
  }

  if (id.startsWith('gemini-')) {
    const suffix = formatVersionSuffix(rawName.replace(/^gemini-/i, '').replace(/-/g, ' '));
    return `Gemini ${titleCaseWords(suffix)}`;
  }

  if (id.startsWith('claude-')) {
    const suffix = formatVersionSuffix(rawName.replace(/^claude-/i, '').replace(/-/g, ' '));
    const withoutFamilyVersion = suffix.replace(/^(\d+(?:\.\d+)?\s*)/i, '');
    return titleCaseWords(withoutFamilyVersion);
  }

  if (id.startsWith('kimi-')) {
    return rawName.replace(/^kimi-/i, 'Kimi ').replace(/-/g, ' ');
  }

  if (id.startsWith('moonshot-')) {
    return rawName.replace(/^moonshot-/i, 'Kimi ').replace(/-/g, ' ');
  }

  if (id.startsWith('mistral-')) {
    const suffix = formatVersionSuffix(rawName.replace(/^mistral-/i, '').replace(/-/g, ' '));
    return `Mistral ${titleCaseWords(suffix)}`;
  }

  if (id.startsWith('deepseek-')) {
    const suffix = formatVersionSuffix(rawName.replace(/^deepseek-/i, '').replace(/-/g, ' '));
    return `DeepSeek ${titleCaseWords(suffix)}`;
  }

  return titleCaseWords(formatVersionSuffix(rawName.replace(/[-_]+/g, ' ')));
};

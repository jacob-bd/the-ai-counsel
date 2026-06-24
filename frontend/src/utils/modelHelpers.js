import openaiLogo from '../assets/icons/openai.svg';
import anthropicLogo from '../assets/icons/anthropic.svg';
import googleLogo from '../assets/icons/google.svg';
import deepseekLogo from '../assets/icons/deepseek.svg';
import xaiLogo from '../assets/icons/xai.svg';

// Helper to get visual properties for models
export const VERIFIED_NOTION2API_MODELS = Object.freeze({
  'oatmeal-cookie': { displayName: 'GPT-5.2', family: 'openai', group: 'fast' },
  'oval-kumquat-medium': { displayName: 'GPT-5.4', family: 'openai', group: 'fast' },
  'opal-quince-medium': { displayName: 'GPT-5.5', family: 'openai', group: 'intelligent' },
  'vertex-gemini-2.5-flash': { displayName: 'Gemini 2.5 Flash', family: 'gemini', group: 'fast' },
  'vertex-gemini-3.5-flash': { displayName: 'Gemini 3.5 Flash', family: 'gemini', group: 'fast' },
  'almond-croissant-low': { displayName: 'Sonnet 4.6', family: 'anthropic', group: 'fast' },
  'avocado-froyo-medium': { displayName: 'Opus 4.6', family: 'anthropic', group: 'intelligent' },
  'apricot-sorbet-high': { displayName: 'Opus 4.7', family: 'anthropic', group: 'intelligent' },
  'ambrosia-tart-high': { displayName: 'Opus 4.8', family: 'anthropic', group: 'intelligent' },
  'oregon-grape-medium': { displayName: 'GPT-5.4 Mini', family: 'openai', group: 'fast' },
  'otaheite-apple-medium': { displayName: 'GPT-5.4 Nano', family: 'openai', group: 'fast' },
  'fireworks-minimax-m2.5': { displayName: 'MiniMax M2.5', family: 'minimax', group: 'intelligent' },
  'fireworks-kimi-k2.6': { displayName: 'Kimi K2.6', family: 'kimi', group: 'intelligent' },
  'baseten-deepseek-v4-pro': { displayName: 'DeepSeek V4 Pro', family: 'deepseek', group: 'intelligent' },
  'xigua-mochi-medium': { displayName: 'Grok 4.3', family: 'xai', group: 'intelligent' },
  'xinomavro-cake': { displayName: 'Grok Build 0.1', family: 'xai', group: 'intelligent' },
  'galette-medium-thinking': { displayName: 'Gemini 3.1 Pro', family: 'gemini', group: 'intelligent' },
  'anthropic-haiku-4.5': { displayName: 'Haiku 4.5', family: 'anthropic', group: 'fast' },
  gingerbread: { displayName: 'Gemini 3 Flash', family: 'gemini', group: 'fast' },
});

export function getModelRawId(model) {
  const modelId = String(model?.id || model?.name || '').trim();
  return modelId.replace(/^notion2api:/i, '');
}

export function getNotion2APIModelMetadata(modelId) {
  const rawId = String(modelId || '').trim().replace(/^notion2api:/i, '').toLowerCase();
  return VERIFIED_NOTION2API_MODELS[rawId] || null;
}

export function getNotion2APIModelFamily(modelId) {
  const metadata = getNotion2APIModelMetadata(modelId);
  if (metadata?.family) return metadata.family;

  const rawId = String(modelId || '').trim().replace(/^notion2api:/i, '').toLowerCase();
  if (/\b(gpt|openai)\b/.test(rawId)) return 'openai';
  if (/\b(claude|sonnet|opus|haiku|anthropic)\b/.test(rawId)) return 'anthropic';
  if (/\b(gemini|google)\b/.test(rawId)) return 'gemini';
  if (/\b(grok|xai)\b/.test(rawId)) return 'xai';
  if (/\bdeepseek\b/.test(rawId)) return 'deepseek';
  if (/\b(kimi|moonshot)\b/.test(rawId)) return 'kimi';
  if (/\bminimax\b/.test(rawId)) return 'minimax';
  return null;
}

export const getModelVisuals = (modelId) => {
  if (!modelId) return { name: 'Unknown', color: '#94a3b8', short: '?' };

  const id = modelId.toLowerCase();

  // Notion2API is the transport; render the underlying model brand.
  if (id.startsWith('notion2api:')) {
    const family = getNotion2APIModelFamily(modelId);
    const familyVisuals = {
      openai: { name: 'OpenAI via Notion2API', color: '#10a37f', short: 'GPT', icon: 'GPT', logo: openaiLogo },
      anthropic: { name: 'Anthropic via Notion2API', color: '#d97757', short: 'Claude', icon: 'A', logo: anthropicLogo },
      gemini: { name: 'Google via Notion2API', color: '#4285f4', short: 'Gemini', icon: 'G', logo: googleLogo },
      xai: { name: 'xAI via Notion2API', color: '#f8fafc', short: 'Grok', icon: 'X', logo: xaiLogo },
      deepseek: { name: 'DeepSeek via Notion2API', color: '#4e80ee', short: 'DeepSeek', icon: 'DS', logo: deepseekLogo },
      kimi: { name: 'Kimi via Notion2API', color: '#cbd5e1', short: 'Kimi', icon: 'K' },
      minimax: { name: 'MiniMax via Notion2API', color: '#a78bfa', short: 'MiniMax', icon: 'M' },
    };

    return familyVisuals[family]
      || { name: 'Notion2API', color: '#64748b', short: 'Notion', icon: 'N2' };
  }

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

  const normalizedModelId = String(modelId).trim();
  if (normalizedModelId.toLowerCase().startsWith('notion2api:')) {
    const verified = getNotion2APIModelMetadata(normalizedModelId);
    if (verified) return verified.displayName;
  }

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
    .replace(/:free$/i, '')
    .replace(/^custom:/i, '')
    .replace(/^notion2api:/i, '')
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

export function getModelPickerDisplayName(model) {
  const modelId = String(model?.id || model?.name || '').trim();
  if (!modelId) return 'Unknown model';

  const isNotion2API = modelId.toLowerCase().startsWith('notion2api:')
    || model?.source === 'notion2api'
    || model?.provider?.toLowerCase() === 'notion2api';
  const verified = isNotion2API ? getNotion2APIModelMetadata(modelId) : null;
  if (verified) return verified.displayName;

  const shortName = getShortModelName(modelId);
  const rawName = getModelRawId(model);
  const leafName = rawName.includes('/') ? rawName.split('/').pop() : rawName;

  if (/^claude-/i.test(leafName) && !/^claude\b/i.test(shortName)) {
    return `Claude ${shortName}`;
  }

  return shortName || model.name || modelId;
}

export function normalizeModelSearchText(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export function modelSearchMatches(searchText, inputValue) {
  const query = normalizeModelSearchText(inputValue);
  if (!query) return true;

  const haystack = normalizeModelSearchText(searchText);
  const compactQuery = query.replace(/\s+/g, '');
  const compactHaystack = haystack.replace(/\s+/g, '');
  return haystack.includes(query) || compactHaystack.includes(compactQuery);
}

export function deduplicateModels(modelsList) {
  if (!Array.isArray(modelsList)) return [];
  const map = new Map();
  const getPriority = (modelId) => {
    if (!modelId) return 0;
    const id = modelId.toLowerCase();
    if (id.startsWith('custom:')) return 1;
    if (id.startsWith('openrouter:') || id.includes('/')) return 2;
    if (id.startsWith('ollama:')) return 3;
    return 4; // Direct connections have highest priority
  };

  for (const m of modelsList) {
    if (!m) continue;
    const key = m.name || m.id;
    const existing = map.get(key);
    if (!existing || getPriority(m.id) > getPriority(existing.id)) {
      map.set(key, m);
    }
  }

  return Array.from(map.values());
}

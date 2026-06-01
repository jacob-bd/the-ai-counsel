import openaiLogo from '../assets/icons/openai.svg';
import anthropicLogo from '../assets/icons/anthropic.svg';
import googleLogo from '../assets/icons/google.svg';
import mistralLogo from '../assets/icons/mistral.svg';
import ollamaLogo from '../assets/icons/ollama.svg';
import deepseekLogo from '../assets/icons/deepseek.svg';
import groqLogo from '../assets/icons/groq.svg';
import openrouterLogo from '../assets/icons/openrouter.svg';
import nvidiaLogo from '../assets/icons/nvidia.svg';
import customLogo from '../assets/icons/openai-compatible.svg';
import opencodeLogo from '../assets/icons/opencode.svg';

export const PROVIDER_CONFIG = {
  openai: { color: '#10a37f', label: 'OpenAI', logo: openaiLogo },
  anthropic: { color: '#d97757', label: 'Anthropic', logo: anthropicLogo },
  google: { color: '#4285f4', label: 'Google', logo: googleLogo },
  mistral: { color: '#fcd34d', label: 'Mistral', logo: mistralLogo },
  groq: { color: '#f55036', label: 'Groq', logo: groqLogo },
  ollama: { color: '#ffffff', label: 'Local', logo: ollamaLogo },
  deepseek: { color: '#4e61e6', label: 'DeepSeek', logo: deepseekLogo },
  nvidia: { color: '#76b900', label: 'NVIDIA', logo: nvidiaLogo },
  openrouter: { color: '#7f5af0', label: 'OpenRouter', logo: openrouterLogo },
  custom: { color: '#06b6d4', label: 'Custom', logo: customLogo },
  'opencode-zen': { color: '#211E1E', label: 'OpenCode Zen', logo: opencodeLogo },
  'opencode-go': { color: '#211E1E', label: 'OpenCode Go', logo: opencodeLogo },
  default: { color: '#888888', label: 'Model', logo: null, icon: '🤖' },
};

const PROVIDER_PREFIXES = [
  ['opencode-zen:', 'opencode-zen'],
  ['opencode-go:', 'opencode-go'],
  ['custom:', 'custom'],
  ['ollama:', 'ollama'],
  ['groq:', 'groq'],
  ['openai:', 'openai'],
  ['anthropic:', 'anthropic'],
  ['google:', 'google'],
  ['mistral:', 'mistral'],
  ['deepseek:', 'deepseek'],
  ['nvidia:', 'nvidia'],
];

export function getProviderInfo(modelId) {
  if (!modelId) return PROVIDER_CONFIG.default;
  const id = modelId.toLowerCase();

  if (id.startsWith('openrouter:') || id.includes('openrouter')) return PROVIDER_CONFIG.openrouter;

  for (const [prefix, key] of PROVIDER_PREFIXES) {
    if (id.startsWith(prefix)) return PROVIDER_CONFIG[key];
  }

  // Legacy unprefixed OpenRouter IDs (e.g. meta-llama/llama-3-70b-instruct)
  if (id.includes('/')) return PROVIDER_CONFIG.openrouter;

  if (id.includes('gpt') || id.includes('openai')) return PROVIDER_CONFIG.openai;
  if (id.includes('claude') || id.includes('anthropic')) return PROVIDER_CONFIG.anthropic;
  if (id.includes('gemini') || id.includes('google')) return PROVIDER_CONFIG.google;
  if (id.includes('mistral') || id.includes('mixtral')) return PROVIDER_CONFIG.mistral;
  if (id.includes('deepseek')) return PROVIDER_CONFIG.deepseek;

  return PROVIDER_CONFIG.default;
}

export function getModelDisplayName(modelId) {
  if (!modelId) return 'Choose model';
  if (modelId.startsWith('placeholder')) return 'Council Member';

  let name = modelId;
  name = name.replace(/:free$/, '');

  if (name.includes(':')) {
    name = name.split(':').slice(1).join(':');
  }

  if (name.includes('/')) {
    name = name.split('/').pop();
  }

  return name;
}

export function getCouncilLayoutClass(lineupCount, showChairman = true) {
  if (!showChairman) {
    if (lineupCount >= 8) return 'layout-8-members';
    if (lineupCount >= 5) return 'layout-5-members';
    return '';
  }

  if (lineupCount <= 2) return 'layout-2-members';
  if (lineupCount === 3) return 'layout-3-members';
  if (lineupCount === 4) return 'layout-4-members';
  if (lineupCount === 5) return 'layout-5-members';
  if (lineupCount === 6) return 'layout-6-members';
  if (lineupCount === 7) return 'layout-7-members';
  return 'layout-8-members';
}

export const LINEUP_COLS = 4;
const LINEUP_ROWS = 2;
export const LINEUP_SLOTS = LINEUP_COLS * LINEUP_ROWS;

/**
 * + Add starts top-right, moves left as members fill row 1.
 * When row 1 is full, + Add jumps to bottom-right (next to chairman) and moves left on row 2.
 */
export function getAddSlot(memberCount) {
  if (memberCount >= 8) return null;
  if (memberCount < LINEUP_COLS) {
    return LINEUP_COLS - 1 - memberCount;
  }
  return LINEUP_SLOTS - 1 - (memberCount - LINEUP_COLS);
}

/** Slot for member at index (members array is newest-first / prepended). */
export function getMemberSlot(memberIndex, memberCount) {
  if (memberCount <= LINEUP_COLS) {
    return LINEUP_COLS - 1 - memberIndex;
  }

  const row2Count = memberCount - LINEUP_COLS;

  if (memberIndex < row2Count) {
    return LINEUP_SLOTS - 1 - memberIndex;
  }

  return memberIndex - row2Count;
}

/** Draft picker opens in the current + Add slot. */
export function getDraftSlot(memberCount) {
  return getAddSlot(memberCount);
}

export function getMemberDisplayNumber(memberIndex, memberCount) {
  return memberCount - memberIndex;
}

export function slotToGridStyle(slot, minCol = 0) {
  return {
    gridColumn: (slot % LINEUP_COLS) - minCol + 1,
    gridRow: Math.floor(slot / LINEUP_COLS) + 1,
  };
}

const LINEUP_GAP = 14;
const LINEUP_CARD_WIDTH = 148;

/** Shrink the lineup grid to occupied columns so the block stays visually centered. */
export function getLineupGridMetrics(occupiedSlots) {
  if (!occupiedSlots?.length) {
    return {
      colCount: 1,
      minCol: 0,
      rowCount: 1,
      width: LINEUP_CARD_WIDTH,
    };
  }

  const cols = occupiedSlots.map((slot) => slot % LINEUP_COLS);
  const rows = occupiedSlots.map((slot) => Math.floor(slot / LINEUP_COLS));
  const minCol = Math.min(...cols);
  const maxCol = Math.max(...cols);
  const colCount = maxCol - minCol + 1;
  const rowCount = Math.max(...rows) - Math.min(...rows) + 1;

  return {
    colCount,
    minCol,
    rowCount,
    width: colCount * LINEUP_CARD_WIDTH + Math.max(0, colCount - 1) * LINEUP_GAP,
  };
}

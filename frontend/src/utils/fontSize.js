export const FONT_SIZE_OPTIONS = [
  { value: 'default', label: 'Default (slightly larger)', scale: 1.1 },
  { value: 'large', label: 'Large', scale: 1.5 },
  { value: 'xlarge', label: 'xLarge', scale: 2 },
];

const FONT_SIZE_SCALES = Object.fromEntries(
  FONT_SIZE_OPTIONS.map(({ value, scale }) => [value, scale]),
);

export function normalizeFontSize(value) {
  return Object.hasOwn(FONT_SIZE_SCALES, value) ? value : 'default';
}

export function getFontScale(value) {
  return FONT_SIZE_SCALES[normalizeFontSize(value)];
}

export function applyFontSize(value, root = document.documentElement) {
  const normalized = normalizeFontSize(value);
  root.dataset.fontSize = normalized;
  root.style.setProperty('--font-scale', String(getFontScale(normalized)));
  return normalized;
}

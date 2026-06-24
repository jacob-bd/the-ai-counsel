import { describe, expect, it } from 'vitest';
import {
  PROVIDER_CONFIG,
  getModelBrandInfo,
  getProviderInfo,
} from './councilGridUtils';

describe('council model branding', () => {
  it('keeps Notion2API as the transport label', () => {
    expect(getProviderInfo('notion2api:opal-quince-medium')).toBe(PROVIDER_CONFIG.notion2api);
  });

  it.each([
    ['notion2api:opal-quince-medium', PROVIDER_CONFIG.openai],
    ['notion2api:almond-croissant-low', PROVIDER_CONFIG.anthropic],
    ['notion2api:galette-medium-thinking', PROVIDER_CONFIG.google],
    ['notion2api:baseten-deepseek-v4-pro', PROVIDER_CONFIG.deepseek],
    ['notion2api:xigua-mochi-medium', PROVIDER_CONFIG.xai],
    ['notion2api:xinomavro-cake', PROVIDER_CONFIG.xai],
  ])('uses the underlying model brand for %s', (modelId, expectedBrand) => {
    expect(getModelBrandInfo(modelId)).toBe(expectedBrand);
  });

  it('falls back to the Notion2API icon for an unknown codename', () => {
    expect(getModelBrandInfo('notion2api:future-model')).toBe(PROVIDER_CONFIG.notion2api);
  });
});

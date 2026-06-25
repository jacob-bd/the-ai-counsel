import { describe, expect, it } from 'vitest';
import {
  VERIFIED_NOTION2API_MODELS,
  getModelPickerDisplayName,
  getModelPickerIdentifier,
  getModelRawId,
  getModelVisuals,
  getNotion2APIModelFamily,
  getNotion2APIModelMetadata,
  getShortModelName,
  modelMatchesStoredValue,
  modelSearchMatches,
} from './modelHelpers';

describe('verified Notion2API model labels', () => {
  it('contains one verified entry for each canonical Notion2API model', () => {
    expect(Object.keys(VERIFIED_NOTION2API_MODELS)).toHaveLength(21);
    expect(VERIFIED_NOTION2API_MODELS['acai-budino'].displayName).toBe('Fable 5');
    expect(VERIFIED_NOTION2API_MODELS['baseten-glm-5.2'].displayName).toBe('GLM 5.2');
  });

  it('maps exact Notion2API IDs to friendly names without changing the ID', () => {
    const model = {
      id: 'notion2api:apricot-sorbet-high',
      provider: 'Notion2API',
      source: 'notion2api',
    };

    expect(getModelPickerDisplayName(model)).toBe('Opus 4.7');
    expect(getShortModelName(model.id)).toBe('Opus 4.7');
    expect(getModelVisuals(model.id)).toMatchObject({
      name: 'Anthropic via Notion2API',
      short: 'Claude',
      icon: 'A',
    });
    expect(getModelRawId(model)).toBe('apricot-sorbet-high');
  });

  it('shows the public alias instead of the internal Notion codename', () => {
    const model = {
      id: 'notion2api:almond-croissant-low',
      provider: 'Notion2API',
      source: 'notion2api',
      public_name: 'claude-sonnet4.6',
    };

    expect(getModelPickerIdentifier(model)).toBe('claude-sonnet4.6');
  });

  it('prefers API-supplied display metadata for Notion2API models', () => {
    const model = {
      id: 'notion2api:baseten-glm-5.2',
      provider: 'Notion2API',
      source: 'notion2api',
      display_name: 'GLM 5.2',
    };

    expect(getModelPickerDisplayName(model)).toBe('GLM 5.2');
    expect(getNotion2APIModelFamily(model.id)).toBe('glm');
    expect(getModelVisuals(model.id)).toMatchObject({
      name: 'GLM via Notion2API',
      short: 'GLM',
    });
  });

  it('matches legacy saved aliases to the canonical Notion2API option', () => {
    const model = {
      id: 'notion2api:baseten-glm-5.2',
      provider: 'Notion2API',
      source: 'notion2api',
      public_name: 'glm-5.2',
      aliases: ['glm-5.2'],
    };

    expect(modelMatchesStoredValue(model, 'notion2api:baseten-glm-5.2')).toBe(true);
    expect(modelMatchesStoredValue(model, 'notion2api:glm-5.2')).toBe(true);
    expect(modelMatchesStoredValue(model, 'glm-5.2')).toBe(true);
    expect(modelMatchesStoredValue(model, 'notion2api:other-model')).toBe(false);
  });

  it('does not apply the registry to another provider using the same codename', () => {
    const model = {
      id: 'custom:apricot-sorbet-high',
      provider: 'Custom',
      source: 'custom',
    };

    expect(getModelPickerDisplayName(model)).toBe('Apricot Sorbet High');
  });

  it.each([
    ['notion2api:gemini-3.5flash', 'gemini', 'Google via Notion2API'],
    ['notion2api:grok-4.3', 'xai', 'xAI via Notion2API'],
    ['notion2api:deepseek-v4-pro', 'deepseek', 'DeepSeek via Notion2API'],
    ['notion2api:sonnet-4.6', 'anthropic', 'Anthropic via Notion2API'],
    ['notion2api:gpt-5.5', 'openai', 'OpenAI via Notion2API'],
  ])('infers model-family branding for friendly Notion2API IDs', (modelId, family, providerName) => {
    expect(getNotion2APIModelFamily(modelId)).toBe(family);
    expect(getModelVisuals(modelId)).toMatchObject({ name: providerName });
    expect(getModelVisuals(modelId).logo).toBeTruthy();
  });

  it('keeps unknown Notion2API IDs visible with a readable fallback label', () => {
    expect(getNotion2APIModelMetadata('notion2api:future-model')).toBeNull();
    expect(getModelPickerDisplayName({
      id: 'notion2api:future-model',
      provider: 'Notion2API',
    })).toBe('Future Model');
  });
});

describe('model picker search', () => {
  const searchText = 'Opus 4.7 apricot-sorbet-high notion2api:apricot-sorbet-high';

  it('matches the friendly display name', () => {
    expect(modelSearchMatches(searchText, 'opus 4.7')).toBe(true);
  });

  it('matches the exact raw ID with flexible punctuation', () => {
    expect(modelSearchMatches(searchText, 'apricot sorbet high')).toBe(true);
    expect(modelSearchMatches(searchText, 'apricotsorbethigh')).toBe(true);
  });

  it('rejects unrelated queries', () => {
    expect(modelSearchMatches(searchText, 'gemini 3.5')).toBe(false);
  });
});

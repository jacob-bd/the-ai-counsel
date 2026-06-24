import { describe, expect, it } from 'vitest';
import {
  VERIFIED_NOTION2API_MODELS,
  getModelPickerDisplayName,
  getModelRawId,
  getModelVisuals,
  getNotion2APIModelFamily,
  getNotion2APIModelMetadata,
  getShortModelName,
  modelSearchMatches,
} from './modelHelpers';

describe('verified Notion2API model labels', () => {
  it('contains the 19 verified models and excludes Fable 5', () => {
    expect(Object.keys(VERIFIED_NOTION2API_MODELS)).toHaveLength(19);
    expect(Object.keys(VERIFIED_NOTION2API_MODELS).some((id) => id.includes('fable5'))).toBe(false);
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

import { describe, expect, it } from 'vitest';
import {
  normalizeProviderEndpoint,
  shouldLoadCustomEndpointModels,
} from './providerSources';

describe('provider source selection', () => {
  it('normalizes equivalent endpoint URLs', () => {
    expect(normalizeProviderEndpoint(' HTTP://127.0.0.1:8120/v1/ '))
      .toBe('http://127.0.0.1:8120/v1');
  });

  it('suppresses custom models when dedicated Notion2API uses the same endpoint', () => {
    expect(shouldLoadCustomEndpointModels({
      custom_endpoint_url: 'http://127.0.0.1:8120/v1/',
      notion2api_base_url: 'http://127.0.0.1:8120/v1',
      notion2api_api_key_set: true,
      enabled_providers: { custom: true, notion2api: true },
    })).toBe(false);
  });

  it('keeps custom models when the endpoint differs or Notion2API is disabled', () => {
    expect(shouldLoadCustomEndpointModels({
      custom_endpoint_url: 'http://127.0.0.1:9000/v1',
      notion2api_base_url: 'http://127.0.0.1:8120/v1',
      notion2api_api_key_set: true,
      enabled_providers: { custom: true, notion2api: true },
    })).toBe(true);
    expect(shouldLoadCustomEndpointModels({
      custom_endpoint_url: 'http://127.0.0.1:8120/v1',
      notion2api_base_url: 'http://127.0.0.1:8120/v1',
      notion2api_api_key_set: true,
      enabled_providers: { custom: true, notion2api: false },
    })).toBe(true);
  });
});
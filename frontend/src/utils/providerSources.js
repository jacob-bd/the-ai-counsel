export function normalizeProviderEndpoint(value) {
  return String(value || '').trim().replace(/\/+$/, '').toLowerCase();
}

export function shouldLoadCustomEndpointModels(settings) {
  const enabled = settings?.enabled_providers || {};
  const customUrl = normalizeProviderEndpoint(settings?.custom_endpoint_url);
  if (!customUrl || enabled.custom === false) return false;

  const notionUrl = normalizeProviderEndpoint(settings?.notion2api_base_url);
  const notionActive = !!settings?.notion2api_api_key_set && enabled.notion2api !== false;

  return !(notionActive && notionUrl && customUrl === notionUrl);
}

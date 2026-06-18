const fs = require('fs');
const http = require('http');
const path = require('path');
const { app } = require('electron');

function tailFile(filePath, maxChars = 4000) {
  try {
    if (!fs.existsSync(filePath)) return '';
    const content = fs.readFileSync(filePath, 'utf8');
    return content.slice(Math.max(0, content.length - maxChars));
  } catch (error) {
    return `Unable to read ${path.basename(filePath)}: ${error.message}`;
  }
}

function requestText(url, options = {}) {
  return new Promise(resolve => {
    const headers = options.headers || {};
    const started = Date.now();
    const request = http.get(url, { headers, timeout: options.timeoutMs || 2500 }, response => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', chunk => {
        if (body.length < 12000) body += chunk;
      });
      response.on('end', () => {
        const statusOk = options.requireSuccess
          ? response.statusCode >= 200 && response.statusCode < 300
          : response.statusCode >= 200 && response.statusCode < 500;
        resolve({
          ok: statusOk,
          statusCode: response.statusCode,
          ms: Date.now() - started,
          body,
        });
      });
    });

    request.on('timeout', () => {
      request.destroy();
      resolve({ ok: false, error: 'Timed out' });
    });
    request.on('error', error => resolve({ ok: false, error: error.message }));
  });
}

function titleContains(body, expectedTitle) {
  if (!expectedTitle) return true;
  const match = /<title>(.*?)<\/title>/is.exec(body || '');
  return !!(match && match[1].includes(expectedTitle));
}

async function testService(name, url, options = {}) {
  const result = await requestText(url, options);
  const contentOk = options.expectedContent ? (result.body || '').includes(options.expectedContent) : true;
  const titleOk = titleContains(result.body, options.expectedTitle);
  return {
    name,
    url,
    ok: !!(result.ok && contentOk && titleOk),
    statusCode: result.statusCode || null,
    ms: result.ms || null,
    error: result.error || '',
    detail: result.error || (!contentOk ? `Missing expected content: ${options.expectedContent}` : (!titleOk ? `Missing expected title: ${options.expectedTitle}` : '')),
  };
}

async function getDiagnosticsStatus(rootDir, backendUrl, frontendUrl) {
  const LOG_DIR = path.join(app.getPath('userData'), 'logs');
  
  // Read settings
  let settings = {};
  try {
    const settingsPath = path.join(rootDir, 'data', 'settings.json');
    if (fs.existsSync(settingsPath)) {
      settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    }
  } catch (e) {
    // Ignore, settings can be empty
  }

  // Resolve Notion2API details
  const notion2apiUrlRaw = settings.notion2api_base_url || 'http://127.0.0.1:8120/v1';
  const notion2apiBaseUrl = notion2apiUrlRaw.replace(/\/v1\/?$/, '').replace(/\/+$/, '');
  const notion2apiHealthUrl = `${notion2apiBaseUrl}/health`;
  const notion2apiModelsUrl = `${notion2apiBaseUrl}/v1/models`;

  const notion2apiApiKey = process.env.NOTION2API_API_KEY || settings.notion2api_api_key || '';
  
  // Test services
  const services = await Promise.all([
    testService('LLM Council Backend', `${backendUrl}/api/health`),
    testService('LLM Council Frontend', frontendUrl),
    testService('Notion2API Health', notion2apiHealthUrl, { expectedContent: 'status' }),
    notion2apiApiKey
      ? testService('Notion2API Models', notion2apiModelsUrl, { headers: { Authorization: `Bearer ${notion2apiApiKey}` }, requireSuccess: true })
      : Promise.resolve({ name: 'Notion2API Models', url: notion2apiModelsUrl, ok: false, detail: 'notion2api_api_key is missing' }),
  ]);

  // Test capabilities
  const [settingsExportRes, askRes, healthRes] = await Promise.all([
    requestText(`${backendUrl}/api/settings/export`),
    requestText(`${backendUrl}/api/ask`),
    requestText(`${backendUrl}/api/health`),
  ]);

  const capabilities = {
    settings: services.find(s => s.name === 'LLM Council Backend')?.ok || false,
    settingsExport: settingsExportRes.ok,
    settingsImport: settingsExportRes.ok,
    ask: askRes.statusCode !== 404,
    health: healthRes.ok,
  };

  const hasNotion2Api = !!settings.notion2api_auto_launch;

  return {
    checkedAt: new Date().toISOString(),
    config: {
      repoRoot: rootDir,
      configPath: path.join(rootDir, 'data', 'settings.json'),
      logsDir: LOG_DIR,
      councilBackendUrl: backendUrl,
      councilUiUrl: frontendUrl,
      notion2apiBaseUrl: notion2apiBaseUrl,
      notion2apiApiKey: notion2apiApiKey ? 'Present (Redacted)' : 'None',
      notion2apiAutoLaunch: hasNotion2Api,
    },
    capabilities,
    services,
    logs: {
      desktop: tailFile(path.join(LOG_DIR, 'desktop.log')),
      backend: tailFile(path.join(LOG_DIR, 'backend.log')),
      frontend: tailFile(path.join(LOG_DIR, 'frontend.log')),
      notion2api: tailFile(path.join(LOG_DIR, 'notion2api.log')),
    },
  };
}

module.exports = {
  getDiagnosticsStatus,
};

const api = window.notion2CouncilDiagnostics;
let lastData = null;
let activeLog = 'desktop';

const checkedAt = document.getElementById('checkedAt');
const servicesEl = document.getElementById('services');
const capabilitiesEl = document.getElementById('capabilities');
const configEl = document.getElementById('config');
const logEl = document.getElementById('log');
const statusEl = document.getElementById('status');

function setStatus(text) {
  statusEl.textContent = text || '';
}

function formatValue(value) {
  if (value === undefined || value === null || value === '') return '-';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

function renderDefinitionList(el, entries) {
  el.textContent = '';
  for (const [key, value] of entries) {
    const dt = document.createElement('dt');
    dt.textContent = key;
    const dd = document.createElement('dd');
    dd.textContent = formatValue(value);
    el.append(dt, dd);
  }
}

function renderServices(services) {
  servicesEl.textContent = '';
  for (const service of services || []) {
    const row = document.createElement('div');
    row.className = 'service';

    const dot = document.createElement('div');
    dot.className = `dot ${service.ok ? 'ok' : 'bad'}`;

    const body = document.createElement('div');
    const name = document.createElement('div');
    name.className = 'name';
    name.textContent = service.name;
    const url = document.createElement('div');
    url.className = 'url';
    url.textContent = service.detail ? `${service.url} - ${service.detail}` : service.url;
    body.append(name, url);

    const pill = document.createElement('div');
    pill.className = 'pill';
    pill.textContent = service.statusCode ? `${service.statusCode} / ${service.ms}ms` : 'offline';

    row.append(dot, body, pill);
    servicesEl.append(row);
  }
}

function render(data) {
  lastData = data;
  checkedAt.textContent = `Last checked: ${new Date(data.checkedAt).toLocaleString()}`;
  renderServices(data.services);

  renderDefinitionList(capabilitiesEl, [
    ['/api/health', data.capabilities?.health ? 'Healthy' : 'Unreachable'],
    ['/api/settings', data.capabilities?.settings ? 'Available' : 'Unavailable'],
    ['/api/settings/export', data.capabilities?.settingsExport ? 'Supported' : 'Not Supported'],
    ['/api/settings/import', data.capabilities?.settingsImport ? 'Supported' : 'Not Supported'],
    ['/api/ask', data.capabilities?.ask ? 'Supported' : 'Not Supported'],
  ]);

  renderDefinitionList(configEl, [
    ['Repository Root', data.config.repoRoot],
    ['Configuration Path', data.config.configPath],
    ['Logs Folder', data.config.logsDir],
    ['Council Backend URL', data.config.councilBackendUrl],
    ['Council UI URL', data.config.councilUiUrl],
    ['Notion2API Base URL', data.config.notion2apiBaseUrl],
    ['Notion2API API Key', data.config.notion2apiApiKey],
    ['Notion2API Auto-Launch', data.config.notion2apiAutoLaunch ? 'Enabled' : 'Disabled'],
  ]);

  logEl.textContent = data.logs?.[activeLog] || 'No log output.';
}

async function refresh() {
  setStatus('Checking services...');
  try {
    const status = await api.status();
    render(status);
    setStatus('Ready');
  } catch (error) {
    setStatus(`Diagnostics status check error: ${error.message}`);
  }
}

document.getElementById('refresh').addEventListener('click', refresh);
document.getElementById('start').addEventListener('click', async () => {
  setStatus('Starting stack...');
  try {
    await api.start();
    setTimeout(refresh, 2000);
  } catch (err) {
    setStatus(`Failed to start stack: ${err.message}`);
  }
});
document.getElementById('stop').addEventListener('click', async () => {
  setStatus('Stopping stack...');
  try {
    await api.stop();
    setTimeout(refresh, 2000);
  } catch (err) {
    setStatus(`Failed to stop stack: ${err.message}`);
  }
});
document.getElementById('openUi').addEventListener('click', () => {
  api.openCouncil().catch(err => setStatus(`Could not open council: ${err.message}`));
});
document.getElementById('openDocs').addEventListener('click', () => {
  api.openDocs().catch(err => setStatus(`Could not open docs: ${err.message}`));
});
document.getElementById('openLogs').addEventListener('click', () => {
  api.openLogs().catch(err => setStatus(`Could not open logs folder: ${err.message}`));
});

document.querySelectorAll('[data-log]').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('[data-log]').forEach(item => item.classList.remove('active'));
    button.classList.add('active');
    activeLog = button.dataset.log;
    if (lastData) {
      logEl.textContent = lastData.logs?.[activeLog] || 'No log output.';
    }
  });
});

refresh();

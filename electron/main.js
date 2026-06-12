const { app, BrowserWindow, Menu, Tray, nativeImage, shell, dialog } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');

const APP_NAME = 'The AI Counsel';
const ROOT_DIR = app.isPackaged
  ? path.join(process.resourcesPath, 'app.asar.unpacked')
  : path.join(__dirname, '..');
const FRONTEND_DIR = path.join(ROOT_DIR, 'frontend');
const LOG_DIR = path.join(app.getPath('userData'), 'logs');
const APP_ICON_PNG = path.join(__dirname, 'icon.png');
const APP_ICON_ICO = path.join(__dirname, 'icon.ico');
const BACKEND_URL = process.env.AI_COUNSEL_BACKEND_URL || 'http://127.0.0.1:8001';
const FRONTEND_URL = process.env.AI_COUNSEL_FRONTEND_URL || 'http://127.0.0.1:5173';
const HEALTH_URL = `${BACKEND_URL}/api/health`;

if (process.platform === 'darwin') {
  process.env.PATH = `/usr/local/bin:/opt/homebrew/bin:${process.env.PATH}`;
}

let mainWindow;
let tray;
let backendProcess;
let frontendProcess;
let providerProcess;
let isQuitting = false;

function ensureLogDir() {
  fs.mkdirSync(LOG_DIR, { recursive: true });
}

function log(message) {
  ensureLogDir();
  const line = `[${new Date().toISOString()}] ${message}\n`;
  fs.appendFileSync(path.join(LOG_DIR, 'desktop.log'), line, 'utf8');
}

function appendProcessLog(name, data) {
  ensureLogDir();
  fs.appendFileSync(path.join(LOG_DIR, `${name}.log`), data.toString(), 'utf8');
}

function commandForUv() {
  return process.platform === 'win32' ? 'uv.exe' : 'uv';
}

function commandForNpm() {
  return process.platform === 'win32' ? 'npm.cmd' : 'npm';
}

function expandWindowsCommand(command, args) {
  if (process.platform !== 'win32' || !/\.(bat|cmd)$/i.test(command)) {
    return { command, args };
  }

  const comspec = process.env.ComSpec || 'C:\\Windows\\System32\\cmd.exe';
  return {
    command: comspec,
    args: ['/d', '/s', '/c', command, ...args],
  };
}

function spawnLogged(name, command, args, options = {}) {
  const cwd = options.cwd || ROOT_DIR;
  const env = { ...process.env, ...(options.env || {}) };
  const { command: spawnCommand, args: spawnArgs } = expandWindowsCommand(command, args);

  log(`Starting ${name}: ${spawnCommand} ${spawnArgs.join(' ')} (cwd=${cwd})`);

  let child;
  try {
    child = spawn(spawnCommand, spawnArgs, {
      cwd,
      windowsHide: false,
      shell: false,
      detached: process.platform !== 'win32',
      env,
    });
  } catch (error) {
    log(`${name} failed to spawn: ${error.stack || error.message}`);
    throw error;
  }

  child.stdout.on('data', data => appendProcessLog(name, data));
  child.stderr.on('data', data => appendProcessLog(name, data));
  child.on('error', error => log(`${name} failed to start: ${error.stack || error.message}`));
  child.on('exit', (code, signal) => log(`${name} exited with code=${code} signal=${signal}`));
  return child;
}


function getJson(url, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, res => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode} for ${url}`));
          return;
        }
        try {
          resolve(JSON.parse(body || '{}'));
        } catch (error) {
          reject(error);
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      reject(new Error(`Timed out waiting for ${url}`));
    });
  });
}


function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function managedStatusUrl() {
  return BACKEND_URL + '/api/' + 'notion2api' + '/status';
}

async function getManagedStatus() {
  try {
    return await getJson(managedStatusUrl(), 5000);
  } catch (error) {
    log('managed provider status check failed: ' + error.message);
    return { running: false, error: error.message };
  }
}


function providerBaseUrl(settings = {}) {
  return (settings.notion2api_base_url || 'http://127.0.0.1:8120/v1').replace(/\/$/, '');
}

function providerRootCandidates(settings = {}) {
  const roots = [
    settings.notion2api_root,
    path.join(ROOT_DIR, 'vendor', 'notion2api'),
    path.join(path.dirname(ROOT_DIR), 'notion2api'),
  ];
  if (process.platform === 'win32') {
    roots.push('X:\\Code\\notion2api');
  }
  return roots.filter(Boolean);
}

function resolveProviderRoot(settings = {}) {

  for (const root of providerRootCandidates(settings)) {
    const markerPath = path.join(root, 'app', 'server' + '.py');
    if (fs.existsSync(markerPath)) {
      return root;
    }
  }
  return null;
}


function providerPython(root) {
  const venvPython = process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
  return fs.existsSync(venvPython) ? venvPython : 'python';
}

function providerListenArgs(settings = {}) {
  const parsed = new URL(providerBaseUrl(settings));
  return {
    host: parsed.hostname || '127.0.0.1',
    port: String(parsed.port || (parsed.protocol === 'https:' ? 443 : 80)),
  };
}


function startProvider(settings = {}) {
  if (providerProcess && providerProcess.pid && !providerProcess.killed) {
    return providerProcess;
  }
  const root = resolveProviderRoot(settings);
  if (!root) {
    log('Notion2API auto-launch skipped: no checkout root found');
    return null;
  }
  const listen = providerListenArgs(settings);
  providerProcess = spawnLogged('notion2api', providerPython(root), ['-m', 'uvicorn', 'app.server:app', '--host', listen.host, '--port', listen.port], {
    cwd: root,
    env: {
      APP_MODE: 'standard',
      HOST: listen.host,
    },
  });
  return providerProcess;
}


function stopProvider() {
  stopProcess(providerProcess, 'notion2api');
  providerProcess = null;
}

async function waitForManagedStatus(timeoutMs = 45000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const status = await getManagedStatus();
    if (status.running) return status;
    await delay(750);
  }
  throw new Error('Timed out waiting for Notion2API status');
}

async function startProviderFromMenu() {
  const settings = await getJson(`${BACKEND_URL}/api/settings`, 5000);
  startProvider(settings);
}


async function ensureProviderAutoLaunch() {
  let settings;
  try {
    settings = await getJson(`${BACKEND_URL}/api/settings`, 5000);
  } catch (error) {
    log(`Could not read Notion2API settings: ${error.message}`);
    return;
  }
  if (!settings.notion2api_auto_launch) {
    log('Notion2API auto-launch disabled');
    return;
  }
  const status = await getManagedStatus();
  if (status.running) {
    log(`Notion2API already running (${status.model_count || 0} models)`);
    return;
  }
  startProvider(settings);
  await waitForManagedStatus(45000);
}

function waitForUrl(url, timeoutMs = 90000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      const req = http.get(url, res => {
        res.resume();
        if (res.statusCode >= 200 && res.statusCode < 500) {
          resolve(true);
          return;
        }
        retry();
      });
      req.on('error', retry);
      req.setTimeout(2500, () => {
        req.destroy();
        retry();
      });
    };

    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error(`Timed out waiting for ${url}`));
        return;
      }
      setTimeout(check, 500);
    };

    check();
  });
}

function startStack() {
  if (!backendProcess || backendProcess.killed) {
    backendProcess = spawnLogged('backend', commandForUv(), ['run', 'python', '-m', 'backend.main'], {
      cwd: ROOT_DIR,
      env: {
        LLM_COUNCIL_BIND_HOST: process.env.LLM_COUNCIL_BIND_HOST || '127.0.0.1',
      },
    });
  }

  if (!frontendProcess || frontendProcess.killed) {
    frontendProcess = spawnLogged('frontend', commandForNpm(), ['run', 'dev', '--', '--host', '127.0.0.1'], {
      cwd: FRONTEND_DIR,
      env: {
        VITE_API_URL: BACKEND_URL,
      },
    });
  }
}

function stopProcess(child, name) {
  if (!child || !child.pid || child.killed) return;
  try {
    log(`Stopping ${name}`);
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
    } else {
      process.kill(-child.pid, 'SIGTERM');
    }
  } catch (error) {
    log(`Failed to stop ${name}: ${error.message}`);
  }
}

function stopStack() {
  stopProcess(frontendProcess, 'frontend');
  stopProcess(backendProcess, 'backend');
  stopProvider();
}

function appIconPath() {
  if (process.platform === 'win32' && fs.existsSync(APP_ICON_ICO)) return APP_ICON_ICO;
  if (fs.existsSync(APP_ICON_PNG)) return APP_ICON_PNG;
  return undefined;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 950,
    minWidth: 1000,
    minHeight: 700,
    title: APP_NAME,
    show: false,
    icon: appIconPath(),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.on('close', event => {
    if (!isQuitting) {
      event.preventDefault();
      hideToTray();
    }
  });

  mainWindow.on('minimize', event => {
    if (!isQuitting) {
      event.preventDefault();
      hideToTray();
    }
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());
  return mainWindow;
}

function hideToTray() {
  if (!mainWindow) return;
  mainWindow.hide();
}

function showWindow() {
  if (!mainWindow) createWindow();
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

function reloadApp() {
  if (mainWindow) mainWindow.loadURL(FRONTEND_URL);
}

function openLogs() {
  ensureLogDir();
  shell.openPath(LOG_DIR);
}

function showAbout() {
  dialog.showMessageBox(mainWindow || null, {
    type: 'info',
    title: `About ${APP_NAME}`,
    message: APP_NAME,
    detail: `Desktop wrapper for The AI Counsel.\n\nBackend: ${BACKEND_URL}\nFrontend: ${FRONTEND_URL}\n\nElectron: ${process.versions.electron}\nNode: ${process.versions.node}\nChrome: ${process.versions.chrome}`,
    buttons: ['OK'],
  });
}

function menuTemplate() {
  return [
    {
      label: APP_NAME,
      submenu: [
        { label: 'Show / Hide', click: () => (mainWindow && mainWindow.isVisible() ? hideToTray() : showWindow()) },
        { label: 'Minimize to Tray', click: hideToTray },
        { label: 'Reload UI', click: reloadApp },
        { type: 'separator' },
        { label: 'Open in Browser', click: () => shell.openExternal(FRONTEND_URL) },
        { label: 'Open Backend Health', click: () => shell.openExternal(HEALTH_URL) },
        { label: 'Open Notion2API Status', click: () => shell.openExternal(BACKEND_URL + '/api/' + 'notion2api' + '/status') },
        { label: 'Open Logs', click: openLogs },
        { type: 'separator' },
        { label: 'Start Stack', click: startStack },
        { label: 'Start Notion2API', click: () => startProviderFromMenu().catch(error => log('Start Notion2API failed: ' + error.message)) },
        { label: 'Stop Notion2API', click: stopProvider },
        { label: 'Stop Stack', click: stopStack },
        { type: 'separator' },
        { label: `About ${APP_NAME}`, click: showAbout },
        { label: 'Quit', click: () => app.quit() },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
      ],
    },
  ];
}

function createTray() {
  const iconPath = APP_ICON_PNG;
  const icon = fs.existsSync(iconPath) ? nativeImage.createFromPath(iconPath) : nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip(APP_NAME);
  tray.setContextMenu(Menu.buildFromTemplate(menuTemplate()[0].submenu));
  tray.on('click', () => (mainWindow && mainWindow.isVisible() ? hideToTray() : showWindow()));
}

async function startDesktopApp() {
  log(`${APP_NAME} desktop starting`);
  Menu.setApplicationMenu(Menu.buildFromTemplate(menuTemplate()));
  createWindow();
  createTray();

  try {
    startStack();
    await waitForUrl(HEALTH_URL, 90000);
    await ensureProviderAutoLaunch();
    await waitForUrl(FRONTEND_URL, 90000);
    await mainWindow.loadURL(FRONTEND_URL);
  } catch (error) {
    log(`Failed to load UI: ${error.stack || error.message}`);
    await mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
      <h1>The AI Counsel desktop launcher could not start the UI.</h1>
      <p>${error.message}</p>
      <p>Check logs at: ${LOG_DIR}</p>
      <p>Backend: ${HEALTH_URL}</p>
      <p>Frontend: ${FRONTEND_URL}</p>
    `)}`);
  }
}

app.whenReady().then(startDesktopApp).catch(error => {
  log(`Fatal desktop startup error: ${error.stack || error.message}`);
  dialog.showErrorBox(`${APP_NAME} startup failed`, error.message);
});

app.on('activate', showWindow);

app.on('before-quit', event => {
  if (isQuitting) return;
  isQuitting = true;
  event.preventDefault();
  stopStack();
  setTimeout(() => {
    app.removeAllListeners('before-quit');
    app.quit();
  }, 1500);
});

app.on('window-all-closed', () => {
  // Keep tray app alive until explicit Quit.
});

process.on('uncaughtException', error => {
  log(`Uncaught exception: ${error.stack || error.message}`);
});

process.on('unhandledRejection', error => {
  log(`Unhandled rejection: ${error.stack || error.message || error}`);
});

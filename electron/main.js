const { app, BrowserWindow, Menu, Tray, nativeImage, shell, dialog, globalShortcut, clipboard, ipcMain } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');

const { readHotkeys, writeHotkeys, defaultHotkeys, getHotkeyConfigPath } = require('./lib/config');
const { openHotkeySettings } = require('./windows/hotkeys');
const { openDiagnostics } = require('./windows/diagnostics');
const { getDiagnosticsStatus } = require('./lib/diagnostics');

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


function readSettingsFile() {
  try {
    const settingsPath = path.join(ROOT_DIR, 'data', 'settings.json');
    if (fs.existsSync(settingsPath)) {
      return JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    }
  } catch (e) {
    log(`Failed to read settings.json: ${e.message}`);
  }
  return {};
}

function updateEnvFile(filePath, keyName, value) {
  try {
    const parentDir = path.dirname(filePath);
    if (!fs.existsSync(parentDir)) {
      fs.mkdirSync(parentDir, { recursive: true });
    }
    let content = '';
    if (fs.existsSync(filePath)) {
      content = fs.readFileSync(filePath, 'utf8');
    }
    const regex = new RegExp(`^\\s*${keyName}\\s*=.*$`, 'm');
    if (regex.test(content)) {
      content = content.replace(regex, `${keyName}=${value}`);
    } else {
      content = content.trim() + `\n${keyName}=${value}\n`;
    }
    fs.writeFileSync(filePath, content, 'utf8');
    log(`Updated ${path.basename(filePath)} with ${keyName}`);
  } catch (e) {
    log(`Failed to update ${path.basename(filePath)}: ${e.message}`);
  }
}

function resolveNotionApiKey(settings = {}) {
  if (process.env.NOTION2API_API_KEY) {
    return process.env.NOTION2API_API_KEY;
  }
  if (settings && settings.notion2api_api_key) {
    return settings.notion2api_api_key;
  }
  // Try reading from .env file to keep it stable
  try {
    const envPath = path.join(ROOT_DIR, '.env');
    if (fs.existsSync(envPath)) {
      const content = fs.readFileSync(envPath, 'utf8');
      const match = content.match(/^\s*NOTION2API_API_KEY\s*=\s*(.+)$/m);
      if (match && match[1].trim()) {
        return match[1].trim();
      }
    }
  } catch (e) {
    log(`Failed to read API key from backend .env: ${e.message}`);
  }
  if (!global.sessionNotionApiKey) {
    try {
      const crypto = require('crypto');
      global.sessionNotionApiKey = 'n2api_' + crypto.randomBytes(24).toString('hex');
    } catch (e) {
      log(`Failed to generate random API key: ${e.message}`);
      global.sessionNotionApiKey = 'n2api_default_session_key';
    }
  }
  return global.sessionNotionApiKey;
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
  const notionApiKey = resolveNotionApiKey(settings);
  if (notionApiKey) {
    const providerEnvPath = path.join(root, '.env');
    updateEnvFile(providerEnvPath, 'API_KEY', notionApiKey);
  }
  const listen = providerListenArgs(settings);
  const providerEnv = {
    APP_MODE: 'standard',
    HOST: listen.host,
  };
  if (notionApiKey) {
    providerEnv.API_KEY = notionApiKey;
  }
  providerProcess = spawnLogged('notion2api', providerPython(root), ['-m', 'uvicorn', 'app.server:app', '--host', listen.host, '--port', listen.port], {
    cwd: root,
    env: providerEnv,
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
  const settings = readSettingsFile();
  const notionApiKey = resolveNotionApiKey(settings);
  log(`Starting stack, resolved Notion2API API key: ${notionApiKey ? notionApiKey.substring(0, 10) + '...' : 'none'}`);

  if (notionApiKey) {
    const backendEnvPath = path.join(ROOT_DIR, '.env');
    updateEnvFile(backendEnvPath, 'NOTION2API_API_KEY', notionApiKey);
  }

  if (!backendProcess || backendProcess.killed) {
    const backendEnv = {
      LLM_COUNCIL_BIND_HOST: process.env.LLM_COUNCIL_BIND_HOST || '127.0.0.1',
    };
    if (notionApiKey) {
      backendEnv.NOTION2API_API_KEY = notionApiKey;
    }
    backendProcess = spawnLogged('backend', commandForUv(), ['run', 'python', '-m', 'backend.main'], {
      cwd: ROOT_DIR,
      env: backendEnv,
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
      preload: path.join(__dirname, 'preload.js'),
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

function restartApplication() {
  log('Restarting application...');
  isQuitting = true;
  stopStack();
  setTimeout(() => {
    app.relaunch();
    app.exit(0);
  }, 1000);
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

// Browser Interaction Helpers
async function focusChatInput(text, submit = false) {
  if (!mainWindow) return false;
  const safeText = JSON.stringify(text || '');
  const shouldSubmit = JSON.stringify(!!submit);
  return mainWindow.webContents.executeJavaScript(`
    (() => {
      const selectors = [
        'textarea.message-input',
        'textarea.council-message-input',
        'textarea#chat-input',
        '.chat-container textarea.message-input',
        '.input-area textarea',
        'textarea'
      ];

      let input = null;
      for (const selector of selectors) {
        const found = document.querySelector(selector);
        if (found && found.offsetParent !== null && !found.disabled) {
          input = found;
          break;
        }
      }

      if (!input) return false;

      const text = ${safeText};
      input.focus();

      if (text) {
        const descriptor = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype,
          'value'
        );
        const setter = descriptor && descriptor.set;

        if (setter) {
          setter.call(input, text);
        } else {
          input.value = text;
        }

        input.dispatchEvent(new InputEvent('input', {
          bubbles: true,
          inputType: 'insertText',
          data: text
        }));
        input.dispatchEvent(new Event('change', { bubbles: true }));

        if (${shouldSubmit}) {
          input.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Enter',
            code: 'Enter',
            bubbles: true
          }));
        }
      }

      return true;
    })();
  `).catch(error => {
    log(`focusChatInput failed: ${error.message}`);
    return false;
  });
}

async function ensureChatInputReady(type = 'council') {
  if (!mainWindow) return false;
  const buttonSelector = type === 'advisors' ? '.sidebar-action-btn--advisors' : '.sidebar-action-btn--council';
  const searchRegex = type === 'advisors' ? /new\s+advisors/i : /new\s+council|new\s+chat/i;
  const searchRegexStr = searchRegex.toString();

  return mainWindow.webContents.executeJavaScript(`
    (async () => {
      const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
      const hasInput = () => !!document.querySelector('textarea.message-input, .input-area textarea, textarea');

      if (hasInput()) return true;

      const buttons = Array.from(document.querySelectorAll('button'));
      const newChatButton = document.querySelector(${JSON.stringify(buttonSelector)}) || 
                            buttons.find(btn => ${searchRegexStr}.test(btn.textContent || ''));

      if (newChatButton && !newChatButton.disabled) {
        newChatButton.click();
        for (let i = 0; i < 40; i += 1) {
          if (hasInput()) return true;
          await sleep(250);
        }
      }

      return hasInput();
    })();
  `).catch(error => {
    log(`ensureChatInputReady failed: ${error.message}`);
    return false;
  });
}

async function openChat() {
  showWindow();
  try {
    const ready = await ensureChatInputReady('council');
    if (!ready) {
      log('Could not open chat input');
      return false;
    }
    return focusChatInput('');
  } catch (error) {
    log(`Could not open chat: ${error.message}`);
    return false;
  }
}

async function openChatWithClipboard() {
  const text = clipboard.readText() || '';
  const opened = await openChat();
  if (!opened) return;
  const injected = await focusChatInput(text);
  if (!injected) {
    log('Clipboard to Chat failed: chat input was not found');
  }
}

async function openNewDebate() {
  showWindow();
  try {
    const ready = await ensureChatInputReady('council');
    if (!ready) {
      log('Could not open new debate input');
      return false;
    }
    return focusChatInput('');
  } catch (error) {
    log(`Could not open new debate: ${error.message}`);
    return false;
  }
}

async function openNewDebateWithClipboard() {
  const text = clipboard.readText() || '';
  showWindow();
  try {
    const ready = await mainWindow.webContents.executeJavaScript(`
      (async () => {
        const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
        const buttons = Array.from(document.querySelectorAll('button'));
        const newChatButton = document.querySelector('.sidebar-action-btn--council') || 
                              buttons.find(btn => /new\\s+council|new\\s+chat/i.test(btn.textContent || ''));
        if (newChatButton && !newChatButton.disabled) {
          newChatButton.click();
          for (let i = 0; i < 40; i += 1) {
            if (document.querySelector('textarea')) return true;
            await sleep(250);
          }
        }
        return !!document.querySelector('textarea');
      })();
    `);
    if (!ready) {
      log('Could not open new debate input');
      return;
    }
    const injected = await focusChatInput(text);
    if (!injected) {
      log('Clipboard to New Debate failed: chat input was not found');
    }
  } catch (error) {
    log(`Could not open new debate: ${error.message}`);
  }
}

async function openNewAdvisors() {
  showWindow();
  try {
    const ready = await ensureChatInputReady('advisors');
    if (!ready) {
      log('Could not open new advisors input');
      return false;
    }
    return focusChatInput('');
  } catch (error) {
    log(`Could not open new advisors: ${error.message}`);
    return false;
  }
}

async function openNewAdvisorsWithClipboard() {
  const text = clipboard.readText() || '';
  showWindow();
  try {
    const ready = await mainWindow.webContents.executeJavaScript(`
      (async () => {
        const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
        const buttons = Array.from(document.querySelectorAll('button'));
        const newChatButton = document.querySelector('.sidebar-action-btn--advisors') || 
                              buttons.find(btn => /new\\s+advisors/i.test(btn.textContent || ''));
        if (newChatButton && !newChatButton.disabled) {
          newChatButton.click();
          for (let i = 0; i < 40; i += 1) {
            if (document.querySelector('textarea')) return true;
            await sleep(250);
          }
        }
        return !!document.querySelector('textarea');
      })();
    `);
    if (!ready) {
      log('Could not open new advisors input');
      return;
    }
    const injected = await focusChatInput(text);
    if (!injected) {
      log('Clipboard to New Advisors failed: chat input was not found');
    }
  } catch (error) {
    log(`Could not open new advisors: ${error.message}`);
  }
}

function getNotion2ApiBrowserUrl() {
  let url = 'http://127.0.0.1:8120';
  try {
    const settingsPath = path.join(ROOT_DIR, 'data', 'settings.json');
    if (fs.existsSync(settingsPath)) {
      const data = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
      if (data && data.notion2api_base_url) {
        url = data.notion2api_base_url;
      }
    }
  } catch (err) {
    log(`Error reading settings for notion2api_base_url: ${err.message}`);
  }
  return url.replace(/\/v1\/?$/, '').replace(/\/+$/, '');
}

async function openNotion2ApiBrowser() {
  const url = getNotion2ApiBrowserUrl();
  log(`Opening Notion2API in browser: ${url}`);
  try {
    await shell.openExternal(url);
  } catch (error) {
    log(`Failed to open Notion2API browser: ${error.message}`);
  }
}

function menuTemplate() {
  const hotkeys = readHotkeys();
  return [
    {
      label: APP_NAME,
      submenu: [
        { label: 'Show / Hide', accelerator: hotkeys.toggleWindow, click: () => (mainWindow && mainWindow.isVisible() ? hideToTray() : showWindow()) },
        { label: 'Minimize to Tray', click: hideToTray },
        { label: 'Open Chat', accelerator: hotkeys.openChat, click: openChat },
        { label: 'New Debate', accelerator: hotkeys.openNewDebate, click: openNewDebate },
        { label: 'New Advisors', accelerator: hotkeys.openNewAdvisors, click: openNewAdvisors },
        { label: 'Clipboard to Chat', accelerator: hotkeys.clipboardToChat, click: openChatWithClipboard },
        { label: 'Clipboard to New Debate', accelerator: hotkeys.clipboardToNewDebate, click: openNewDebateWithClipboard },
        { label: 'Clipboard to New Advisors', accelerator: hotkeys.clipboardToNewAdvisors, click: openNewAdvisorsWithClipboard },
        { label: 'Open Notion2API Browser', accelerator: hotkeys.openNotion2Api, click: openNotion2ApiBrowser },
        { type: 'separator' },
        { label: 'Hotkey Settings', accelerator: hotkeys.openHotkeySettings, click: () => openHotkeySettings(mainWindow) },
        { label: 'Diagnostics', click: () => openDiagnostics(mainWindow) },
        { type: 'separator' },
        { label: 'Reload UI', click: reloadApp },
        { label: 'Restart Application', click: restartApplication },
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

function updateApplicationMenu() {
  Menu.setApplicationMenu(Menu.buildFromTemplate(menuTemplate()));
  if (tray) {
    tray.setContextMenu(Menu.buildFromTemplate(menuTemplate()[0].submenu));
  }
}

function createTray() {
  const iconPath = APP_ICON_PNG;
  const icon = fs.existsSync(iconPath) ? nativeImage.createFromPath(iconPath) : nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip(APP_NAME);
  tray.setContextMenu(Menu.buildFromTemplate(menuTemplate()[0].submenu));
  tray.on('click', () => (mainWindow && mainWindow.isVisible() ? hideToTray() : showWindow()));
}

function registerHotkeys() {
  globalShortcut.unregisterAll();
  const hotkeys = readHotkeys();
  const registrations = [];
  const bind = (name, accelerator, handler) => {
    if (!accelerator) return;
    const ok = globalShortcut.register(accelerator, handler);
    registrations.push({ name, accelerator, ok });
    if (!ok) log(`Failed to register hotkey ${name}: ${accelerator}`);
  };

  bind('toggleWindow', hotkeys.toggleWindow, () => (mainWindow && mainWindow.isVisible() && mainWindow.isFocused() ? mainWindow.hide() : showWindow()));
  bind('openChat', hotkeys.openChat, openChat);
  bind('openNewDebate', hotkeys.openNewDebate, openNewDebate);
  bind('openNewAdvisors', hotkeys.openNewAdvisors, openNewAdvisors);
  bind('clipboardToChat', hotkeys.clipboardToChat, openChatWithClipboard);
  bind('clipboardToNewDebate', hotkeys.clipboardToNewDebate, openNewDebateWithClipboard);
  bind('clipboardToNewAdvisors', hotkeys.clipboardToNewAdvisors, openNewAdvisorsWithClipboard);
  bind('openNotion2Api', hotkeys.openNotion2Api, openNotion2ApiBrowser);
  bind('openHotkeySettings', hotkeys.openHotkeySettings, () => openHotkeySettings(mainWindow));

  return registrations;
}

// IPC Handlers for Hotkeys
ipcMain.handle('hotkeys:get', () => ({ 
  defaults: defaultHotkeys, 
  current: readHotkeys(), 
  configPath: getHotkeyConfigPath() 
}));

ipcMain.handle('hotkeys:save', (_event, hotkeys) => {
  writeHotkeys(hotkeys);
  const registrations = registerHotkeys();
  updateApplicationMenu();
  return { ok: registrations.every(item => item.ok), registrations, current: readHotkeys() };
});

ipcMain.handle('hotkeys:reset', () => {
  writeHotkeys(defaultHotkeys);
  const registrations = registerHotkeys();
  updateApplicationMenu();
  return { ok: registrations.every(item => item.ok), registrations, current: readHotkeys() };
});

ipcMain.handle('hotkeys:testClipboardToChat', async () => {
  await openChatWithClipboard();
  return { ok: true };
});

ipcMain.handle('hotkeys:testClipboardToNewDebate', async () => {
  await openNewDebateWithClipboard();
  return { ok: true };
});

ipcMain.handle('hotkeys:testClipboardToNewAdvisors', async () => {
  await openNewAdvisorsWithClipboard();
  return { ok: true };
});

// IPC Handlers for Diagnostics
ipcMain.handle('diagnostics:status', () => {
  return getDiagnosticsStatus(ROOT_DIR, BACKEND_URL, FRONTEND_URL);
});

ipcMain.handle('diagnostics:start', () => {
  startStack();
  return { ok: true };
});

ipcMain.handle('diagnostics:retryStartup', async () => {
  stopStack();
  await startStackAndLoadUi();
  return { ok: true };
});

ipcMain.handle('diagnostics:stop', () => {
  stopStack();
  return { ok: true };
});

ipcMain.handle('diagnostics:openCouncil', async () => {
  await shell.openExternal(FRONTEND_URL);
  return { ok: true };
});

ipcMain.handle('diagnostics:openDocs', async () => {
  await shell.openExternal(`${BACKEND_URL}/docs`);
  return { ok: true };
});

ipcMain.handle('diagnostics:openLogs', () => {
  openLogs();
  return { ok: true };
});

async function loadStartupErrorPage(error) {
  const errorMessage = error?.message || String(error || 'Unknown startup error');
  const errorPage = path.join(__dirname, 'error.html');
  if (fs.existsSync(errorPage)) {
    await mainWindow.loadFile(errorPage, { query: { error: errorMessage } });
    return;
  }
  await mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
    <h1>The AI Counsel desktop launcher could not start the UI.</h1>
    <p>${errorMessage}</p>
    <p>Check logs at: ${LOG_DIR}</p>
    <p>Backend: ${HEALTH_URL}</p>
    <p>Frontend: ${FRONTEND_URL}</p>
  `)}`);
}

async function startStackAndLoadUi() {
  startStack();
  await waitForUrl(HEALTH_URL, 90000);
  await ensureProviderAutoLaunch();
  await waitForUrl(FRONTEND_URL, 90000);
  await mainWindow.loadURL(FRONTEND_URL);
}

async function startDesktopApp() {
  log(`${APP_NAME} desktop starting`);
  updateApplicationMenu();
  createWindow();
  createTray();
  registerHotkeys();

  try {
    await startStackAndLoadUi();
  } catch (error) {
    log(`Failed to load UI: ${error.stack || error.message}`);
    await loadStartupErrorPage(error);
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

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

process.on('uncaughtException', error => {
  log(`Uncaught exception: ${error.stack || error.message}`);
});

process.on('unhandledRejection', error => {
  log(`Unhandled rejection: ${error.stack || error.message || error}`);
});

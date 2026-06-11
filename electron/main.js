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
function spawnLogged(name, command, args, options = {}) {
  log(`Starting ${name}: ${command} ${args.join(' ')}`);
  const child = spawn(command, args, {
    cwd: ROOT_DIR,
    windowsHide: false,
    shell: false,
    detached: process.platform !== 'win32',
    env: { ...process.env, ...options.env },
    ...options,
  });

  child.stdout.on('data', data => appendProcessLog(name, data));
  child.stderr.on('data', data => appendProcessLog(name, data));
  child.on('error', error => log(`${name} failed to start: ${error.message}`));
  child.on('exit', (code, signal) => log(`${name} exited with code=${code} signal=${signal}`));
  return child;
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
      // Kill the process group to clean up any orphaned child processes
      process.kill(-child.pid, 'SIGTERM');
    }
  } catch (error) {
    log(`Failed to stop ${name}: ${error.message}`);
  }
}

function stopStack() {
  stopProcess(frontendProcess, 'frontend');
  stopProcess(backendProcess, 'backend');
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 950,
    minWidth: 1000,
    minHeight: 700,
    title: APP_NAME,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.on('close', event => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());
  return mainWindow;
}

function showWindow() {
  if (!mainWindow) createWindow();
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
        { label: 'Show / Hide', click: () => (mainWindow && mainWindow.isVisible() ? mainWindow.hide() : showWindow()) },
        { label: 'Reload UI', click: reloadApp },
        { type: 'separator' },
        { label: 'Open in Browser', click: () => shell.openExternal(FRONTEND_URL) },
        { label: 'Open Backend Health', click: () => shell.openExternal(HEALTH_URL) },
        { label: 'Open Logs', click: openLogs },
        { type: 'separator' },
        { label: 'Start Stack', click: startStack },
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
  const iconPath = path.join(__dirname, 'icon.png');
  const icon = fs.existsSync(iconPath) ? nativeImage.createFromPath(iconPath) : nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip(APP_NAME);
  tray.setContextMenu(Menu.buildFromTemplate(menuTemplate()[0].submenu));
  tray.on('click', () => (mainWindow && mainWindow.isVisible() ? mainWindow.hide() : showWindow()));
}

async function startDesktopApp() {
  log(`${APP_NAME} desktop starting`);
  Menu.setApplicationMenu(Menu.buildFromTemplate(menuTemplate()));
  createWindow();
  createTray();

  try {
    startStack();
    await waitForUrl(HEALTH_URL, 90000);
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

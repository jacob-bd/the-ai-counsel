const { BrowserWindow } = require('electron');
const path = require('path');

let diagnosticsWindow = null;

function openDiagnostics(parentWindow) {
  if (diagnosticsWindow && !diagnosticsWindow.isDestroyed()) {
    diagnosticsWindow.show();
    diagnosticsWindow.focus();
    return diagnosticsWindow;
  }

  diagnosticsWindow = new BrowserWindow({
    width: 980,
    height: 760,
    minWidth: 820,
    minHeight: 620,
    title: 'The AI Counsel Diagnostics',
    backgroundColor: '#101418',
    parent: parentWindow || undefined,
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  diagnosticsWindow.on('closed', () => {
    diagnosticsWindow = null;
  });

  diagnosticsWindow.loadFile(path.join(__dirname, '..', 'diagnostics.html'));
  return diagnosticsWindow;
}

module.exports = {
  openDiagnostics,
};

const { BrowserWindow } = require('electron');
const path = require('path');

let hotkeyWindow = null;

function openHotkeySettings(parentWindow) {
  if (hotkeyWindow && !hotkeyWindow.isDestroyed()) {
    hotkeyWindow.show();
    hotkeyWindow.focus();
    return hotkeyWindow;
  }

  hotkeyWindow = new BrowserWindow({
    width: 720,
    height: 625,
    minWidth: 620,
    minHeight: 520,
    title: 'The AI Counsel Hotkeys',
    backgroundColor: '#111827',
    parent: parentWindow || undefined,
    webPreferences: { 
      preload: path.join(__dirname, '..', 'preload.js'), 
      nodeIntegration: false, 
      contextIsolation: true,
      sandbox: true // Security hardening
    },
  });

  hotkeyWindow.on('closed', () => {
    hotkeyWindow = null;
  });

  hotkeyWindow.loadFile(path.join(__dirname, '..', 'hotkeys.html'));
  
  return hotkeyWindow;
}

module.exports = {
  openHotkeySettings
};

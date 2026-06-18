const { app } = require('electron');
const fs = require('fs');
const path = require('path');

const defaultHotkeys = {
  toggleWindow: 'CommandOrControl+Alt+Space',
  openChat: 'CommandOrControl+Alt+L',
  openNewDebate: 'CommandOrControl+Alt+N',
  openNewAdvisors: 'CommandOrControl+Alt+A',
  clipboardToChat: 'CommandOrControl+Alt+V',
  clipboardToNewDebate: 'CommandOrControl+Alt+Shift+V',
  clipboardToNewAdvisors: 'CommandOrControl+Alt+Shift+A',
  openNotion2Api: 'CommandOrControl+Alt+O',
  openHotkeySettings: 'CommandOrControl+Alt+H',
};

function getHotkeyConfigPath() {
  return path.join(app.getPath('userData'), 'hotkeys.json');
}

function readHotkeys() {
  try {
    const file = getHotkeyConfigPath();
    if (!fs.existsSync(file)) return { ...defaultHotkeys };

    const saved = JSON.parse(fs.readFileSync(file, 'utf8'));
    const merged = { ...defaultHotkeys, ...saved };
    return merged;
  } catch {
    return { ...defaultHotkeys };
  }
}

function writeHotkeys(hotkeys) {
  const file = getHotkeyConfigPath();
  const dir = path.dirname(file);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(file, JSON.stringify({ ...defaultHotkeys, ...hotkeys }, null, 2), 'utf8');
}

module.exports = {
  defaultHotkeys,
  getHotkeyConfigPath,
  readHotkeys,
  writeHotkeys
};

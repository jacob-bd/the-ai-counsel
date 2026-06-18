const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('notion2CouncilHotkeys', {
  get: () => ipcRenderer.invoke('hotkeys:get'),
  save: hotkeys => ipcRenderer.invoke('hotkeys:save', hotkeys),
  reset: () => ipcRenderer.invoke('hotkeys:reset'),
  testClipboardToChat: () => ipcRenderer.invoke('hotkeys:testClipboardToChat'),
  testClipboardToNewDebate: () => ipcRenderer.invoke('hotkeys:testClipboardToNewDebate'),
  testClipboardToNewAdvisors: () => ipcRenderer.invoke('hotkeys:testClipboardToNewAdvisors'),
});

contextBridge.exposeInMainWorld('notion2CouncilDiagnostics', {
  status: () => ipcRenderer.invoke('diagnostics:status'),
  start: () => ipcRenderer.invoke('diagnostics:start'),
  stop: () => ipcRenderer.invoke('diagnostics:stop'),
  openCouncil: () => ipcRenderer.invoke('diagnostics:openCouncil'),
  openDocs: () => ipcRenderer.invoke('diagnostics:openDocs'),
  openLogs: () => ipcRenderer.invoke('diagnostics:openLogs'),
});

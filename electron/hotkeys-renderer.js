const api = window.notion2CouncilHotkeys;
const fields = [
  'toggleWindow',
  'openChat',
  'openNewDebate',
  'openNewAdvisors',
  'clipboardToChat',
  'clipboardToNewDebate',
  'clipboardToNewAdvisors',
  'openNotion2Api',
  'openHotkeySettings'
];
const status = document.getElementById('status');
const pathEl = document.getElementById('path');

function setStatus(text, kind = '') {
  status.textContent = text || '';
  status.className = `status ${kind}`.trim();
}

function readForm() {
  return Object.fromEntries(fields.map(id => [id, document.getElementById(id).value.trim()]));
}

function writeForm(values) {
  fields.forEach(id => {
    document.getElementById(id).value = values?.[id] || '';
  });
}

function formatRegistrations(registrations) {
  if (!registrations || !registrations.length) return '';
  return registrations.map(item => `${item.ok ? '✓' : '×'} ${item.name}: ${item.accelerator}`).join('\n');
}

/**
 * Converts a KeyboardEvent into an Electron Accelerator string.
 * @param {KeyboardEvent} e 
 */
function getAcceleratorString(e) {
  const modifiers = [];
  if (e.ctrlKey) modifiers.push('Control');
  if (e.altKey) modifiers.push('Alt');
  if (e.shiftKey) modifiers.push('Shift');
  if (e.metaKey) modifiers.push('Command');

  let key = e.key;

  // Normalization for Electron
  if (key === ' ') key = 'Space';
  if (key === 'Control' || key === 'Alt' || key === 'Shift' || key === 'Meta') {
    key = ''; // Don't include standalone modifiers as the primary key
  }

  if (key.length === 1) {
    key = key.toUpperCase();
  } else if (key.startsWith('Arrow')) {
    key = key.replace('Arrow', '');
  }

  if (!key) return modifiers.join('+');
  return [...modifiers, key].join('+');
}

// Setup keyboard capture for each input
fields.forEach(id => {
  const input = document.getElementById(id);
  input.addEventListener('keydown', (e) => {
    // Ignore standalone modifier presses
    if (['Control', 'Alt', 'Shift', 'Meta'].includes(e.key)) return;

    // Allow Tab to escape the field
    if (e.key === 'Tab') return;

    e.preventDefault();
    e.stopPropagation();

    if (e.key === 'Escape' || e.key === 'Backspace') {
      input.value = '';
      return;
    }

    const accelerator = getAcceleratorString(e);
    if (accelerator) {
      input.value = accelerator;
    }
  });

  input.placeholder = 'Press keys to record...';
});

async function load() {
  try {
    const data = await api.get();
    writeForm(data.current);
    pathEl.textContent = `Saved at: ${data.configPath}`;
    setStatus('Loaded current hotkeys.', 'ok');
  } catch (error) {
    setStatus(`Failed to load hotkeys: ${error.message}`, 'error');
  }
}

document.getElementById('save').addEventListener('click', async () => {
  const form = readForm();
  
  try {
    const result = await api.save(form);
    writeForm(result.current);
    const failures = (result.registrations || []).filter(item => !item.ok);
    if (failures.length) {
      setStatus(`Saved, but some hotkeys could not be registered. They may already be used by Windows or another app.\n\n${formatRegistrations(result.registrations)}`, 'error');
    } else {
      setStatus(`Saved and registered.\n\n${formatRegistrations(result.registrations)}`, 'ok');
    }
  } catch (error) {
    setStatus(`Failed to save hotkeys: ${error.message}`, 'error');
  }
});

document.getElementById('reset').addEventListener('click', async () => {
  try {
    const result = await api.reset();
    writeForm(result.current);
    setStatus(`Defaults restored.\n\n${formatRegistrations(result.registrations)}`, result.ok ? 'ok' : 'error');
  } catch (error) {
    setStatus(`Failed to reset hotkeys: ${error.message}`, 'error');
  }
});

document.getElementById('testClipboard').addEventListener('click', async () => {
  try {
    await api.testClipboardToChat();
    setStatus('Clipboard-to-chat command sent.', 'ok');
  } catch (error) {
    setStatus(`Clipboard-to-chat test failed: ${error.message}`, 'error');
  }
});

document.getElementById('testClipboardToNewDebate').addEventListener('click', async () => {
  try {
    await api.testClipboardToNewDebate();
    setStatus('Clipboard-to-new-debate command sent.', 'ok');
  } catch (error) {
    setStatus(`Clipboard-to-new-debate test failed: ${error.message}`, 'error');
  }
});

document.getElementById('testClipboardToNewAdvisors').addEventListener('click', async () => {
  try {
    await api.testClipboardToNewAdvisors();
    setStatus('Clipboard-to-new-advisors command sent.', 'ok');
  } catch (error) {
    setStatus(`Clipboard-to-new-advisors test failed: ${error.message}`, 'error');
  }
});

document.getElementById('reload').addEventListener('click', load);

// Initial load
load();

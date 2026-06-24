const params = new URLSearchParams(window.location.search);
const errorBox = document.getElementById('error-message');
const retryButton = document.getElementById('retry-btn');
const diagnostics = window.notion2CouncilDiagnostics;

errorBox.textContent = params.get('error')
  || 'Timed out waiting for background services to report a healthy status.';

document.getElementById('logs-btn').addEventListener('click', () => {
  if (diagnostics && typeof diagnostics.openLogs === 'function') {
    diagnostics.openLogs();
  }
});

retryButton.addEventListener('click', async () => {
  retryButton.disabled = true;
  retryButton.textContent = 'Retrying...';

  if (!diagnostics || typeof diagnostics.retryStartup !== 'function') {
    retryButton.disabled = false;
    retryButton.textContent = 'Retry Startup';
    errorBox.textContent = 'Retry controls are unavailable. Restart the desktop application.';
    return;
  }

  try {
    await diagnostics.retryStartup();
  } catch (error) {
    retryButton.disabled = false;
    retryButton.textContent = 'Retry Startup';
    errorBox.textContent = `Retry failed: ${error.message}`;
  }
});

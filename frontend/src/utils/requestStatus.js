const KNOWN_STATUSES = new Set([
  'queued',
  'running',
  'paused',
  'completed',
  'failed',
  'unaccounted',
]);

export function getRequestStatus(item = {}) {
  if (KNOWN_STATUSES.has(item.status)) return item.status;
  if (item.retrying || item.firing || item.running) return 'running';
  if (item.paused) return 'paused';
  if (item.pending) return 'queued';
  if (item.error) return item.unaccounted ? 'unaccounted' : 'failed';
  return 'completed';
}

export function getRequestStatusLabel(status) {
  switch (status) {
    case 'queued': return 'Queued';
    case 'running': return 'Running';
    case 'paused': return 'Paused';
    case 'failed': return 'Failed';
    case 'unaccounted': return 'Unaccounted';
    default: return 'Completed';
  }
}

export function markTerminalResult(item = {}) {
  const failed = Boolean(item.error);
  return {
    ...item,
    status: failed ? 'failed' : 'completed',
    pending: false,
    running: false,
    firing: false,
    retrying: false,
  };
}

export function reconcileTerminalResults(existing = [], results = [], expectedModels = []) {
  const currentByModel = new Map(
    (existing || []).filter((item) => item?.model).map((item) => [item.model, item])
  );
  const resultByModel = new Map(
    (results || []).filter((item) => item?.model).map((item) => [item.model, item])
  );

  const orderedModels = [];
  const seen = new Set();
  const addModel = (model) => {
    if (model && !seen.has(model)) {
      seen.add(model);
      orderedModels.push(model);
    }
  };

  expectedModels.forEach(addModel);
  (existing || []).forEach((item) => addModel(item?.model));
  (results || []).forEach((item) => addModel(item?.model));

  return orderedModels.map((model) => {
    const result = resultByModel.get(model);
    if (result) return markTerminalResult(result);

    const current = currentByModel.get(model) || { model };
    return {
      ...current,
      model,
      status: 'unaccounted',
      pending: false,
      running: false,
      firing: false,
      retrying: false,
      error: true,
      unaccounted: true,
      error_message: current.error_message || 'No terminal result was received for this dispatched request.',
    };
  });
}

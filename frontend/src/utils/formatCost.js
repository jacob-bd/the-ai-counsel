export function formatUsd(value, unknown = false, unknownLabel = 'Unknown') {
  if (unknown || typeof value !== 'number' || Number.isNaN(value)) return unknownLabel;
  if (value === 0) return '$0.00';
  if (value < 0.000001) return '<$0.000001';
  if (value < 0.01) return `$${value.toFixed(6)}`;
  return `$${value.toFixed(4)}`;
}

export function formatSidebarCost(totalCost, costStatus) {
  const amount = formatUsd(totalCost);
  if (costStatus === 'estimated') return `~${amount}`;
  if (costStatus === 'partial') return `${amount}+`;
  return amount;
}

export function sidebarCostTooltip(totalCost, costStatus, totalCalls, t) {
  const parts = [t('Conversation total')];
  if (typeof totalCalls === 'number' && totalCalls > 0) {
    parts.push(t(totalCalls === 1 ? '{count} API call' : '{count} API calls', { count: totalCalls }));
  }
  if (costStatus === 'partial') {
    parts.push(t('some pricing unavailable'));
  } else if (costStatus === 'estimated') {
    parts.push(t('estimated pricing'));
  } else if (costStatus === 'free') {
    parts.push(t('known free models'));
  }
  if (typeof totalCost === 'number') {
    parts.push(formatUsd(totalCost));
  }
  return parts.join(' · ');
}

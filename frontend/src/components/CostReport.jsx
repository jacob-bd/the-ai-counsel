import './CostReport.css';

const numberFormatter = new Intl.NumberFormat(undefined);

function formatUsd(value, unknown = false) {
  if (unknown || typeof value !== 'number' || Number.isNaN(value)) return 'Unknown';
  if (value === 0) return '$0.00';
  if (value < 0.000001) return '<$0.000001';
  if (value < 0.01) return `$${value.toFixed(6)}`;
  return `$${value.toFixed(4)}`;
}

function formatTokens(value) {
  if (typeof value !== 'number') return '0';
  return numberFormatter.format(value);
}

function rowCostLabel(row) {
  return formatUsd(row.total_cost, row.known_cost_calls === 0 && row.unknown_cost_calls > 0);
}

function rowStatus(row) {
  if (row.free_calls === row.calls) return 'Free';
  if (row.unknown_cost_calls > 0 && row.known_cost_calls === 0) return 'Usage only';
  if (row.estimated_calls > 0) return 'Estimated';
  return 'Known';
}

export default function CostReport({ report, title = 'Run Cost' }) {
  if (!report || !Array.isArray(report.by_model) || report.by_model.length === 0) {
    return null;
  }

  const unknownTotal = report.known_cost_calls === 0 && report.unknown_cost_calls > 0;
  const statusText = report.has_unknown_costs
    ? 'Some pricing unavailable'
    : report.has_estimates
      ? 'Estimated'
      : 'Known';

  return (
    <section className="cost-report" aria-label={title}>
      <div className="cost-report__summary">
        <div>
          <div className="cost-report__eyebrow">{title}</div>
          <div className="cost-report__total">{formatUsd(report.total_cost, unknownTotal)}</div>
        </div>
        <div className="cost-report__metrics" aria-label="Cost metrics">
          <span>{formatTokens(report.total_tokens)} tokens</span>
          <span>{report.total_calls || 0} calls</span>
          <span className={`cost-report__status ${report.has_unknown_costs ? 'unknown' : report.has_estimates ? 'estimated' : 'known'}`}>
            {statusText}
          </span>
        </div>
      </div>

      <details className="cost-report__details">
        <summary>Model breakdown</summary>
        <div className="cost-report__table" role="table" aria-label="Cost by model">
          <div className="cost-report__row cost-report__row--head" role="row">
            <span role="columnheader">Model</span>
            <span role="columnheader">Calls</span>
            <span role="columnheader">Tokens</span>
            <span role="columnheader">Cost</span>
            <span role="columnheader">Status</span>
          </div>
          {report.by_model.map((row) => (
            <div className="cost-report__row" role="row" key={row.name}>
              <span className="cost-report__model" role="cell" title={row.name}>{row.name}</span>
              <span role="cell">{row.calls || 0}</span>
              <span role="cell">{formatTokens(row.total_tokens)}</span>
              <span role="cell">{rowCostLabel(row)}</span>
              <span role="cell" className={`cost-report__source ${rowStatus(row).toLowerCase().replace(' ', '-')}`}>
                {rowStatus(row)}
              </span>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

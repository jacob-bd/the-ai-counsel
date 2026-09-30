import './CostReport.css';
import { formatUsd } from '../utils/formatCost';
import { useI18n } from '../i18n';

const numberFormatter = new Intl.NumberFormat(undefined);

function formatTokens(value) {
  if (typeof value !== 'number') return '0';
  return numberFormatter.format(value);
}

function formatTokenBreakdown(item, t) {
  return t('{input} in / {output} out', {
    input: formatTokens(item.input_tokens),
    output: formatTokens(item.output_tokens),
  });
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
  const { t } = useI18n();
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
    <section className="cost-report" aria-label={t(title)}>
      <div className="cost-report__summary">
        <div>
          <div className="cost-report__eyebrow">{t(title)}</div>
          <div className="cost-report__total">{formatUsd(report.total_cost, unknownTotal)}</div>
        </div>
        <div className="cost-report__metrics" aria-label={t('Cost metrics')}>
          <span title={t('Provider-reported total tokens when available, otherwise input plus output tokens.')}>
            {t('{count} total tokens', { count: formatTokens(report.total_tokens) })}
          </span>
          <span title={t('Input tokens')}>{t('{count} in', { count: formatTokens(report.input_tokens) })}</span>
          <span title={t('Output tokens')}>{t('{count} out', { count: formatTokens(report.output_tokens) })}</span>
          <span>{t('{count} calls', { count: report.total_calls || 0 })}</span>
          <span className={`cost-report__status ${report.has_unknown_costs ? 'unknown' : report.has_estimates ? 'estimated' : 'known'}`}>
            {t(statusText)}
          </span>
        </div>
      </div>

      <details className="cost-report__details">
        <summary>{t('Model breakdown')}</summary>
        <div className="cost-report__table" role="table" aria-label={t('Cost by model')}>
          <div className="cost-report__row cost-report__row--head" role="row">
            <span role="columnheader">{t('Model')}</span>
            <span role="columnheader">{t('Calls')}</span>
            <span role="columnheader">{t('Tokens')}</span>
            <span role="columnheader">{t('Cost')}</span>
            <span role="columnheader">{t('Status')}</span>
          </div>
          {report.by_model.map((row) => (
            <div className="cost-report__row" role="row" key={row.name}>
              <span className="cost-report__model" role="cell" title={row.name}>{row.name}</span>
              <span role="cell">{row.calls || 0}</span>
              <span className="cost-report__tokens" role="cell" title={formatTokenBreakdown(row, t)}>
                <span>{formatTokens(row.total_tokens)}</span>
                <small>{formatTokenBreakdown(row, t)}</small>
              </span>
              <span role="cell">{rowCostLabel(row)}</span>
              <span role="cell" className={`cost-report__source ${rowStatus(row).toLowerCase().replace(' ', '-')}`}>
                {t(rowStatus(row))}
              </span>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

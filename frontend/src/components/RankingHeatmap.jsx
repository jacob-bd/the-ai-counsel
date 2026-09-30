import { getShortModelName, getModelVisuals } from '../utils/modelHelpers';
import { useI18n } from '../i18n';
import './RankingHeatmap.css';

function ordinal(n, t) {
  if (n === 1) return t('{rank}st', { rank: n });
  if (n === 2) return t('{rank}nd', { rank: n });
  if (n === 3) return t('{rank}rd', { rank: n });
  return t('{rank}th', { rank: n });
}

/**
 * Renders a premium, color-coded N×N heatmap showing how each council model
 * ranked every other model in Stage 2. Fully optimized for Midnight Glass dark theme.
 *
 * Props:
 *   rankings      – Stage 2 rankings array: [{model, parsed_ranking, error, ...}]
 *   labelToModel  – Map of "Response A" -> full model id
 */
export default function RankingHeatmap({ rankings, labelToModel }) {
  const { t } = useI18n();
  if (!rankings || !labelToModel || rankings.length === 0) return null;

  // Filter out any models that failed to rank (failed peer review runs)
  const validRankings = rankings.filter((r) => !r.error && r.parsed_ranking && r.parsed_ranking.length > 0);
  if (validRankings.length === 0) return null;

  // Rankees in label order (A, B, C …)
  const rankeeModels = Object.entries(labelToModel)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, model]) => model);

  const rankerModels = validRankings.map((r) => r.model);

  // Build position matrix: positions[rankerModel][rankeeModel] = 1-based rank
  const positions = {};
  for (const ranking of validRankings) {
    positions[ranking.model] = {};
    const parsed = ranking.parsed_ranking || [];
    parsed.forEach((label, idx) => {
      const model = labelToModel[label];
      if (model) positions[ranking.model][model] = idx + 1;
    });
  }

  // Average rank per rankee (matching backend leaderboard logic where self-vote defaults to a perfect 1.00)
  const avgRanks = {};
  for (const rankee of rankeeModels) {
    const vals = rankerModels
      .map((r) => {
        if (r === rankee) return 1; // Self-review defaults to a perfect 1st place in aggregate calculations
        return positions[r]?.[rankee];
      })
      .filter((v) => v !== undefined);
    if (vals.length > 0) {
      avgRanks[rankee] = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2);
    }
  }

  return (
    <div className="ranking-heatmap glass-panel">
      <div className="heatmap-header">
        <h4 className="heatmap-title">{t('📊 Peer Deliberation Matrix')}</h4>
        <p className="heatmap-description">
          {t('Detailed matrix of anonymous peer reviews. Raters are on the left; rated responses are on top. Self-review cells (—) are excluded from the grid but counted as a perfect')}
          {' '}<strong>{t('1st place (1.00)')}</strong>{' '}
          {t('in aggregate score calculations to match the leaderboard averages.')}
        </p>
      </div>

      <div className="heatmap-table-wrapper">
        <table className="heatmap-table">
          <thead>
            <tr>
              <th className="heatmap-corner">{t('Rater ↓ / Rated →')}</th>
              {rankeeModels.map((model) => {
                const visuals = getModelVisuals(model);
                const short = getShortModelName(model);
                return (
                  <th key={model} className="heatmap-col-header" style={{ '--model-color': visuals.color }}>
                    <div className="header-cell-content">
                      <span className="mini-avatar" style={{ backgroundColor: visuals.color }}>
                        {visuals.icon}
                      </span>
                      <span className="col-name-text" title={short}>{short}</span>
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rankerModels.map((ranker) => {
              const rankerVisuals = getModelVisuals(ranker);
              const rankerShort = getShortModelName(ranker);
              return (
                <tr key={ranker} className="heatmap-row">
                  <td className="heatmap-row-header" style={{ '--model-color': rankerVisuals.color }}>
                    <div className="row-cell-content">
                      <span className="mini-avatar" style={{ backgroundColor: rankerVisuals.color }}>
                        {rankerVisuals.icon}
                      </span>
                      <span className="row-name-text" title={rankerShort}>{rankerShort}</span>
                    </div>
                  </td>
                  {rankeeModels.map((rankee) => {
                    if (ranker === rankee) {
                      return (
                        <td key={rankee} className="heatmap-cell heatmap-self">
                          —
                        </td>
                      );
                    }
                    const pos = positions[ranker]?.[rankee];
                    if (pos === undefined) {
                      return (
                        <td key={rankee} className="heatmap-cell heatmap-unknown">
                          ?
                        </td>
                      );
                    }
                    return (
                      <td
                        key={rankee}
                        className={`heatmap-cell heatmap-pos-${pos}`}
                      >
                        <span className="rank-badge">{ordinal(pos, t)}</span>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            <tr className="heatmap-avg-row">
              <td className="heatmap-row-header heatmap-avg-label">
                <div className="row-cell-content">
                  <span className="mini-avatar" style={{ backgroundColor: 'var(--accent-stage2)' }}>📈</span>
                  <span className="row-name-text font-semibold">{t('Average Rank')}</span>
                </div>
              </td>
              {rankeeModels.map((rankee) => (
                <td key={rankee} className="heatmap-cell heatmap-avg">
                  {avgRanks[rankee] ?? '—'}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

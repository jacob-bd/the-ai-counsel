import { getShortModelName, getModelVisuals } from '../utils/modelHelpers';
import { getRequestStatus, getRequestStatusLabel } from '../utils/requestStatus';
import ModelVisualIcon from './ModelVisualIcon';
import './RankingHeatmap.css';

function ordinal(n) {
  if (n === 1) return '1st';
  if (n === 2) return '2nd';
  if (n === 3) return '3rd';
  return `${n}th`;
}

function getMatrixStatus(ranking) {
  const requestStatus = getRequestStatus(ranking);
  if (requestStatus === 'completed' && !(ranking?.parsed_ranking?.length > 0)) {
    return 'unparsed';
  }
  return requestStatus;
}

function getMatrixStatusLabel(status) {
  if (status === 'unparsed') return 'Unparsed';
  return getRequestStatusLabel(status);
}

/**
 * Renders an N×N matrix showing every expected Stage 2 request. Rows without a
 * usable parsed ranking remain visible with their actual lifecycle state.
 */
export default function RankingHeatmap({ rankings, labelToModel }) {
  if (!rankings || !labelToModel || rankings.length === 0) return null;

  const rankingByModel = new Map();
  rankings.forEach((ranking) => {
    if (ranking?.model) rankingByModel.set(ranking.model, ranking);
  });
  const allRankings = [...rankingByModel.values()];
  const validRankings = allRankings.filter(
    (ranking) => !ranking.error && ranking.parsed_ranking?.length > 0
  );

  const rankeeModels = Object.entries(labelToModel)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, model]) => model);
  if (rankeeModels.length === 0) return null;

  const rankerModels = allRankings.map((ranking) => ranking.model);
  const validRankerModels = validRankings.map((ranking) => ranking.model);

  const positions = {};
  for (const ranking of validRankings) {
    positions[ranking.model] = {};
    ranking.parsed_ranking.forEach((label, index) => {
      const model = labelToModel[label];
      if (model) positions[ranking.model][model] = index + 1;
    });
  }

  const avgRanks = {};
  for (const rankee of rankeeModels) {
    const values = validRankerModels
      .map((ranker) => {
        if (ranker === rankee) return 1;
        return positions[ranker]?.[rankee];
      })
      .filter((value) => value !== undefined);
    if (values.length > 0) {
      avgRanks[rankee] = (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(2);
    }
  }

  return (
    <div className="ranking-heatmap glass-panel">
      <div className="heatmap-header">
        <h4 className="heatmap-title">📊 Peer Deliberation Matrix</h4>
        <p className="heatmap-description">
          Every Stage 2 request remains visible. Raters are on the left; rated responses are on top.
          Running, queued, failed, and unparsed reviews are identified explicitly and excluded from averages.
          Valid self-review cells (—) count as a perfect <strong>1st place (1.00)</strong> to match the leaderboard.
        </p>
      </div>

      <div className="heatmap-accounting" role="status">
        <span>{allRankings.length} requests accounted for</span>
        <span>{validRankings.length} usable rankings</span>
        <span>{allRankings.length - validRankings.length} unavailable or incomplete</span>
      </div>

      <div className="heatmap-table-wrapper">
        <table className="heatmap-table">
          <thead>
            <tr>
              <th className="heatmap-corner">Rater ↓ / Rated →</th>
              {rankeeModels.map((model) => {
                const visuals = getModelVisuals(model);
                const short = getShortModelName(model);
                return (
                  <th key={model} className="heatmap-col-header" style={{ '--model-color': visuals.color }}>
                    <div className="header-cell-content">
                      <span className="mini-avatar" style={{ backgroundColor: visuals.color }}>
                        <ModelVisualIcon visuals={visuals} scale={0.68} />
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
              const ranking = rankingByModel.get(ranker) || { model: ranker };
              const rowStatus = getMatrixStatus(ranking);
              const rowUsable = rowStatus === 'completed' && ranking.parsed_ranking?.length > 0;
              const rankerVisuals = getModelVisuals(ranker);
              const rankerShort = getShortModelName(ranker);
              return (
                <tr key={ranker} className={`heatmap-row heatmap-row--${rowStatus}`}>
                  <td className="heatmap-row-header" style={{ '--model-color': rankerVisuals.color }}>
                    <div className="row-cell-content">
                      <span className="mini-avatar" style={{ backgroundColor: rankerVisuals.color }}>
                        <ModelVisualIcon visuals={rankerVisuals} scale={0.68} />
                      </span>
                      <span className="row-name-text" title={rankerShort}>{rankerShort}</span>
                      <span className={`heatmap-status-badge heatmap-status-badge--${rowStatus}`}>
                        {getMatrixStatusLabel(rowStatus)}
                      </span>
                    </div>
                  </td>
                  {rankeeModels.map((rankee) => {
                    if (!rowUsable) {
                      return (
                        <td key={rankee} className={`heatmap-cell heatmap-state heatmap-state--${rowStatus}`}>
                          {getMatrixStatusLabel(rowStatus)}
                        </td>
                      );
                    }
                    if (ranker === rankee) {
                      return <td key={rankee} className="heatmap-cell heatmap-self">—</td>;
                    }
                    const position = positions[ranker]?.[rankee];
                    if (position === undefined) {
                      return <td key={rankee} className="heatmap-cell heatmap-unknown">Not ranked</td>;
                    }
                    return (
                      <td key={rankee} className={`heatmap-cell heatmap-pos-${position}`}>
                        <span className="rank-badge">{ordinal(position)}</span>
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
                  <span className="row-name-text font-semibold">Average Rank</span>
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

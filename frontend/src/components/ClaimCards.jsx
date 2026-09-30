import { useState } from 'react';
import { getShortModelName } from '../utils/modelHelpers';
import { useI18n } from '../i18n';
import './ClaimCards.css';

export default function ClaimCards({ claims, labelToModel }) {
  const { t } = useI18n();
  if (!claims || Object.keys(claims).length === 0) return null;

  const flatClaims = [];
  for (const [label, claimList] of Object.entries(claims)) {
    for (const claim of claimList) {
      flatClaims.push({ ...claim, sourceLabel: label, sourceModel: labelToModel?.[label] || label });
    }
  }

  if (flatClaims.length === 0) return null;

  return (
    <div className="claim-cards">
      <h4>{t('Canonical Claims')}</h4>
      <p className="claim-cards-description">{t('Claims extracted from each response and evaluated by all peers.')}</p>
      <div className="claim-cards-grid">
        {flatClaims.map((claim) => (
          <ClaimCardSimple key={claim.id} claim={claim} />
        ))}
      </div>
    </div>
  );
}

function ClaimCardSimple({ claim }) {
  return (
    <div className="claim-card">
      <div className="claim-header">
        <span className="claim-id">{claim.id}</span>
        <span className="claim-source">{getShortModelName(claim.sourceModel)}</span>
      </div>
      <p className="claim-text">&ldquo;{claim.claim}&rdquo;</p>
    </div>
  );
}

/**
 * Main claim evaluation display for Stage 2 in claim mode.
 * Surfaces contested/flawed claims prominently at the top.
 */
export function ClaimCardWithVerdicts({ claims, aggregatedVerdicts, labelToModel, stage2Results }) {
  const { t } = useI18n();
  const [showAllStrong, setShowAllStrong] = useState(false);

  if (!claims || Object.keys(claims).length === 0) return null;

  const flatClaims = [];
  for (const [label, claimList] of Object.entries(claims)) {
    for (const claim of claimList) {
      const verdictInfo = aggregatedVerdicts?.[claim.id] || {};
      const evaluatorVerdicts = [];
      if (stage2Results) {
        for (const result of stage2Results) {
          const cv = result.claim_verdicts?.[claim.id];
          if (cv) {
            evaluatorVerdicts.push({ model: result.model, verdict: cv.verdict, reason: cv.reason });
          }
        }
      }
      flatClaims.push({
        ...claim,
        sourceLabel: label,
        sourceModel: labelToModel?.[label] || label,
        majority_verdict: verdictInfo.majority_verdict,
        agreement: verdictInfo.agreement,
        evaluator_verdicts: evaluatorVerdicts,
      });
    }
  }

  if (flatClaims.length === 0) return null;

  // Split into contested and strong
  const contested = flatClaims.filter(c => c.majority_verdict && c.majority_verdict !== 'strong');
  const strong = flatClaims.filter(c => c.majority_verdict === 'strong');
  const unknown = flatClaims.filter(c => !c.majority_verdict);
  const totalClaims = flatClaims.length;

  // Group strong claims by source for compact display
  const strongBySource = {};
  for (const claim of strong) {
    const key = claim.sourceLabel;
    if (!strongBySource[key]) strongBySource[key] = [];
    strongBySource[key].push(claim);
  }

  return (
    <div className="claim-cards">
      {/* Summary bar */}
      <div className="claim-summary-bar">
        <div className="claim-summary-title">
          <span className="claim-summary-icon">🔬</span>
          <span>{t('Claim-Level Evaluation')}</span>
        </div>
        <div className="claim-summary-stats">
          {contested.length > 0 && (
            <span className="claim-stat contested">
              <span className="claim-stat-num">{contested.length}</span> {t('contested')}
            </span>
          )}
          <span className="claim-stat strong">
            <span className="claim-stat-num">{strong.length}</span> {t('strong')}
          </span>
          <span className="claim-stat total">{t('{count} total', { count: totalClaims })}</span>
        </div>
      </div>

      {/* Contested claims - always shown prominently */}
      {contested.length > 0 && (
        <div className="claim-contested-section">
          <div className="claim-section-label contested-label">
            <span className="pulse-dot"></span>
            {t('Contested Claims')}
          </div>
          {contested.map((claim) => (
            <ClaimCardDetailed key={claim.id} claim={claim} prominent t={t} />
          ))}
        </div>
      )}

      {contested.length === 0 && (
        <div className="claim-all-strong-banner">
          <span className="check-icon">✓</span>
          {t('All {total} claims reached STRONG consensus across evaluators.', { total: totalClaims })}
        </div>
      )}

      {/* Unknown verdict claims */}
      {unknown.length > 0 && unknown.map((claim) => (
        <ClaimCardDetailed key={claim.id} claim={claim} t={t} />
      ))}

      {/* Strong claims - collapsed by default */}
      {strong.length > 0 && (
        <div className="claim-strong-section">
          <button
            className="claim-section-toggle"
            onClick={() => setShowAllStrong(!showAllStrong)}
          >
            <span className="toggle-icon">{showAllStrong ? '▾' : '▸'}</span>
            <span className="claim-section-label">
              {t('{count} Strong Claims', { count: strong.length })}
            </span>
            <span className="claim-section-hint">
              {showAllStrong ? t('click to collapse') : t('click to expand')}
            </span>
          </button>

          {showAllStrong && (
            <div className="claim-strong-list">
              {Object.entries(strongBySource).map(([label, groupClaims]) => (
                <div key={label} className="claim-source-group">
                  <div className="claim-source-header">
                    <span className="claim-source-label">{label}</span>
                    <span className="claim-source-model">
                      {labelToModel?.[label] ? getShortModelName(labelToModel[label]) : ''}
                    </span>
                    <span className="claim-source-count">{t('{count} claims', { count: groupClaims.length })}</span>
                  </div>
                  {groupClaims.map((claim) => (
                    <ClaimCardCompact key={claim.id} claim={claim} />
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Claim Evolution: shows how claims changed across rounds.
 */
export function ClaimEvolution({ rounds, labelToModel: finalLabelToModel }) {
  const { t } = useI18n();
  if (!rounds || rounds.length < 2) return null;

  // Build claim data per round
  const roundData = rounds.map(rd => {
    const meta = rd.metadata || {};
    const claims = meta.canonical_claims || {};
    const verdicts = meta.aggregate_claim_verdicts || {};
    const l2m = meta.label_to_model || {};
    const totalClaims = Object.values(claims).reduce((sum, arr) => sum + arr.length, 0);
    const strong = Object.values(verdicts).filter(v => v.majority_verdict === 'strong').length;
    const contested = Object.values(verdicts).filter(v => v.majority_verdict && v.majority_verdict !== 'strong');
    return { round: rd.round_number, claims, verdicts, l2m, totalClaims, strong, contested, mode: rd.critique_mode };
  }).filter(rd => rd.mode === 'claim' && rd.totalClaims > 0);

  if (roundData.length < 1) return null;

  // Find claims that were contested in any round
  const contestedAcrossRounds = [];
  for (const rd of roundData) {
    for (const cv of rd.contested) {
      // Find which claim this is
      for (const [label, claimList] of Object.entries(rd.claims)) {
        for (const claim of claimList) {
          const vi = rd.verdicts[claim.id];
          if (vi && vi.majority_verdict !== 'strong') {
            contestedAcrossRounds.push({
              ...claim,
              sourceLabel: label,
              round: rd.round,
              verdict: vi.majority_verdict,
              agreement: vi.agreement,
            });
          }
        }
      }
    }
  }

  // Deduplicate by claim ID + round
  const seen = new Set();
  const uniqueContested = contestedAcrossRounds.filter(c => {
    const key = `${c.id}-${c.round}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return (
    <div className="claim-evolution">
      <div className="claim-evolution-header">
        <span className="claim-evolution-icon">📊</span>
        <span className="claim-evolution-title">{t('Claim Evolution Across Rounds')}</span>
      </div>

      {/* Round-by-round summary */}
      <div className="claim-evolution-rounds">
        {roundData.map((rd, i) => (
          <div key={rd.round} className="claim-evolution-round">
            <div className="evolution-round-header">
              <span className="evolution-round-badge">{t('Round {round}', { round: rd.round })}</span>
              <span className="evolution-round-stats">
                {t('{count} claims', { count: rd.totalClaims })}
              </span>
            </div>
            <div className="evolution-bar-container">
              <div
                className="evolution-bar strong"
                style={{ width: `${(rd.strong / rd.totalClaims) * 100}%` }}
              >
                {t('{count} strong', { count: rd.strong })}
              </div>
              {rd.contested.length > 0 && (
                <div
                  className="evolution-bar contested"
                  style={{ width: `${(rd.contested.length / rd.totalClaims) * 100}%` }}
                >
                  {t('{count} contested', { count: rd.contested.length })}
                </div>
              )}
            </div>
            {i < roundData.length - 1 && (
              <div className="evolution-arrow">↓</div>
            )}
          </div>
        ))}
      </div>

      {/* Contested claims detail */}
      {uniqueContested.length > 0 && (
        <div className="claim-evolution-contested">
          <div className="evolution-contested-label">{t('Claims That Were Contested')}</div>
          {uniqueContested.map((claim) => (
            <div key={`${claim.id}-${claim.round}`} className="evolution-contested-item">
              <span className="evolution-claim-id">{claim.id}</span>
              <span className="evolution-claim-round">R{claim.round}</span>
              <span className={`evolution-claim-verdict ${claim.verdict}`}>
                {claim.verdict?.toUpperCase()}
              </span>
              <span className="evolution-claim-text">&ldquo;{claim.claim}&rdquo;</span>
            </div>
          ))}
        </div>
      )}

      {uniqueContested.length === 0 && roundData.length >= 2 && (
        <div className="claim-all-strong-banner" style={{ marginTop: '12px' }}>
          <span className="check-icon">✓</span>
          {t('No claims were contested in any round. Full consensus across all evaluators.')}
        </div>
      )}
    </div>
  );
}

function ClaimCardDetailed({ claim, prominent, t }) {
  const [expanded, setExpanded] = useState(prominent);
  const verdictClass = claim.majority_verdict || 'unknown';
  const agreementPct = Math.round((claim.agreement || 0) * 100);

  return (
    <div className={`claim-card-detailed ${verdictClass} ${prominent ? 'prominent' : ''}`} onClick={() => setExpanded(!expanded)}>
      <div className="claim-header">
        <span className="claim-id">{claim.id}</span>
        <span className={`claim-verdict-badge ${verdictClass}`}>
          {claim.majority_verdict ? claim.majority_verdict.toUpperCase() : t('N/A')}
        </span>
        {claim.agreement != null && (
          <span className="claim-agreement">{agreementPct}%</span>
        )}
        <span className="claim-source-tag">{getShortModelName(claim.sourceModel)}</span>
      </div>
      <p className="claim-text">&ldquo;{claim.claim}&rdquo;</p>
      {expanded && claim.evaluator_verdicts && claim.evaluator_verdicts.length > 0 && (
        <div className="claim-evaluators">
          {claim.evaluator_verdicts.map((ev, i) => (
            <div key={i} className="evaluator-verdict">
              <span className="ev-model">{getShortModelName(ev.model)}</span>
              <span className={`ev-verdict ${ev.verdict}`}>{ev.verdict}</span>
              {ev.reason && <span className="ev-reason">{ev.reason}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ClaimCardCompact({ claim }) {
  const agreementPct = Math.round((claim.agreement || 0) * 100);
  return (
    <div className="claim-card-compact">
      <span className="claim-id">{claim.id}</span>
      <span className="claim-compact-text">{claim.claim}</span>
      <span className="claim-compact-pct">{agreementPct}%</span>
    </div>
  );
}

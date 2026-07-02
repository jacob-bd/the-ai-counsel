import { getRequestStatus } from './requestStatus';

/**
 * Pure view-model for Audit-mode (critique_mode === 'audit') Stage 2A/2B/2C results.
 * Normalizes both live-streamed and restored-conversation data at the boundary so
 * AuditResults.jsx stays a thin presentational shell. No React, no DOM — fully
 * testable under vitest's default Node environment.
 *
 * Backend shapes (authoritative, from backend/audit_pipeline.py):
 *   Stage 2B aggregate (metadata.aggregated_2b):
 *     { audit_status, valid_evaluators, expected_evaluators, claims_evaluated,
 *       aggregated_claims: [{ claim_id, canonical_text,
 *         support_counts: { supported, partially_supported, unsupported, contradicted, unverifiable },
 *         assessment_counts: { sound, requires_qualification, unsound, unverifiable } }] }
 *   Stage 2C result (message.stage2c / metadata.stage2c_result):
 *     { record: { adopt, reject, qualify, authority_gaps, record_gaps, stage3_constraints },
 *       model, raw_output, usage, cost, attempts }
 *     OR { error: true, error_message, model, attempts } on failure.
 *
 * Contested rule (matches backend format_aggregate_verdicts_for_prompt): a claim is
 * contested when ANY evaluator produced an adverse verdict —
 *   support: partially_supported | unsupported | contradicted | unverifiable
 *   assessment: requires_qualification | unsound | unverifiable
 * Never derive "strong" from plurality of supported/sound alone.
 */

export const STAGE2A_HEADING = 'Stage 2A: Holistic Evaluation';
export const STAGE2B_HEADING = 'Stage 2B: Claim Audit';
export const STAGE2C_HEADING = 'Stage 2C: Chairman Adjudication';

export const ADVERSE_SUPPORT_KEYS = ['partially_supported', 'unsupported', 'contradicted', 'unverifiable'];
export const ADVERSE_ASSESSMENT_KEYS = ['requires_qualification', 'unsound', 'unverifiable'];

export function shouldRenderAuditResults(critiqueMode) {
  return critiqueMode === 'audit';
}

/** Normalize live vs restored Stage 2C payload to a canonical shape. */
export function normalizeStage2c(stage2c, metadata = {}) {
  const raw = stage2c || metadata.stage2c_result || {};
  if (!raw || typeof raw !== 'object' || Object.keys(raw).length === 0) {
    return {
      record: null,
      model: null,
      rawOutput: null,
      error: false,
      errorMessage: null,
      attempts: [],
    };
  }
  // Live: raw is the full result wrapper { record, model, raw_output, ... }
  // Restored: raw may be the correction record itself (backend storage.py line 513
  // sets message.stage2c = correction_record, i.e. { adopt, reject, ... }).
  const isWrapper = Boolean(raw.record || raw.error || raw.model || raw.raw_output);
  if (isWrapper) {
    return {
      record: raw.record || null,
      model: raw.model || null,
      rawOutput: raw.raw_output || null,
      error: Boolean(raw.error),
      errorMessage: raw.error_message || null,
      attempts: raw.attempts || [],
    };
  }
  // Restored bare correction record.
  return {
    record: raw,
    model: metadata.stage2c_model || null,
    rawOutput: null,
    error: false,
    errorMessage: null,
    attempts: [],
  };
}

/** Restore precedence helper: prefer live message field, fall back to metadata. */
function pickResults(stageField, metadataKeys, metadata = {}) {
  if (stageField) return stageField;
  for (const key of metadataKeys) {
    const v = metadata[key];
    if (v && (!Array.isArray(v) || v.length > 0) && !(typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0)) {
      return v;
    }
  }
  return null;
}

/** Classify a single aggregated claim as 'strong' | 'contested'. */
export function classifyClaim(aggClaim) {
  const support = aggClaim.support_counts || {};
  const assessment = aggClaim.assessment_counts || {};
  const contested =
    ADVERSE_SUPPORT_KEYS.some((k) => (support[k] || 0) > 0) ||
    ADVERSE_ASSESSMENT_KEYS.some((k) => (assessment[k] || 0) > 0);
  return contested ? 'contested' : 'strong';
}

/** Build the Stage 2B view model from aggregate + results. */
export function buildStage2bView(stage2bResults, metadata = {}) {
  const aggregate = metadata.aggregated_2b || metadata.aggregate_claim_verdicts || {};
  const results = pickResults(stage2bResults, ['stage2b_results', 'stage2b', 'audits'], metadata) || [];

  const resultStatuses = results.map((r) => getRequestStatus(r || {}));
  const completedResults = results.filter(
    (r, index) => r && !r.error && resultStatuses[index] === 'completed'
  );
  const hasInProgressResults = resultStatuses.some((status) =>
    ['queued', 'running', 'paused'].includes(status)
  );

  const auditStatus = aggregate.audit_status || 'unknown';
  const validEvaluators = aggregate.valid_evaluators ?? completedResults.length;
  const expectedEvaluators = aggregate.expected_evaluators ?? results.length;
  const claimsEvaluated = aggregate.claims_evaluated ?? (aggregate.aggregated_claims || []).length;

  const aggregatedClaims = aggregate.aggregated_claims || [];
  const claims = aggregatedClaims.map((c) => ({
    claimId: c.claim_id,
    canonicalText: c.canonical_text || '',
    supportCounts: c.support_counts || {},
    assessmentCounts: c.assessment_counts || {},
    status: classifyClaim(c),
  }));
  const contestedCount = claims.filter((c) => c.status === 'contested').length;
  const strongCount = claims.filter((c) => c.status === 'strong').length;

  const quorumMet = auditStatus !== 'failed' && validEvaluators >= 2 && (expectedEvaluators === 0 || validEvaluators / Math.max(1, expectedEvaluators) >= 0.5);
  const partialCoverage = auditStatus === 'partial'
    || (!hasInProgressResults && validEvaluators > 0 && validEvaluators < expectedEvaluators);

  // Per-evaluator raw audits for expandable detail.
  const evaluatorAudits = results.map((r, index) => ({
    model: r?.model,
    status: resultStatuses[index],
    errorMessage: r?.error_message || null,
    claimVerdicts: r?.claim_verdicts || {},
  }));

  return {
    auditStatus,
    validEvaluators,
    expectedEvaluators,
    claimsEvaluated,
    claims,
    contestedCount,
    strongCount,
    quorumMet,
    partialCoverage,
    evaluatorAudits,
  };
}

/** Correction-record section normalization. */
export function buildCorrectionRecordSections(record) {
  const r = record || {};
  return [
    { key: 'adopt', label: 'Adopt', items: r.adopt || [] },
    { key: 'reject', label: 'Reject', items: r.reject || [] },
    { key: 'qualify', label: 'Qualify', items: r.qualify || [] },
    { key: 'authority_gaps', label: 'Authority Gaps', items: r.authority_gaps || [] },
    { key: 'record_gaps', label: 'Record Gaps', items: r.record_gaps || [] },
    { key: 'stage3_constraints', label: 'Stage 3 Constraints', items: r.stage3_constraints || [] },
  ];
}

/** Top-level view model used by AuditResults.jsx. */
export function buildAuditViewModel({ stage2a, stage2b, stage2c, metadata = {}, loading = {}, timers = {} } = {}) {
  const meta = metadata || {};
  const loadingState = loading && typeof loading === 'object' ? loading : {};
  const timerState = timers && typeof timers === 'object' ? timers : {};

  const stage2aResults = pickResults(stage2a, ['stage2a_results', 'stage2a', 'evaluations'], meta) || [];
  const stage2bView = buildStage2bView(stage2b, meta);
  const stage2cView = normalizeStage2c(stage2c, meta);

  const evaluators = stage2aResults.map((r) => ({
    model: r?.model,
    status: getRequestStatus(r || {}),
    errorMessage: r?.error_message || null,
    rawOutput: r?.raw_output || r?.ranking || r?.response || '',
    parsedRanking: r?.parsed_ranking || r?.parsed?.ranking || r?.parsed || [],
    attempts: r?.attempts || [],
  }));
  const coverage = {
    total: evaluators.length,
    completed: evaluators.filter((e) => e.status === 'completed').length,
    failed: evaluators.filter((e) => e.status === 'failed').length,
    queued: evaluators.filter((e) => e.status === 'queued').length,
    running: evaluators.filter((e) => e.status === 'running').length,
    paused: evaluators.filter((e) => e.status === 'paused').length,
    unaccounted: evaluators.filter((e) => e.status === 'unaccounted').length,
  };

  const aggregateRankings = meta.aggregate_rankings || [];
  const labelToModel = meta.label_to_model || {};

  return {
    stage2a: {
      heading: STAGE2A_HEADING,
      evaluators,
      coverage,
      aggregateRankings,
      labelToModel,
      loading: Boolean(loadingState.stage2a),
      duration: { start: timerState.stage2aStart, end: timerState.stage2aEnd },
    },
    stage2b: {
      heading: STAGE2B_HEADING,
      ...stage2bView,
      loading: Boolean(loadingState.stage2b),
      duration: { start: timerState.stage2bStart, end: timerState.stage2bEnd },
    },
    stage2c: {
      heading: STAGE2C_HEADING,
      ...stage2cView,
      sections: buildCorrectionRecordSections(stage2cView.record),
      loading: Boolean(loadingState.stage2c),
      duration: { start: timerState.stage2cStart, end: timerState.stage2cEnd },
    },
  };
}
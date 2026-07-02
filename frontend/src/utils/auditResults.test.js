import { describe, it, expect } from 'vitest';
import {
  shouldRenderAuditResults,
  classifyClaim,
  buildStage2bView,
  normalizeStage2c,
  buildCorrectionRecordSections,
  buildAuditViewModel,
  STAGE2A_HEADING,
  STAGE2B_HEADING,
  STAGE2C_HEADING,
} from './auditResults';

const twoA = [
  { model: 'modelA', raw_output: 'A eval', parsed_ranking: ['Response B', 'Response A'], attempts: [] },
  { model: 'modelB', raw_output: 'B eval', parsed_ranking: ['Response A', 'Response B'], attempts: [] },
];

const twoBAggregate = {
  audit_status: 'complete',
  valid_evaluators: 2,
  expected_evaluators: 2,
  claims_evaluated: 3,
  aggregated_claims: [
    { claim_id: 'C-001', canonical_text: 'Water boils at 100C at sea level.', support_counts: { supported: 2 }, assessment_counts: { sound: 2 } },
    { claim_id: 'C-002', canonical_text: 'Water boils at 99C.', support_counts: { supported: 1, unsupported: 1 }, assessment_counts: { sound: 1, unsound: 1 } },
    { claim_id: 'C-003', canonical_text: 'Perhaps pressure matters.', support_counts: { supported: 2 }, assessment_counts: { sound: 1, requires_qualification: 1 } },
  ],
};

const twoBResults = [
  { model: 'modelA', claim_verdicts: { 'C-001': { source_support: 'supported', substantive_assessment: 'sound' } } },
  { model: 'modelB', claim_verdicts: { 'C-001': { source_support: 'supported', substantive_assessment: 'sound' } } },
];

const twoCResult = {
  record: { adopt: ['C-001'], reject: ['C-002'], qualify: ['C-003'], authority_gaps: [], record_gaps: ['gap-1'], stage3_constraints: [] },
  model: 'chairman-model',
  raw_output: '{...raw...}',
  attempts: [],
};

describe('shouldRenderAuditResults', () => {
  it('returns true only for audit mode', () => {
    expect(shouldRenderAuditResults('audit')).toBe(true);
    expect(shouldRenderAuditResults('freeform')).toBe(false);
    expect(shouldRenderAuditResults('paragraph')).toBe(false);
    expect(shouldRenderAuditResults('claim')).toBe(false);
    expect(shouldRenderAuditResults(undefined)).toBe(false);
  });
});

describe('classifyClaim', () => {
  it('marks a claim strong only when no adverse counts exist', () => {
    expect(classifyClaim({ support_counts: { supported: 3 }, assessment_counts: { sound: 3 } })).toBe('strong');
  });
  it('marks a claim contested when any adverse support count exists', () => {
    expect(classifyClaim({ support_counts: { supported: 2, partially_supported: 1 }, assessment_counts: { sound: 3 } })).toBe('contested');
    expect(classifyClaim({ support_counts: { unsupported: 1 }, assessment_counts: {} })).toBe('contested');
  });
  it('marks a claim contested when any adverse assessment count exists', () => {
    expect(classifyClaim({ support_counts: { supported: 3 }, assessment_counts: { sound: 2, unsound: 1 } })).toBe('contested');
    expect(classifyClaim({ support_counts: {}, assessment_counts: { requires_qualification: 1 } })).toBe('contested');
  });
  it('does not derive strong from plurality of supported alone', () => {
    // supported=2 but one unsound => contested, NOT strong
    expect(classifyClaim({ support_counts: { supported: 2 }, assessment_counts: { unsound: 1 } })).toBe('contested');
  });
});

describe('buildStage2bView', () => {
  it('normalizes the audit aggregate and classifies claims', () => {
    const view = buildStage2bView(twoBResults, { aggregated_2b: twoBAggregate });
    expect(view.auditStatus).toBe('complete');
    expect(view.validEvaluators).toBe(2);
    expect(view.expectedEvaluators).toBe(2);
    expect(view.claimsEvaluated).toBe(3);
    expect(view.claims).toHaveLength(3);
    expect(view.contestedCount).toBe(2); // C-002 and C-003
    expect(view.strongCount).toBe(1); // C-001
    expect(view.quorumMet).toBe(true);
    expect(view.partialCoverage).toBe(false);
    expect(view.evaluatorAudits).toHaveLength(2);
  });

  it('reports partial coverage when valid < expected', () => {
    const agg = { ...twoBAggregate, audit_status: 'partial', valid_evaluators: 1, expected_evaluators: 2 };
    const view = buildStage2bView(twoBResults, { aggregated_2b: agg });
    expect(view.partialCoverage).toBe(true);
    expect(view.quorumMet).toBe(false); // valid_evaluators=1 < MIN_VALID_EVALUATORS=2
  });

  it('reports quorum failure when below threshold', () => {
    const agg = { audit_status: 'failed', valid_evaluators: 1, expected_evaluators: 2, claims_evaluated: 0, aggregated_claims: [] };
    const view = buildStage2bView([{ model: 'a', error: true }, { model: 'b', error: true }], { aggregated_2b: agg });
    expect(view.quorumMet).toBe(false);
    expect(view.claims).toHaveLength(0);
  });

  it('falls back to metadata.stage2b_results when stage2b results not passed directly', () => {
    const view = buildStage2bView(null, { aggregated_2b: twoBAggregate, stage2b_results: twoBResults });
    expect(view.evaluatorAudits).toHaveLength(2);
    expect(view.auditStatus).toBe('complete');
  });

  it('does not count queued or running placeholders as valid evaluators', () => {
    const view = buildStage2bView([
      { model: 'modelA', status: 'queued' },
      { model: 'modelB', status: 'running' },
    ]);

    expect(view.validEvaluators).toBe(0);
    expect(view.expectedEvaluators).toBe(2);
    expect(view.quorumMet).toBe(false);
    expect(view.partialCoverage).toBe(false);
    expect(view.evaluatorAudits.map((audit) => audit.status)).toEqual(['queued', 'running']);
  });
});

describe('normalizeStage2c', () => {
  it('unwraps a live result wrapper', () => {
    const n = normalizeStage2c(twoCResult, {});
    expect(n.record).toEqual(twoCResult.record);
    expect(n.model).toBe('chairman-model');
    expect(n.rawOutput).toBe('{...raw...}');
    expect(n.error).toBe(false);
  });
  it('handles a restored bare correction record', () => {
    const n = normalizeStage2c(twoCResult.record, { stage2c_result: null });
    expect(n.record).toEqual(twoCResult.record);
    expect(n.rawOutput).toBeNull();
  });
  it('preferentially uses metadata.stage2c_result when stage2c absent', () => {
    const n = normalizeStage2c(null, { stage2c_result: twoCResult });
    expect(n.record).toEqual(twoCResult.record);
    expect(n.model).toBe('chairman-model');
  });
  it('surfaces error payloads', () => {
    const n = normalizeStage2c({ error: true, error_message: 'Stage 2C failed', model: 'c' }, {});
    expect(n.error).toBe(true);
    expect(n.errorMessage).toBe('Stage 2C failed');
  });
});

describe('buildCorrectionRecordSections', () => {
  it('returns all six sections with empty-state items arrays', () => {
    const sections = buildCorrectionRecordSections(twoCResult.record);
    expect(sections).toHaveLength(6);
    const byKey = Object.fromEntries(sections.map((s) => [s.key, s]));
    expect(byKey.adopt.items).toEqual(['C-001']);
    expect(byKey.reject.items).toEqual(['C-002']);
    expect(byKey.qualify.items).toEqual(['C-003']);
    expect(byKey.authority_gaps.items).toEqual([]);
    expect(byKey.record_gaps.items).toEqual(['gap-1']);
    expect(byKey.stage3_constraints.items).toEqual([]);
  });
  it('returns empty items arrays for a null record', () => {
    const sections = buildCorrectionRecordSections(null);
    expect(sections.every((s) => s.items.length === 0)).toBe(true);
  });
});

describe('buildAuditViewModel', () => {
  it('renders all three stage headings', () => {
    const vm = buildAuditViewModel({
      stage2a: twoA,
      stage2b: twoBResults,
      stage2c: twoCResult,
      metadata: { aggregated_2b: twoBAggregate, label_to_model: { A: 'modelA', B: 'modelB' } },
      loading: {},
      timers: {},
    });
    expect(vm.stage2a.heading).toBe(STAGE2A_HEADING);
    expect(vm.stage2b.heading).toBe(STAGE2B_HEADING);
    expect(vm.stage2c.heading).toBe(STAGE2C_HEADING);
    expect(vm.stage2a.evaluators).toHaveLength(2);
    expect(vm.stage2a.coverage.completed).toBe(2);
    expect(vm.stage2b.contestedCount).toBe(2);
    expect(vm.stage2c.sections).toHaveLength(6);
  });

  it('reports loading state per stage without fabricating completed data', () => {
    const vm = buildAuditViewModel({
      stage2a: null,
      stage2b: null,
      stage2c: null,
      metadata: {},
      loading: { stage2: true, stage2a: true, stage2b: false, stage2c: false },
      timers: {},
    });
    expect(vm.stage2a.loading).toBe(true);
    expect(vm.stage2a.evaluators).toHaveLength(0);
    expect(vm.stage2b.loading).toBe(false);
    expect(vm.stage2c.loading).toBe(false);
  });

  it('does not project the legacy aggregate Stage 2 flag onto substages', () => {
    const vm = buildAuditViewModel({
      stage2a: null,
      stage2b: null,
      stage2c: null,
      metadata: {},
      loading: { stage2: true },
      timers: {},
    });

    expect(vm.stage2a.loading).toBe(false);
    expect(vm.stage2b.loading).toBe(false);
    expect(vm.stage2c.loading).toBe(false);
  });

  it('preserves Stage 2A queued and running statuses in coverage', () => {
    const vm = buildAuditViewModel({
      stage2a: [
        { model: 'modelA', status: 'queued' },
        { model: 'modelB', status: 'running' },
      ],
      metadata: {},
      loading: { stage2a: true },
      timers: {},
    });

    expect(vm.stage2a.evaluators.map((evaluator) => evaluator.status)).toEqual(['queued', 'running']);
    expect(vm.stage2a.coverage.completed).toBe(0);
    expect(vm.stage2a.coverage.queued).toBe(1);
    expect(vm.stage2a.coverage.running).toBe(1);
  });

  it('terminates Stage 2C loading after an error event', () => {
    // Error payloads arrive with loading flags already cleared by the reducer
    // (stage2c_error sets loading.stage2c=false). The view model must reflect
    // that: not loading, error visible, no perpetual spinner.
    const vm = buildAuditViewModel({
      stage2c: { error: true, error_message: 'API Failure' },
      metadata: {},
      loading: { stage2c: false, stage2: false },
      timers: {},
    });
    expect(vm.stage2c.loading).toBe(false);
    expect(vm.stage2c.error).toBe(true);
    expect(vm.stage2c.errorMessage).toBe('API Failure');
  });

  it('renders from restored metadata shape only (no live stage fields)', () => {
    const vm = buildAuditViewModel({
      stage2a: null,
      stage2b: null,
      stage2c: null,
      metadata: {
        stage2a_results: twoA,
        stage2b_results: twoBResults,
        stage2c_result: twoCResult,
        aggregated_2b: twoBAggregate,
        label_to_model: { A: 'modelA', B: 'modelB' },
      },
      loading: {},
      timers: {},
    });
    expect(vm.stage2a.evaluators).toHaveLength(2);
    expect(vm.stage2b.evaluatorAudits).toHaveLength(2);
    expect(vm.stage2c.record).toEqual(twoCResult.record);
    expect(vm.stage2c.sections).toHaveLength(6);
  });

  it('does not throw when loading and timers are null', () => {
    const vm = buildAuditViewModel({
      stage2a: null,
      stage2b: null,
      stage2c: null,
      metadata: {},
      loading: null,
      timers: null,
    });
    expect(vm.stage2a.loading).toBe(false);
    expect(vm.stage2b.loading).toBe(false);
    expect(vm.stage2c.loading).toBe(false);
    expect(vm.stage2a.duration.start).toBeUndefined();
  });
});
import { describe, it, expect } from 'vitest';
import { auditEventReducer } from './auditEventReducer';

describe('auditEventReducer', () => {
  const initialMessage = {
    role: 'assistant',
    stage1: [],
    stage2: null,
    stage3: null,
    metadata: {},
    loading: {
      search: false,
      stage1: false,
      stage2: false,
      stage3: false,
      stage4: false,
      stage2a: false,
      stage2b: false,
      stage2c: false,
    },
    timers: {
      stage1Start: null,
      stage1End: null,
      stage2Start: null,
      stage2End: null,
      stage3Start: null,
      stage3End: null,
      stage4Start: null,
      stage4End: null,
      stage2aStart: null,
      stage2aEnd: null,
      stage2bStart: null,
      stage2bEnd: null,
      stage2cStart: null,
      stage2cEnd: null,
    },
    progress: {
      stage1: { count: 0, total: 0, currentModel: null },
      stage2: { count: 0, total: 0, currentModel: null },
      stage2a: { count: 0, total: 0, currentModel: null },
      stage2b: { count: 0, total: 0, currentModel: null },
    }
  };

  const councilModels = ['modelA', 'modelB'];

  it('starts Stage 2A timers and loading state', () => {
    const nextState = auditEventReducer(initialMessage, { type: 'stage2a_start' }, councilModels);

    expect(nextState.loading.stage2).toBe(true);
    expect(nextState.loading.stage2a).toBe(true);
    expect(nextState.timers.stage2Start).not.toBeNull();
    expect(nextState.timers.stage2aStart).not.toBeNull();
  });

  it('uses the authoritative request manifest and initializes queued rows', () => {
    const event = {
      type: 'stage2_init',
      total: 2,
      models: ['manifestA', 'manifestB'],
      label_to_model: { 'Response A': 'manifestA', 'Response B': 'manifestB' },
    };
    const nextState = auditEventReducer(initialMessage, event, councilModels);

    expect(nextState.stage2.map((row) => row.model)).toEqual(['manifestA', 'manifestB']);
    expect(nextState.stage2.every((row) => row.status === 'queued')).toBe(true);
    expect(nextState.metadata.label_to_model).toEqual(event.label_to_model);
  });

  it('marks a completed progress result as terminal', () => {
    const initialized = auditEventReducer(
      initialMessage,
      { type: 'stage2a_init', total: 2, models: councilModels },
      councilModels
    );
    const nextState = auditEventReducer(initialized, {
      type: 'stage2a_progress',
      count: 1,
      total: 2,
      data: { model: 'modelA', response: 'Evaluated' }
    }, councilModels);

    expect(nextState.progress.stage2.currentModel).toBe('modelA');
    expect(nextState.stage2[0]).toMatchObject({
      model: 'modelA',
      response: 'Evaluated',
      status: 'completed',
    });
    expect(nextState.stage2[1].status).toBe('queued');
  });

  it('preserves every expected model and marks a missing terminal result unaccounted', () => {
    const initialized = auditEventReducer(
      initialMessage,
      { type: 'stage2_init', total: 2, models: councilModels },
      councilModels
    );
    const nextState = auditEventReducer(initialized, {
      type: 'stage2_complete',
      data: [{ model: 'modelA', ranking: 'A, B', parsed_ranking: ['Response A', 'Response B'] }],
      metadata: { aggregate_rankings: [] },
    }, councilModels);

    expect(nextState.stage2).toHaveLength(2);
    expect(nextState.stage2[0].status).toBe('completed');
    expect(nextState.stage2[1]).toMatchObject({
      model: 'modelB',
      status: 'unaccounted',
      error: true,
      unaccounted: true,
    });
  });

  it('handles Stage 2B lifecycle and reconciles missing results', () => {
    let state = auditEventReducer(initialMessage, { type: 'stage2b_start' }, councilModels);
    state = auditEventReducer(state, { type: 'stage2b_init', total: 2, models: councilModels }, councilModels);
    state = auditEventReducer(state, {
      type: 'stage2b_progress',
      count: 1,
      total: 2,
      data: { model: 'modelA', claim_verdicts: {} }
    }, councilModels);
    state = auditEventReducer(state, {
      type: 'stage2b_complete',
      data: [{ model: 'modelA', claim_verdicts: {} }]
    }, councilModels);

    expect(state.loading.stage2b).toBe(false);
    expect(state.stage2b[0].status).toBe('completed');
    expect(state.stage2b[1].status).toBe('unaccounted');
    expect(state.timers.stage2bEnd).not.toBeNull();
  });

  it('handles Stage 2C completion metadata', () => {
    let state = auditEventReducer(initialMessage, { type: 'stage2c_start' }, councilModels);
    state = auditEventReducer(state, {
      type: 'stage2c_complete',
      data: { adopt: ['C-001'] },
      aggregated: { claims: [] }
    }, councilModels);

    expect(state.loading.stage2c).toBe(false);
    expect(state.loading.stage2).toBe(false);
    expect(state.metadata.aggregated_2b).toEqual({ claims: [] });
    expect(state.metadata.stage2c_result).toEqual({ adopt: ['C-001'] });
  });

  it('handles an audit-stage error', () => {
    const nextState = auditEventReducer(
      initialMessage,
      { type: 'stage2a_error', message: 'Quorum failed' },
      councilModels
    );

    expect(nextState.loading.stage2).toBe(false);
    expect(nextState.loading.stage2a).toBe(false);
    expect(nextState.error).toBe('Quorum failed');
  });
});

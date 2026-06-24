import { describe, expect, it } from 'vitest';
import {
  getRequestStatus,
  markTerminalResult,
  reconcileTerminalResults,
} from './requestStatus';

describe('requestStatus', () => {
  it('distinguishes queued, running, paused, failed, and completed states', () => {
    expect(getRequestStatus({ pending: true })).toBe('queued');
    expect(getRequestStatus({ firing: true })).toBe('running');
    expect(getRequestStatus({ paused: true })).toBe('paused');
    expect(getRequestStatus({ error: true })).toBe('failed');
    expect(getRequestStatus({ response: 'done' })).toBe('completed');
  });

  it('marks terminal results and clears active flags', () => {
    expect(markTerminalResult({ model: 'm', firing: true, response: 'done' })).toMatchObject({
      model: 'm',
      status: 'completed',
      firing: false,
      running: false,
    });
  });

  it('preserves the manifest and emits an explicit unaccounted row', () => {
    const reconciled = reconcileTerminalResults(
      [{ model: 'a', status: 'running' }, { model: 'b', status: 'queued' }],
      [{ model: 'a', ranking: 'ok' }],
      ['a', 'b']
    );

    expect(reconciled).toHaveLength(2);
    expect(reconciled[0].status).toBe('completed');
    expect(reconciled[1]).toMatchObject({
      model: 'b',
      status: 'unaccounted',
      error: true,
    });
  });
});

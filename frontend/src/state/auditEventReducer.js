import { markTerminalResult, reconcileTerminalResults } from '../utils/requestStatus';

/**
 * Pure state reducer for handling Stage 2 (including Audit mode sub-stages) SSE events.
 */
export function auditEventReducer(message, event, councilModels = []) {
  const now = Date.now();

  switch (event.type) {
    case 'stage2_start':
    case 'stage2a_start': {
      const isAudit = event.type === 'stage2a_start';
      return {
        ...message,
        loading: {
          ...message.loading,
          stage2: true,
          stage2a: isAudit ? true : message.loading.stage2a,
        },
        timers: {
          ...message.timers,
          stage2Start: message.timers.stage2Start || now,
          stage2aStart: isAudit ? now : message.timers.stage2aStart,
        }
      };
    }

    case 'stage2_init':
    case 'stage2a_init': {
      const isAudit = event.type === 'stage2a_init';
      const manifestModels = event.models?.length
        ? event.models
        : Object.values(event.label_to_model || {});
      const models = manifestModels.length > 0 ? manifestModels : (councilModels || []);
      const initialStage2 = models.map((model) => ({ model, status: 'queued' }));
      return {
        ...message,
        progress: {
          ...message.progress,
          stage2: {
            count: 0,
            total: event.total,
            currentModel: null
          },
          ...(isAudit ? {
            stage2a: {
              count: 0,
              total: event.total,
              currentModel: null
            }
          } : {})
        },
        stage2: initialStage2,
        ...(isAudit ? { stage2a: initialStage2 } : {}),
        metadata: {
          ...message.metadata,
          ...(event.label_to_model ? { label_to_model: event.label_to_model } : {}),
        },
      };
    }

    case 'stage2_progress':
    case 'stage2a_progress': {
      const isAudit = event.type === 'stage2a_progress';
      const lastStage2 = isAudit ? (message.stage2a || message.stage2) : message.stage2;
      const terminalResult = markTerminalResult(event.data);
      const updatedStage2 = lastStage2
        ? lastStage2.some((result) => result.model === terminalResult.model)
          ? lastStage2.map((result) => result.model === terminalResult.model ? terminalResult : result)
          : [...lastStage2, terminalResult]
        : [terminalResult];

      return {
        ...message,
        progress: {
          ...message.progress,
          stage2: {
            count: event.count,
            total: event.total,
            currentModel: terminalResult.model
          },
          ...(isAudit ? {
            stage2a: {
              count: event.count,
              total: event.total,
              currentModel: terminalResult.model
            }
          } : {})
        },
        stage2: updatedStage2,
        ...(isAudit ? { stage2a: updatedStage2 } : {})
      };
    }

    case 'stage2_complete':
    case 'stage2a_complete': {
      const isAudit = event.type === 'stage2a_complete';
      const current = isAudit ? (message.stage2a || message.stage2 || []) : (message.stage2 || []);
      const expectedModels = event.models?.length
        ? event.models
        : current.map((result) => result.model).filter(Boolean);
      const reconciled = reconcileTerminalResults(current, event.data || [], expectedModels);
      return {
        ...message,
        stage2: reconciled,
        ...(isAudit ? { stage2a: reconciled } : {}),
        loading: {
          ...message.loading,
          stage2a: isAudit ? false : message.loading.stage2a,
          stage2: isAudit ? message.loading.stage2 : false,
        },
        timers: {
          ...message.timers,
          stage2aEnd: isAudit ? now : message.timers.stage2aEnd,
          stage2End: isAudit ? message.timers.stage2End : now,
        },
        metadata: {
          ...message.metadata,
          ...event.metadata,
          ...(event.label_to_model ? { label_to_model: event.label_to_model } : {}),
        }
      };
    }

    case 'stage2b_start':
      return {
        ...message,
        loading: {
          ...message.loading,
          stage2b: true,
        },
        timers: {
          ...message.timers,
          stage2bStart: now,
        }
      };

    case 'stage2b_init': {
      const models = event.models?.length ? event.models : (councilModels || []);
      const initialStage2b = models.map((model) => ({ model, status: 'queued' }));
      return {
        ...message,
        progress: {
          ...message.progress,
          stage2b: {
            count: 0,
            total: event.total,
            currentModel: null
          }
        },
        stage2b: initialStage2b,
      };
    }

    case 'stage2b_progress': {
      const terminalResult = markTerminalResult(event.data);
      const updatedStage2b = message.stage2b
        ? message.stage2b.some((result) => result.model === terminalResult.model)
          ? message.stage2b.map((result) => result.model === terminalResult.model ? terminalResult : result)
          : [...message.stage2b, terminalResult]
        : [terminalResult];

      return {
        ...message,
        progress: {
          ...message.progress,
          stage2b: {
            count: event.count,
            total: event.total,
            currentModel: terminalResult.model
          }
        },
        stage2b: updatedStage2b,
      };
    }

    case 'stage2b_complete': {
      const current = message.stage2b || [];
      const expectedModels = event.models?.length
        ? event.models
        : current.map((result) => result.model).filter(Boolean);
      return {
        ...message,
        stage2b: reconcileTerminalResults(current, event.data || [], expectedModels),
        loading: {
          ...message.loading,
          stage2b: false,
        },
        timers: {
          ...message.timers,
          stage2bEnd: now,
        }
      };
    }

    case 'stage2c_start':
      return {
        ...message,
        loading: {
          ...message.loading,
          stage2c: true,
        },
        timers: {
          ...message.timers,
          stage2cStart: now,
        }
      };

    case 'stage2c_complete':
      return {
        ...message,
        stage2c: event.data,
        loading: {
          ...message.loading,
          stage2c: false,
          stage2: false,
        },
        timers: {
          ...message.timers,
          stage2cEnd: now,
          stage2End: now,
        },
        metadata: {
          ...message.metadata,
          aggregated_2b: event.aggregated,
          stage2c_result: event.data,
        }
      };

    case 'stage2a_error':
    case 'stage2b_error':
    case 'stage2c_error':
      return {
        ...message,
        loading: {
          ...message.loading,
          stage2: false,
          stage2a: false,
          stage2b: false,
          stage2c: false,
        },
        error: event.message,
      };

    default:
      return message;
  }
}

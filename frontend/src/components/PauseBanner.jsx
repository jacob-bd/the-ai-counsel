import React from 'react';

export default function PauseBanner({
  failedModel,
  pendingCount,
  continuationMode,
  onModeChange,
  onResume,
  onAbort
}) {
  const getShortModelName = (modelId) => {
    if (!modelId) return 'Unknown';
    if (modelId.includes('/')) return modelId.split('/').pop();
    if (modelId.includes(':')) return modelId.split(':').pop();
    return modelId;
  };

  return (
    <div style={{
      background: 'rgba(30, 27, 22, 0.75)',
      border: '1px solid rgba(251, 191, 36, 0.35)',
      backdropFilter: 'blur(12px)',
      borderRadius: '12px',
      padding: '16px 20px',
      margin: '20px 0',
      display: 'flex',
      flexDirection: 'column',
      gap: '14px',
      boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.4)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <span style={{
          color: '#fbbf24',
          fontSize: '20px',
          display: 'flex',
          alignItems: 'center'
        }}>
          ⚠️
        </span>
        <div style={{ flex: 1 }}>
          <h4 style={{ margin: 0, fontSize: '15px', fontWeight: '600', color: '#f3f4f6' }}>
            Run Paused — {getShortModelName(failedModel)} Failed
          </h4>
          <p style={{ margin: '3px 0 0 0', fontSize: '12px', color: '#94a3b8' }}>
            {pendingCount} provider(s) still pending. Choose a continuation mode and click Resume, or manually fire pending models.
          </p>
        </div>
      </div>

      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        borderTop: '1px solid rgba(255, 255, 255, 0.06)',
        paddingTop: '12px'
      }}>
        <label style={{ fontSize: '12px', fontWeight: '500', color: '#94a3b8' }}>
          Continuation Mode for Remaining Providers:
        </label>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {[
            ['normal', 'Normal', 'Resume with current settings'],
            ['fail_safe', 'Fail-Safe', '30s wait + 5–13s stagger delay'],
            ['conservative', 'Conservative', '1 concurrent · 15–25s delay · 2x timeout']
          ].map(([val, label, desc]) => (
            <div
              key={val}
              onClick={() => onModeChange(val)}
              style={{
                flex: 1,
                minWidth: '150px',
                padding: '10px 14px',
                borderRadius: '8px',
                border: `1px solid ${continuationMode === val ? 'rgba(251, 191, 36, 0.5)' : 'rgba(255, 255, 255, 0.06)'}`,
                background: continuationMode === val ? 'rgba(251, 191, 36, 0.08)' : 'rgba(255, 255, 255, 0.02)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <div style={{
                fontSize: '12px',
                fontWeight: '600',
                color: continuationMode === val ? '#fbbf24' : '#e5e7eb',
                marginBottom: '2px'
              }}>
                {label}
              </div>
              <div style={{ fontSize: '10px', color: '#94a3b8' }}>{desc}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{
        display: 'flex',
        justifyContent: 'flex-end',
        alignItems: 'center',
        gap: '10px',
        marginTop: '6px'
      }}>
        <button
          onClick={onAbort}
          style={{
            background: 'transparent',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            color: '#ef4444',
            padding: '8px 16px',
            borderRadius: '6px',
            fontSize: '13px',
            fontWeight: '500',
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          Abort Run
        </button>
        <button
          onClick={onResume}
          style={{
            background: 'linear-gradient(135deg, #fbbf24 0%, #d97706 100%)',
            border: 'none',
            color: '#1e1b16',
            padding: '8px 20px',
            borderRadius: '6px',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer',
            transition: 'all 0.15s ease',
            boxShadow: '0 2px 8px rgba(217, 119, 6, 0.3)'
          }}
        >
          ▶ Resume Automated
        </button>
      </div>
    </div>
  );
}

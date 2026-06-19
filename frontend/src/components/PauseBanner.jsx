import React from 'react';

export default function PauseBanner({
  failedModel,
  pendingCount,
  activeProviders = [],
  pendingProviders = [],
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

  const hasProviderDetail = activeProviders.length > 0 || pendingProviders.length > 0;

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
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <span style={{ color: '#fbbf24', fontSize: '20px', display: 'flex', alignItems: 'center' }}>
          ⚠️
        </span>
        <div style={{ flex: 1 }}>
          <h4 style={{ margin: 0, fontSize: '15px', fontWeight: '600', color: '#f3f4f6' }}>
            Run Paused — {getShortModelName(failedModel)} Failed
          </h4>
          <p style={{ margin: '3px 0 0 0', fontSize: '12px', color: '#94a3b8' }}>
            {hasProviderDetail
              ? `${activeProviders.length} in-flight · ${pendingProviders.length} not yet started`
              : `${pendingCount} provider(s) still pending`}
            . Choose a continuation mode and click Resume, or manually fire pending models.
          </p>
        </div>
      </div>

      {/* Provider status breakdown */}
      {hasProviderDetail && (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          borderTop: '1px solid rgba(255,255,255,0.06)',
          paddingTop: '12px',
        }}>
          {/* In-flight */}
          {activeProviders.length > 0 && (
            <div>
              <div style={{ fontSize: '11px', fontWeight: '600', color: '#fbbf24', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                🔄 In-Flight — Already Executing
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {activeProviders.map((m) => (
                  <span key={m} style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '4px 10px',
                    borderRadius: '20px',
                    background: 'rgba(251, 191, 36, 0.1)',
                    border: '1px solid rgba(251, 191, 36, 0.3)',
                    fontSize: '11px',
                    color: '#fbbf24',
                    fontWeight: '500',
                  }}>
                    <span style={{
                      width: '6px', height: '6px', borderRadius: '50%',
                      background: '#fbbf24',
                      boxShadow: '0 0 0 0 rgba(251,191,36,0.4)',
                      animation: 'pausePulse 1.4s ease-in-out infinite',
                    }} />
                    {getShortModelName(m)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Not yet started */}
          {pendingProviders.length > 0 && (
            <div>
              <div style={{ fontSize: '11px', fontWeight: '600', color: '#94a3b8', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                ⏸ Not Yet Started — Can Fire Manually
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {pendingProviders.map((m) => (
                  <span key={m} style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '4px 10px',
                    borderRadius: '20px',
                    background: 'rgba(148, 163, 184, 0.08)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    fontSize: '11px',
                    color: '#94a3b8',
                    fontWeight: '500',
                  }}>
                    <span style={{
                      width: '6px', height: '6px', borderRadius: '50%',
                      background: '#64748b',
                    }} />
                    {getShortModelName(m)}
                  </span>
                ))}
              </div>
            </div>
          )}

          <style>{`
            @keyframes pausePulse {
              0%   { box-shadow: 0 0 0 0   rgba(251,191,36,0.5); }
              70%  { box-shadow: 0 0 0 6px rgba(251,191,36,0); }
              100% { box-shadow: 0 0 0 0   rgba(251,191,36,0); }
            }
          `}</style>
        </div>
      )}

      {/* Continuation mode selector */}
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

      {/* Action buttons */}
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

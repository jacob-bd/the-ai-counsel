import { useState, useEffect } from 'react';
import Skeleton from './common/Skeleton';
import { getModelVisuals, getShortModelName } from '../utils/modelHelpers';
import { copyToClipboard } from '../utils/clipboard';
import ThinkBlockRenderer from './ThinkBlockRenderer';
import StageTimer from './StageTimer';
import './Stage1.css';

export default function Stage1({ responses, startTime, endTime, onRetryProvider, onFireProvider }) {
  const [activeTab, setActiveTab] = useState(0);

  // Reset activeTab if it becomes out of bounds
  useEffect(() => {
    if (responses && responses.length > 0 && activeTab >= responses.length) {
      setActiveTab(responses.length - 1);
    }
  }, [responses, activeTab]);

  if (!responses || responses.length === 0) {
    return null;
  }

  const safeActiveTab = Math.min(activeTab, responses.length - 1);
  const currentResponse = responses[safeActiveTab] || {};
  const hasError = currentResponse?.error || false;

  const gridColumns = Math.min(responses.length, 4);

  // Get visuals for current tab
  const currentVisuals = getModelVisuals(currentResponse?.model);

  // Copy functionality
  const [isCopied, setIsCopied] = useState(false);

  // Reset copy state when tab changes
  useEffect(() => {
    setIsCopied(false);
  }, [activeTab]);

  const handleCopy = async () => {
    const textToCopy = typeof currentResponse.response === 'string'
      ? currentResponse.response
      : String(currentResponse.response || '');

    if (!textToCopy) return;

    const copied = await copyToClipboard(textToCopy);
    if (copied) {
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    }
  };

  return (
    <div className="stage-container stage-1">
      <div className="stage-header">
        <div className="stage-title">
          <span className="stage-icon">💬</span>
          Stage 1: Individual Perspectives
        </div>
        <StageTimer startTime={startTime} endTime={endTime} label="Duration" />
      </div>

      {/* Avatar Tabs */}
      <div
        className="tabs"
        style={{ gridTemplateColumns: `repeat(${gridColumns}, 1fr)` }}
      >
        {responses.map((resp, index) => {
          const visuals = getModelVisuals(resp?.model);
          const shortName = getShortModelName(resp?.model);

          return (
            <button
              key={index}
              className={`tab ${safeActiveTab === index ? 'active' : ''} ${resp?.error ? 'tab-error' : ''}`}
              onClick={() => setActiveTab(index)}
              style={safeActiveTab === index ? { borderColor: visuals.color, color: visuals.color } : {}}
              title={resp?.model}
            >
              <span className="tab-icon" style={{ backgroundColor: safeActiveTab === index ? 'transparent' : 'rgba(255,255,255,0.1)' }}>
                {visuals.icon}
              </span>
              <span className="tab-name">{shortName}</span>
              {resp?.error && <span className="error-badge" style={{ backgroundColor: '#ef4444' }}>!</span>}
              {resp?.retrying && <span className="error-badge" style={{ backgroundColor: '#3b82f6' }}>↺</span>}
              {resp?.pending && <span className="error-badge" style={{ backgroundColor: '#6b7280' }}>…</span>}
            </button>
          );
        })}
      </div>

      <div className="tab-content glass-panel">
        <div className="model-header">
          <div className="model-identity">
            <span className="model-avatar" style={{ backgroundColor: hasError ? '#ef4444' : currentVisuals.color }}>
              {currentVisuals.icon}
            </span>
            <div className="model-info">
              <span className="model-name-large">{currentResponse.model || 'Unknown Model'}</span>
              <span className="model-provider-badge" style={{ borderColor: currentVisuals.color, color: currentVisuals.color }}>
                {currentVisuals.name}
              </span>
            </div>
          </div>

          <div className="header-actions">
            {!hasError && (
              <button
                className={`copy-button ${isCopied ? 'copied' : ''}`}
                onClick={handleCopy}
                title="Copy to clipboard"
              >
                {isCopied ? (
                  <>
                    <span className="icon">✓</span>
                    <span className="label">Copied</span>
                  </>
                ) : (
                  <>
                    <span className="icon">📋</span>
                    <span className="label">Copy</span>
                  </>
                )}
              </button>
            )}

            {currentResponse.pending ? (
              <span className="model-status pending" style={{ borderColor: '#6b7280', color: '#94a3b8' }}>Pending</span>
            ) : hasError ? (
              <span className="model-status error">Failed</span>
            ) : (
              <span className="model-status success">Completed</span>
            )}
          </div>
        </div>

        {currentResponse.pending ? (
          <div className="response-pending" style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '20px 0' }}>
            <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
              <div className="pending-icon" style={{ fontSize: '24px' }}>⏳</div>
              <div className="pending-details">
                <div className="pending-title" style={{ fontSize: '15px', fontWeight: '600', color: '#e5e7eb' }}>Request Paused (Pending)</div>
                <div className="pending-message" style={{ fontSize: '13px', color: '#94a3b8' }}>This model is held. You can resume the automated run or trigger it individually.</div>
              </div>
            </div>
            {onFireProvider && (
              <button
                className="fire-provider-button"
                onClick={() => onFireProvider(currentResponse.model, 'stage1')}
                style={{
                  alignSelf: 'flex-start',
                  background: 'rgba(16,185,129,0.1)',
                  border: '1px solid rgba(16,185,129,0.4)',
                  color: '#10b981',
                  padding: '6px 14px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '12px',
                  fontWeight: '500',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  transition: 'all 0.15s ease'
                }}
              >
                ▶ Fire Manually
              </button>
            )}
          </div>
        ) : hasError ? (
          <div className="response-error" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
              <div className="error-icon">⚠️</div>
              <div className="error-details">
                <div className="error-title">Model Failed to Respond</div>
                <div className="error-message">{currentResponse?.error_message || 'Unknown error'}</div>
              </div>
            </div>
            {onRetryProvider && !currentResponse.retrying && (
              <button
                className="retry-provider-button"
                onClick={() => onRetryProvider(currentResponse.model, 'stage1')}
                style={{
                  alignSelf: 'flex-start',
                  background: 'rgba(59,130,246,0.1)',
                  border: '1px solid rgba(59,130,246,0.4)',
                  color: '#60a5fa',
                  padding: '6px 14px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '12px',
                  fontWeight: '500',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  transition: 'all 0.15s ease'
                }}
              >
                ↺ Retry {getShortModelName(currentResponse.model)}
              </button>
            )}
            {currentResponse.retrying && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#60a5fa', fontSize: '13px' }}>
                <span className="retrying-indicator">↺</span> Retrying {getShortModelName(currentResponse.model)}...
              </div>
            )}
          </div>
        ) : (
          <div className="response-text markdown-content">
            <ThinkBlockRenderer
              content={
                typeof currentResponse.response === 'string'
                  ? currentResponse.response
                  : String(currentResponse.response || 'No response')
              }
            />
          </div>
        )}
      </div>
    </div>
  );
}

export function Stage1Skeleton() {
  return (
    <div className="stage-container stage-1 skeleton-mode">
      <div className="stage-header">
        <div className="stage-title">
          <span className="stage-icon">💬</span>
          Stage 1: Individual Perspectives
        </div>
        <div className="stage-timer-skeleton">
          <Skeleton variant="text" width="60px" />
        </div>
      </div>

      {/* Tabs Skeleton */}
      <div className="tabs" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="tab skeleton-tab">
            <Skeleton variant="circle" width="24px" height="24px" style={{ marginBottom: '8px' }} />
            <Skeleton variant="text" width="60%" height="0.8em" />
          </div>
        ))}
      </div>

      <div className="tab-content glass-panel">
        <div className="model-header">
          <div className="model-identity">
            <Skeleton variant="avatar" />
            <div className="model-info" style={{ gap: '4px', display: 'flex', flexDirection: 'column' }}>
              <Skeleton variant="text" width="120px" height="1.2em" />
              <Skeleton variant="text" width="80px" height="0.8em" />
            </div>
          </div>
          <div className="header-actions">
            <Skeleton variant="rect" width="60px" height="24px" style={{ borderRadius: '12px' }} />
          </div>
        </div>

        <div className="response-text">
          <Skeleton variant="text" width="100%" />
          <Skeleton variant="text" width="95%" />
          <Skeleton variant="text" width="90%" />
          <br />
          <Skeleton variant="text" width="100%" />
          <Skeleton variant="text" width="85%" />
        </div>
      </div>
    </div>
  );
}

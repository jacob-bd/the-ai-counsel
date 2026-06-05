import { useState, useEffect } from 'react';
import Skeleton from './common/Skeleton';
import { getModelVisuals, getShortModelName } from '../utils/modelHelpers';
import { copyToClipboard } from '../utils/clipboard';
import ThinkBlockRenderer from './ThinkBlockRenderer';
import StageTimer from './StageTimer';
import './Stage1.css';

export default function Stage1({ responses, startTime, endTime }) {
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
              style={safeActiveTab === index ? { borderColor: visuals.color, color: '#f8fafc' } : {}}
              title={resp?.model}
            >
              <span
                className="tab-icon"
                style={{
                  backgroundColor: safeActiveTab === index ? visuals.color : 'rgba(255,255,255,0.1)',
                  color: safeActiveTab === index ? '#ffffff' : undefined
                }}>
                {visuals.icon}
              </span>
              <span className="tab-name">{shortName}</span>
              {resp?.error && <span className="error-badge">!</span>}
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
              <span className="model-name-large">{getShortModelName(currentResponse.model) || 'Unknown Model'}</span>
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

            {hasError ? (
              <span className="model-status error">Failed</span>
            ) : (
              <span className="model-status success">Completed</span>
            )}
          </div>
        </div>

        {hasError ? (
          <div className="response-error">
            <div className="error-icon">⚠️</div>
            <div className="error-details">
              <div className="error-title">Model Failed to Respond</div>
              <div className="error-message">{currentResponse?.error_message || 'Unknown error'}</div>
            </div>
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

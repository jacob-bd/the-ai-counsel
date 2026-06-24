import { useState, useEffect } from 'react';
import Skeleton from './common/Skeleton';
import { getModelVisuals, getShortModelName } from '../utils/modelHelpers';
import { getRequestStatus, getRequestStatusLabel } from '../utils/requestStatus';
import { copyToClipboard } from '../utils/clipboard';
import ThinkBlockRenderer from './ThinkBlockRenderer';
import StageTimer from './StageTimer';
import ModelVisualIcon from './ModelVisualIcon';
import './Stage1.css';

export default function Stage1({ responses, startTime, endTime, onRetryProvider, onFireProvider }) {
  const [activeTab, setActiveTab] = useState(0);
  const [isCopied, setIsCopied] = useState(false);

  useEffect(() => {
    if (responses && responses.length > 0 && activeTab >= responses.length) {
      const timer = setTimeout(() => setActiveTab(responses.length - 1), 0);
      return () => clearTimeout(timer);
    }
  }, [responses, activeTab]);

  useEffect(() => {
    const timer = setTimeout(() => setIsCopied(false), 0);
    return () => clearTimeout(timer);
  }, [activeTab]);

  if (!responses || responses.length === 0) return null;

  const safeActiveTab = Math.min(activeTab, responses.length - 1);
  const currentResponse = responses[safeActiveTab] || {};
  const requestStatus = getRequestStatus(currentResponse);
  const hasError = requestStatus === 'failed' || requestStatus === 'unaccounted';
  const isQueued = requestStatus === 'queued';
  const isRunning = requestStatus === 'running';
  const isPaused = requestStatus === 'paused';
  const isCompleted = requestStatus === 'completed';
  const gridColumns = Math.min(responses.length, 4);
  const currentVisuals = getModelVisuals(currentResponse?.model);

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

      <div className="tabs" style={{ gridTemplateColumns: `repeat(${gridColumns}, 1fr)` }}>
        {responses.map((response, index) => {
          const visuals = getModelVisuals(response?.model);
          const shortName = getShortModelName(response?.model);
          const status = getRequestStatus(response);
          const statusError = status === 'failed' || status === 'unaccounted';
          return (
            <button
              key={response?.model || index}
              className={`tab ${safeActiveTab === index ? 'active' : ''} ${statusError ? 'tab-error' : ''}`}
              onClick={() => setActiveTab(index)}
              style={safeActiveTab === index ? { borderColor: visuals.color, color: visuals.color } : {}}
              title={`${response?.model || 'Unknown model'} — ${getRequestStatusLabel(status)}`}
            >
              <span className="tab-icon" style={{ backgroundColor: safeActiveTab === index ? 'transparent' : 'rgba(255,255,255,0.1)' }}>
                <ModelVisualIcon visuals={visuals} scale={0.7} />
              </span>
              <span className="tab-name">{shortName}</span>
              {statusError && <span className="error-badge" style={{ backgroundColor: '#ef4444' }}>!</span>}
              {status === 'running' && <span className="error-badge" style={{ backgroundColor: '#3b82f6' }}>↻</span>}
              {status === 'queued' && <span className="error-badge" style={{ backgroundColor: '#6b7280' }}>…</span>}
              {status === 'paused' && <span className="error-badge" style={{ backgroundColor: '#d97706' }}>Ⅱ</span>}
            </button>
          );
        })}
      </div>

      <div className="tab-content glass-panel">
        <div className="model-header">
          <div className="model-identity">
            <span className="model-avatar" style={{ backgroundColor: hasError ? '#ef4444' : currentVisuals.color }}>
              <ModelVisualIcon visuals={currentVisuals} scale={0.72} />
            </span>
            <div className="model-info">
              <span className="model-name-large" title={currentResponse.model || ''}>
                {getShortModelName(currentResponse.model)}
              </span>
              <span className="model-provider-badge" style={{ borderColor: currentVisuals.color, color: currentVisuals.color }}>
                {currentVisuals.name}
              </span>
            </div>
          </div>

          <div className="header-actions">
            {isCompleted && (
              <button className={`copy-button ${isCopied ? 'copied' : ''}`} onClick={handleCopy} title="Copy to clipboard">
                {isCopied ? <><span className="icon">✓</span><span className="label">Copied</span></> : <><span className="icon">📋</span><span className="label">Copy</span></>}
              </button>
            )}
            <span className={`model-status ${requestStatus}`}>
              {getRequestStatusLabel(requestStatus)}
            </span>
          </div>
        </div>

        {isQueued ? (
          <RequestState
            icon="⏳"
            title="Queued"
            message="Waiting for an execution slot. This request has not been dispatched yet."
          />
        ) : isRunning ? (
          <RequestState
            icon="↻"
            title="Request Running"
            message="The request was dispatched and the model is actively generating a response."
            accent="#60a5fa"
          />
        ) : isPaused ? (
          <div className="response-pending" style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '20px 0' }}>
            <RequestState
              icon="⏸"
              title="Request Paused"
              message="The run is paused before this model starts. Resume the run or trigger this request individually."
              accent="#fbbf24"
            />
            {onFireProvider && (
              <button className="fire-provider-button" onClick={() => onFireProvider(currentResponse.model, 'stage1')} style={fireButtonStyle}>
                ▶ Run This Request
              </button>
            )}
          </div>
        ) : hasError ? (
          <div className="response-error" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
              <div className="error-icon">⚠️</div>
              <div className="error-details">
                <div className="error-title">{requestStatus === 'unaccounted' ? 'Request Result Missing' : 'Model Failed to Respond'}</div>
                <div className="error-message">{currentResponse?.error_message || 'Unknown error'}</div>
              </div>
            </div>
            {onRetryProvider && !currentResponse.retrying && requestStatus !== 'unaccounted' && (
              <button className="retry-provider-button" onClick={() => onRetryProvider(currentResponse.model, 'stage1')} style={retryButtonStyle}>
                ↺ Retry {getShortModelName(currentResponse.model)}
              </button>
            )}
          </div>
        ) : (
          <div className="response-text markdown-content">
            <ThinkBlockRenderer content={typeof currentResponse.response === 'string' ? currentResponse.response : String(currentResponse.response || 'No response')} />
          </div>
        )}
      </div>
    </div>
  );
}

function RequestState({ icon, title, message, accent = '#e5e7eb' }) {
  return (
    <div style={{ display: 'flex', gap: '14px', alignItems: 'center', padding: '20px 0' }} role="status">
      <div style={{ fontSize: '24px', color: accent }}>{icon}</div>
      <div>
        <div style={{ fontSize: '15px', fontWeight: '600', color: accent }}>{title}</div>
        <div style={{ fontSize: '13px', color: '#94a3b8' }}>{message}</div>
      </div>
    </div>
  );
}

const fireButtonStyle = {
  alignSelf: 'flex-start', background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.4)',
  color: '#10b981', padding: '6px 14px', borderRadius: '6px', cursor: 'pointer', fontSize: '12px',
  fontWeight: '500', display: 'flex', alignItems: 'center', gap: '6px', transition: 'all 0.15s ease'
};

const retryButtonStyle = {
  alignSelf: 'flex-start', background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.4)',
  color: '#60a5fa', padding: '6px 14px', borderRadius: '6px', cursor: 'pointer', fontSize: '12px',
  fontWeight: '500', display: 'flex', alignItems: 'center', gap: '6px', transition: 'all 0.15s ease'
};

export function Stage1Skeleton() {
  return (
    <div className="stage-container stage-1 skeleton-mode">
      <div className="stage-header">
        <div className="stage-title"><span className="stage-icon">💬</span>Stage 1: Individual Perspectives</div>
        <div className="stage-timer-skeleton"><Skeleton variant="text" width="60px" /></div>
      </div>
      <div className="tabs" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        {[1, 2, 3, 4].map((index) => (
          <div key={index} className="tab skeleton-tab">
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
          <div className="header-actions"><Skeleton variant="rect" width="60px" height="24px" style={{ borderRadius: '12px' }} /></div>
        </div>
        <div className="response-text">
          <Skeleton variant="text" width="100%" /><Skeleton variant="text" width="95%" /><Skeleton variant="text" width="90%" />
          <br /><Skeleton variant="text" width="100%" /><Skeleton variant="text" width="85%" />
        </div>
      </div>
    </div>
  );
}

import React, { useEffect, useRef, useState } from 'react';
import { api } from '../../api';
import { OAUTH_PROVIDERS } from '../../constants/oauthProviders';
import { useI18n } from '../../i18n';

const POLL_MS = 2000;

export default function SubscriptionOAuth({
  settings,
  onSettingsChange,
  onModelsRefresh,
  directAvailableModels = [],
}) {
  const { t } = useI18n();
  const [sessions, setSessions] = useState({});
  const [busy, setBusy] = useState({});
  const [errors, setErrors] = useState({});
  const pollTimers = useRef({});

  useEffect(() => () => {
    Object.values(pollTimers.current).forEach(clearInterval);
  }, []);

  const stopPolling = (providerId) => {
    if (pollTimers.current[providerId]) {
      clearInterval(pollTimers.current[providerId]);
      delete pollTimers.current[providerId];
    }
  };

  const handleComplete = async (providerId) => {
    stopPolling(providerId);
    setSessions((prev) => {
      const next = { ...prev };
      delete next[providerId];
      return next;
    });
    setBusy((prev) => ({ ...prev, [providerId]: false }));
    const data = await api.getSettings();
    onSettingsChange?.(data);
    await onModelsRefresh?.();
  };

  const startPolling = (providerId, sessionId) => {
    stopPolling(providerId);
    pollTimers.current[providerId] = setInterval(async () => {
      try {
        const status = await api.oauthStatus(providerId, sessionId);
        if (status.status === 'complete') {
          await handleComplete(providerId);
        } else if (status.status === 'error' || status.status === 'expired') {
          stopPolling(providerId);
          setErrors((prev) => ({
            ...prev,
            [providerId]: status.error || 'Authorization failed or expired',
          }));
          setBusy((prev) => ({ ...prev, [providerId]: false }));
        }
      } catch (err) {
        stopPolling(providerId);
        setErrors((prev) => ({ ...prev, [providerId]: err.message }));
        setBusy((prev) => ({ ...prev, [providerId]: false }));
      }
    }, POLL_MS);
  };

  const handleConnect = async (providerId) => {
    setErrors((prev) => ({ ...prev, [providerId]: null }));
    setBusy((prev) => ({ ...prev, [providerId]: true }));
    try {
      const result = await api.startOAuth(providerId);
      setSessions((prev) => ({ ...prev, [providerId]: result }));
      startPolling(providerId, result.session_id);
    } catch (err) {
      setErrors((prev) => ({ ...prev, [providerId]: err.message }));
      setBusy((prev) => ({ ...prev, [providerId]: false }));
    }
  };

  const handleDisconnect = async (providerId) => {
    setErrors((prev) => ({ ...prev, [providerId]: null }));
    setBusy((prev) => ({ ...prev, [providerId]: true }));
    stopPolling(providerId);
    try {
      await api.disconnectOAuth(providerId);
      setSessions((prev) => {
        const next = { ...prev };
        delete next[providerId];
        return next;
      });
      const data = await api.getSettings();
      onSettingsChange?.(data);
      await onModelsRefresh?.();
    } catch (err) {
      setErrors((prev) => ({ ...prev, [providerId]: err.message }));
    } finally {
      setBusy((prev) => ({ ...prev, [providerId]: false }));
    }
  };

  const openVerification = (session) => {
    const url = session.verification_uri_complete || session.verification_uri;
    if (url) window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="subsection" style={{ marginTop: '24px' }}>
      <h4>{t('Subscription Logins')}</h4>
      <p className="subsection-description" style={{ fontSize: 'calc(13px * var(--font-scale))', color: '#94a3b8', marginBottom: '16px' }}>
        {t('Connect paid subscriptions via OAuth device login. These use your personal subscription through third-party tooling — not official API billing. Use at your own discretion.')}
      </p>

      {OAUTH_PROVIDERS.map((provider) => {
        const connected = !!settings?.[provider.connectedKey];
        const session = sessions[provider.id];
        const isBusy = busy[provider.id];
        const error = errors[provider.id];
        const modelCount = (directAvailableModels || []).filter(
          (m) => m.source === provider.id || m.id?.startsWith(`${provider.id}:`)
        ).length;

        return (
          <div key={provider.id} className="api-key-section oauth-provider-section">
            <label>{provider.label}</label>
            <p className="api-key-hint" style={{ marginTop: 0, marginBottom: '10px' }}>
              {t(provider.description)}
            </p>

            {connected && !session && (
              <div className="key-status set key-status-row">
                <span>
                  ✓ {t('Connected')}
                  {provider.id === 'github-copilot' && settings?.github_copilot_is_free_plan === true && (
                    <> · {t('Free plan')}</>
                  )}
                  {provider.id === 'github-copilot' && settings?.github_copilot_is_free_plan === false && (
                    <> · {t('Paid')}{settings?.github_copilot_plan ? ` (${settings.github_copilot_plan})` : ''}</>
                  )}
                  {modelCount > 0 && <> · {t(modelCount === 1 ? '{count} model available' : '{count} models available', { count: modelCount })}</>}
                </span>
                <button
                  type="button"
                  className="test-button danger"
                  onClick={() => handleDisconnect(provider.id)}
                  disabled={isBusy}
                >
                  {isBusy ? t('Disconnecting…') : t('Disconnect')}
                </button>
              </div>
            )}

            {!connected && !session && (
              <button
                type="button"
                className="test-button"
                onClick={() => handleConnect(provider.id)}
                disabled={isBusy}
              >
                {isBusy ? t('Starting…') : t('Connect')}
              </button>
            )}

            {session && (
              <div className="oauth-device-flow">
                <p className="oauth-instructions">
                  {t('Open the verification page and enter this code:')}
                </p>
                <div className="oauth-user-code">{session.user_code}</div>
                <div className="oauth-actions">
                  <button
                    type="button"
                    className="action-btn"
                    onClick={() => openVerification(session)}
                  >
                    {t('Open verification page')}
                  </button>
                  <span className="oauth-waiting">{t('Waiting for authorization…')}</span>
                </div>
              </div>
            )}

            {error && (
              <div className="test-result error">{t(error)}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

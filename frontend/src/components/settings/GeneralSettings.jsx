import React from 'react';
import { formatDatePart } from '../../utils/dateFormat';
import { RESPONSE_LANGUAGE_DEFAULT, RESPONSE_LANGUAGES_FALLBACK } from '../../constants/responseLanguages';

export { RESPONSE_LANGUAGE_DEFAULT };

export default function GeneralSettings({
  dateFormat,
  onDateFormatChange,
  responseLanguage,
  onResponseLanguageChange,
  responseLanguages = RESPONSE_LANGUAGES_FALLBACK,
  // relay-ai import (optional — desktop only feature)
  settings,
  relayItems = [],
  relaySelected = [],
  setRelaySelected,
  relayBannerVisible = false,
  relayDiscoverBusy = false,
  relayImportBusy = false,
  relayImportMessage = null,
  relayDiscoverReason = null,
  onDiscoverRelayAi,
  onImportRelayAi,
  onDismissRelayBanner,
}) {
  return (
    <section className="settings-section">
      <h3>General</h3>
      <p className="section-description">
        Display and language preferences for the application interface and model responses.
        Changes save automatically.
      </p>

      <div className="subsection">
        <h4>Display Preferences</h4>
        <div className="general-setting-row">
          <label htmlFor="date-format-select" className="general-setting-label">Date Format</label>
          <select
            id="date-format-select"
            value={dateFormat}
            onChange={(e) => onDateFormatChange(e.target.value)}
            className="select-input general-setting-select"
          >
            <option value="auto">Auto (browser locale)</option>
            <option value="MM/DD/YYYY">MM/DD/YYYY (US)</option>
            <option value="DD/MM/YYYY">DD/MM/YYYY (Europe / intl.)</option>
            <option value="YYYY-MM-DD">YYYY-MM-DD (ISO)</option>
          </select>
          <span className="general-setting-hint">
            Sidebar preview: {formatDatePart(new Date(), dateFormat)}
          </span>
        </div>
      </div>

      <div className="subsection general-subsection-divider">
        <h4>Response Language</h4>
        <p className="section-description general-section-note">
          Council and advisor models will be instructed to respond in this language.
          Conversation titles and internal search queries stay in English.
        </p>
        <div className="general-setting-row">
          <label htmlFor="response-language-select" className="general-setting-label">Model responses</label>
          <select
            id="response-language-select"
            value={responseLanguage}
            onChange={(e) => onResponseLanguageChange(e.target.value)}
            className="select-input general-setting-select"
          >
            {responseLanguages.map((lang) => (
              <option key={lang} value={lang}>{lang}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="subsection general-subsection-divider">
        <h4>Import from relay-ai</h4>
        <p className="section-description">
          Copy credentials from a local relay-ai install (OS keystore). Imported keys are saved to your
          chosen credential store (Encrypted file or OS keystore) — not into settings.json — so Retest
          works without re-pasting. Click Discover only when you want to scan; macOS Keychain may ask
          once per credential (use Always Allow). Import may ask again for large/chunked secrets.
        </p>

        {relayBannerVisible && relayItems.length > 0 && !settings?.relay_ai_import_dismissed && (
          <div className="relay-import-banner">
            <div className="relay-import-banner-text">
              Found {relayItems.length} credential{relayItems.length === 1 ? '' : 's'} in relay-ai that can be imported.
            </div>
            <button type="button" className="cancel-button" onClick={onDismissRelayBanner}>
              Dismiss
            </button>
          </div>
        )}

        <button
          type="button"
          className="action-btn"
          onClick={onDiscoverRelayAi}
          disabled={relayDiscoverBusy}
          style={{ marginBottom: '12px' }}
        >
          {relayDiscoverBusy ? 'Discovering…' : 'Discover credentials'}
        </button>

        {relayDiscoverReason && relayItems.length === 0 && (
          <p className="api-key-hint">{relayDiscoverReason}</p>
        )}

        {relayImportMessage && (
          <div
            className={`test-result ${relayImportMessage.tone === 'error' ? 'error' : 'success'}`}
            style={{ marginBottom: '12px' }}
            role="status"
          >
            {relayImportMessage.text}
          </div>
        )}

        {relayItems.length > 0 && (
          <div className="relay-import-list">
            {relayItems.map((item) => (
              <label key={item.relay_id} className="relay-import-item">
                <input
                  type="checkbox"
                  checked={relaySelected.includes(item.relay_id)}
                  onChange={(e) => {
                    setRelaySelected?.((prev) => (
                      e.target.checked
                        ? [...prev, item.relay_id]
                        : prev.filter((id) => id !== item.relay_id)
                    ));
                  }}
                />
                <span>
                  {item.label}
                  {item.already_configured_in_counsel && (
                    <span className="toggle-hint"> · already in Counsel</span>
                  )}
                </span>
              </label>
            ))}
            <div className="council-actions" style={{ marginTop: '12px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <button
                type="button"
                className="action-btn"
                onClick={onImportRelayAi}
                disabled={relayImportBusy || relaySelected.length === 0}
              >
                {relayImportBusy ? 'Importing…' : `Import selected (${relaySelected.length})`}
              </button>
              {!settings?.relay_ai_import_dismissed && (
                <button type="button" className="cancel-button" onClick={onDismissRelayBanner}>
                  Dismiss notice
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

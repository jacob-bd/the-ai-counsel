import React from 'react';
import { formatDatePart } from '../../utils/dateFormat';
import { FONT_SIZE_OPTIONS } from '../../utils/fontSize';
import { RESPONSE_LANGUAGE_DEFAULT, RESPONSE_LANGUAGES_FALLBACK } from '../../constants/responseLanguages';
import { useI18n } from '../../i18n';

export { RESPONSE_LANGUAGE_DEFAULT };

export default function GeneralSettings({
  dateFormat,
  onDateFormatChange,
  fontSize,
  onFontSizeChange,
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
  const { t } = useI18n();

  return (
    <section className="settings-section">
      <h3>{t('General')}</h3>
      <p className="section-description">
        {t('Display and language preferences for the application interface and model responses. Changes save automatically.')}
      </p>

      <div className="subsection">
        <h4>{t('Display Preferences')}</h4>
        <div className="general-setting-row">
          <label htmlFor="date-format-select" className="general-setting-label">{t('Date Format')}</label>
          <select
            id="date-format-select"
            value={dateFormat}
            onChange={(e) => onDateFormatChange(e.target.value)}
            className="select-input general-setting-select"
          >
            <option value="auto">{t('Auto (browser locale)')}</option>
            <option value="MM/DD/YYYY">{t('MM/DD/YYYY (US)')}</option>
            <option value="DD/MM/YYYY">{t('DD/MM/YYYY (Europe / intl.)')}</option>
            <option value="YYYY-MM-DD">{t('YYYY-MM-DD (ISO)')}</option>
          </select>
          <span className="general-setting-hint">
            {t('Sidebar preview: {date}', { date: formatDatePart(new Date(), dateFormat) })}
          </span>
        </div>
        <div className="general-setting-row">
          <label htmlFor="font-size-select" className="general-setting-label">{t('Font Size')}</label>
          <select
            id="font-size-select"
            value={fontSize}
            onChange={(e) => onFontSizeChange(e.target.value)}
            className="select-input general-setting-select"
          >
            {FONT_SIZE_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>{t(label)}</option>
            ))}
          </select>
          <span className="general-setting-hint">
            {t('Scales all text across the application. Saves automatically.')}
          </span>
        </div>
      </div>

      <div className="subsection general-subsection-divider">
        <h4>{t('Response Language')}</h4>
        <p className="section-description general-section-note">
          {t('Council and advisor models will be instructed to respond in this language. Conversation titles and internal search queries stay in English.')}
        </p>
        <div className="general-setting-row">
          <label htmlFor="response-language-select" className="general-setting-label">{t('Model responses')}</label>
          <select
            id="response-language-select"
            value={responseLanguage}
            onChange={(e) => onResponseLanguageChange(e.target.value)}
            className="select-input general-setting-select"
          >
            {responseLanguages.map((lang) => (
              <option key={lang} value={lang}>{t(lang)}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="subsection general-subsection-divider">
        <h4>{t('Import from relay-ai')}</h4>
        <p className="section-description">
          {t('Copy credentials from a local relay-ai install (OS keystore). Imported keys are saved to your chosen credential store (local file or OS keystore) — not into settings.json — so Retest works without re-pasting. Click Discover only when you want to scan; macOS Keychain may ask once per credential (use Always Allow). Import may ask again for large/chunked secrets.')}
        </p>

        {relayBannerVisible && relayItems.length > 0 && !settings?.relay_ai_import_dismissed && (
          <div className="relay-import-banner">
            <div className="relay-import-banner-text">
              {t(
                relayItems.length === 1
                  ? 'Found {count} credential in relay-ai that can be imported.'
                  : 'Found {count} credentials in relay-ai that can be imported.',
                { count: relayItems.length }
              )}
            </div>
            <button type="button" className="cancel-button" onClick={onDismissRelayBanner}>
              {t('Dismiss')}
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
          {relayDiscoverBusy ? t('Discovering…') : t('Discover credentials')}
        </button>

        {relayDiscoverReason && relayItems.length === 0 && (
          <p className="api-key-hint">{t(relayDiscoverReason)}</p>
        )}

        {relayImportMessage && (
          <div
            className={`test-result ${relayImportMessage.tone === 'error' ? 'error' : 'success'}`}
            style={{ marginBottom: '12px' }}
            role="status"
          >
            {t(relayImportMessage.text)}
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
                    <span className="toggle-hint"> · {t('already in Counsel')}</span>
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
                {relayImportBusy ? t('Importing…') : t('Import selected ({count})', { count: relaySelected.length })}
              </button>
              {!settings?.relay_ai_import_dismissed && (
                <button type="button" className="cancel-button" onClick={onDismissRelayBanner}>
                  {t('Dismiss notice')}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

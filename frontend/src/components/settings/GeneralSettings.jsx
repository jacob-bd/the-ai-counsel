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
  modelTimeoutSeconds,
  onModelTimeoutChange,
  preflightTimeoutSeconds,
  onPreflightTimeoutChange,
  claimExtractionTimeoutSeconds,
  onClaimExtractionTimeoutChange,
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
        <h4>Timeout Configuration</h4>
        <p className="section-description general-section-note">
          Configure maximum execution times for model queries, startup preflight checks, and claim extraction.
        </p>
        
        <div className="general-setting-row">
          <label htmlFor="model-timeout-input" className="general-setting-label" style={{ minWidth: '220px' }}>
            Model Query Timeout
          </label>
          <input
            id="model-timeout-input"
            type="number"
            min="30"
            max="1800"
            value={modelTimeoutSeconds}
            onChange={(e) => onModelTimeoutChange(parseInt(e.target.value) || 300)}
            className="select-input general-setting-select"
            style={{ width: '90px', padding: '6px 10px' }}
          />
          <span className="general-setting-hint">
            Time limit for individual model responses (30–1800s).
          </span>
        </div>

        <div className="general-setting-row" style={{ marginTop: '16px' }}>
          <label htmlFor="preflight-timeout-input" className="general-setting-label" style={{ minWidth: '220px' }}>
            Preflight Check Timeout
          </label>
          <input
            id="preflight-timeout-input"
            type="number"
            min="1"
            max="120"
            value={preflightTimeoutSeconds}
            onChange={(e) => onPreflightTimeoutChange(parseFloat(e.target.value) || 10.0)}
            className="select-input general-setting-select"
            style={{ width: '90px', padding: '6px 10px' }}
          />
          <span className="general-setting-hint">
            Timeout for checking model availability on startup (1–120s).
          </span>
        </div>

        <div className="general-setting-row" style={{ marginTop: '16px' }}>
          <label htmlFor="claim-timeout-input" className="general-setting-label" style={{ minWidth: '220px' }}>
            Claim Extraction Timeout
          </label>
          <input
            id="claim-timeout-input"
            type="number"
            min="10"
            max="600"
            value={claimExtractionTimeoutSeconds}
            onChange={(e) => onClaimExtractionTimeoutChange(parseFloat(e.target.value) || 180.0)}
            className="select-input general-setting-select"
            style={{ width: '90px', padding: '6px 10px' }}
          />
          <span className="general-setting-hint">
            Limit for the Chairman to decompose responses into claims (10–600s).
          </span>
        </div>
      </div>
    </section>
  );
}


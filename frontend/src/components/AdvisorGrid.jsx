import React from 'react';
import { getShortModelName } from '../utils/modelHelpers';
import { useI18n } from '../i18n';
import './AdvisorGrid.css';

export default function AdvisorGrid({
  personas = [],
  activePersonaId = null,
  round = 1,
  maxRounds = 3,
  isRunning = false,
}) {
  const { t } = useI18n();
  if (!personas || personas.length === 0) return null;

  return (
    <div className="advisor-grid-wrapper">
      <div className="advisor-round-indicator">
        {t('Round {round} of {maxRounds}', { round, maxRounds })}
      </div>
      <div className="advisor-grid">
        {personas.map((persona) => {
          const isActive = persona.id === activePersonaId;

          let cardState = 'idle';
          if (isActive) {
            cardState = 'thinking';
          } else if (isRunning) {
            cardState = 'waiting';
          }

          return (
            <div
              key={persona.id}
              className={`advisor-card advisor-card--${cardState}`}
              style={{ '--persona-color': persona.color }}
            >
              <div className="advisor-avatar-wrap">
                <div
                  className="advisor-avatar"
                  style={{ backgroundColor: persona.color + '26' }}
                >
                  <span className="advisor-emoji">{persona.avatar_emoji}</span>
                  {cardState === 'thinking' && (
                    <div
                      className="advisor-thinking-ring"
                      style={{ borderColor: persona.color }}
                    />
                  )}
                  {!isRunning && !isActive && round > 1 && (
                    <div className="advisor-done-badge">✓</div>
                  )}
                </div>
              </div>
              <div className="advisor-info">
                <span className="advisor-name">{persona.name}</span>
                <span className="advisor-role">{persona.role}</span>
                {persona.model && (
                  <span className="advisor-model">{getShortModelName(persona.model)}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


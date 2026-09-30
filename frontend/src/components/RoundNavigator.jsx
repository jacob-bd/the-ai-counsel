import React from 'react';
import { useI18n } from '../i18n';
import './RoundNavigator.css';

export default function RoundNavigator({ currentRound, totalRounds, converged, onSelectRound }) {
  const { t } = useI18n();
  if (!totalRounds || totalRounds <= 1) return null;

  return (
    <div className="round-navigator">
      <div className="round-dots">
        {Array.from({ length: totalRounds }, (_, i) => {
          const roundNum = i + 1;
          const isCompleted = roundNum < currentRound;
          const isActive = roundNum === currentRound;
          return (
            <div
              key={roundNum}
              className={`round-dot ${isCompleted ? 'completed' : ''} ${isActive ? 'active' : ''} ${onSelectRound ? 'clickable' : ''}`}
              title={t('Round {round}', { round: roundNum })}
              onClick={() => onSelectRound && onSelectRound(roundNum)}
            />
          );
        })}
      </div>
      <span className="round-label">
        {t('Round {current} of {total}', { current: currentRound, total: totalRounds })}
        {converged && t(' — Converged')}
      </span>
    </div>
  );
}

import './ExecutionModeToggle.css';
import { useI18n } from '../i18n';

export default function ExecutionModeToggle({ value, onChange, disabled, chairmanModel }) {
    const { t } = useI18n();
    const hasChairman = !!(chairmanModel && chairmanModel.trim());

    const modes = [
        { id: 'chat_only', label: t('Chat Only'), icon: '💬' },
        { id: 'chat_ranking', label: t('Chat + Ranking'), icon: '⚖️' },
        { id: 'full', label: t('Full Deliberation'), icon: '🏛️', needsChairman: true }
    ];

    return (
        <div className="execution-mode-toggle" role="radiogroup" aria-label={t('Execution Mode')}>
            {modes.map(mode => {
                const locked = mode.needsChairman && !hasChairman;
                const isDisabled = disabled || locked;
                return (
                    <button
                        key={mode.id}
                        type="button"
                        role="radio"
                        aria-checked={value === mode.id}
                        className={`mode-option ${value === mode.id ? 'active' : ''} ${locked ? 'locked' : ''}`}
                        onClick={() => !isDisabled && onChange(mode.id)}
                        disabled={isDisabled}
                        title={locked ? t('Select a chairman model to enable Full Deliberation') : mode.label}
                    >
                        <span className="mode-icon">{mode.icon}</span>
                        <span className="mode-label">{mode.label}</span>
                    </button>
                );
            })}
        </div>
    );
}

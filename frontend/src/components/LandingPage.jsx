import './LandingPage.css';
import { useI18n } from '../i18n';

const CouncilIcon = () => (
  <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="24" cy="10" r="3.5" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="10" cy="34" r="3.5" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="38" cy="34" r="3.5" stroke="currentColor" strokeWidth="1.5" />
    <line x1="24" y1="13.5" x2="10" y2="30.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <line x1="24" y1="13.5" x2="38" y2="30.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <line x1="10" y1="34" x2="38" y2="34" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <line x1="24" y1="13.5" x2="24" y2="30.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="2 3" />
  </svg>
);

const AdvisorsIcon = () => (
  <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="18" y="6" width="12" height="12" rx="6" stroke="currentColor" strokeWidth="1.5" />
    <rect x="6" y="30" width="10" height="10" rx="5" stroke="currentColor" strokeWidth="1.5" />
    <rect x="32" y="30" width="10" height="10" rx="5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M24 18 L11 30" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M24 18 L37 30" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M16 35 L32 35" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="2 2.5" />
  </svg>
);

export default function LandingPage({ onSelectMode }) {
  const { t } = useI18n();
  return (
    <div className="landing-page">
      <div className="landing-orb landing-orb--blue" />
      <div className="landing-orb landing-orb--violet" />
      <div className="landing-grid" />

      <div className="landing-inner">
        <div className="landing-header">
          <div className="landing-eyebrow">{t('Multi-model AI deliberation')}</div>
          <h1 className="landing-title">
            The AI <span className="landing-title__plus">Counsel</span>
          </h1>
          <p className="landing-subtitle">{t('Choose Council for answers. Choose Advisors for decisions.')}</p>
        </div>

        <div className="landing-cards">
          <button className="landing-card landing-card--council" onClick={() => onSelectMode('council')}>
            <div className="landing-card__glow" />
            <div className="landing-card__content">
              <div className="landing-card__icon landing-card__icon--council">
                <CouncilIcon />
              </div>
              <div className="landing-card__body">
                <div className="landing-card__label">{t('LLM Council')}</div>
                <h2 className="landing-card__title">{t('Multi-Model Deliberation')}</h2>
                <p className="landing-card__desc">
                  {t('Multiple AI models answer in parallel, rank each other anonymously, and a chairman synthesizes the best response.')}
                </p>
                <ul className="landing-card__features">
                  <li>{t('Best for facts, summaries, creative prompts')}</li>
                  <li>{t('Use when you want one strong answer')}</li>
                  <li>{t('Peer ranking plus chairman synthesis')}</li>
                </ul>
              </div>
              <div className="landing-card__cta">
                <span>{t('Enter Council')}</span>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </div>
          </button>

          <button className="landing-card landing-card--advisors" onClick={() => onSelectMode('advisors')}>
            <div className="landing-card__glow" />
            <div className="landing-card__content">
              <div className="landing-card__icon landing-card__icon--advisors">
                <AdvisorsIcon />
              </div>
              <div className="landing-card__body">
                <div className="landing-card__label">{t('LLM Advisors')}</div>
                <h2 className="landing-card__title">{t('Persona-Driven Debate')}</h2>
                <p className="landing-card__desc">
                  {t('Named advisor personas argue through choices where the right answer depends on priorities, risks, and tradeoffs.')}
                </p>
                <ul className="landing-card__features">
                  <li>{t('Best for strategy, ethics, risk, prioritization')}</li>
                  <li>{t('Use when reasonable advisors may disagree')}</li>
                  <li>{t('Consensus verdict plus next steps')}</li>
                </ul>
              </div>
              <div className="landing-card__cta">
                <span>{t('Start Advisory Session')}</span>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}

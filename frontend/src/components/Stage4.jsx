import { useState } from 'react';
import Skeleton from './common/Skeleton';
import { getModelVisuals, getShortModelName } from '../utils/modelHelpers';
import ThinkBlockRenderer from './ThinkBlockRenderer';
import StageTimer from './StageTimer';
import { copyToClipboard } from '../utils/clipboard';
import { useI18n } from '../i18n';
import './Stage4.css';

/** Highlight [REVISED: ...] and [NEW: ...] markers for visual scanning */
function highlightRevisionMarkers(text) {
    if (!text) return text;
    return text
        .replace(/\[REVISED[:\s]*/gi, '**🔶 REVISED:** *')
        .replace(/\[NEW[:\s]*/gi, '**🟢 NEW:** *')
        .replace(/(?<=\*)(\.?\])/g, '*');  // close the italic before the bracket
}

export default function Stage4({ correctedDraft, startTime, endTime }) {
    const { t } = useI18n();
    const [isCopied, setIsCopied] = useState(false);

    if (!correctedDraft) return null;

    const visuals = getModelVisuals(correctedDraft?.model);
    const shortName = getShortModelName(correctedDraft?.model);

    const handleCopy = async () => {
        const textToCopy = typeof correctedDraft?.response === 'string'
            ? correctedDraft.response
            : String(correctedDraft?.response || '');
        if (!textToCopy) return;
        const copied = await copyToClipboard(textToCopy);
        if (copied) {
            setIsCopied(true);
            setTimeout(() => setIsCopied(false), 2000);
        }
    };

    return (
        <div className="stage-container stage-4">
            <div className="stage-header">
                <div className="stage-title">
                    <span className="stage-icon">📝</span>
                    {t('Stage 4: Corrected Draft')}
                </div>
                <StageTimer startTime={startTime} endTime={endTime} label="Duration" />
            </div>
            <p className="stage-4-description">
                {t('The chairman has rewritten the original document incorporating all corrections, fixing flawed claims, and applying recommendations from the deliberation. Changes are marked with')}
                {' '}<strong>[REVISED]</strong> {t('or')} <strong>[NEW]</strong>.
            </p>
            <div className="corrected-draft-response">
                <div className="corrected-draft-header">
                    <div className="corrected-draft-identity">
                        <span className="corrected-draft-avatar" style={{ backgroundColor: visuals.color }}>
                            {visuals.icon}
                        </span>
                        <div className="corrected-draft-info">
                            <span className="corrected-draft-role">
                                <span>📝</span> {t('Corrected Draft')}
                            </span>
                            <span className="corrected-draft-model">{shortName}</span>
                            <span className="corrected-draft-provider-badge">{visuals.name}</span>
                        </div>
                    </div>
                    <button
                        className={`copy-button ${isCopied ? 'copied' : ''}`}
                        onClick={handleCopy}
                        title={t('Copy corrected draft to clipboard')}
                    >
                        {isCopied ? (
                            <><span className="icon">✓</span><span className="label">{t('Copied')}</span></>
                        ) : (
                            <><span className="icon">📋</span><span className="label">{t('Copy')}</span></>
                        )}
                    </button>
                </div>
                <div className="corrected-draft-text markdown-content">
                    <ThinkBlockRenderer
                        content={highlightRevisionMarkers(
                            typeof correctedDraft?.response === 'string'
                                ? correctedDraft.response
                                : String(correctedDraft?.response || t('No corrected draft generated.'))
                        )}
                    />
                </div>
            </div>
        </div>
    );
}

export function Stage4Skeleton() {
    const { t } = useI18n();
    return (
        <div className="stage-container stage-4 skeleton-mode">
            <div className="stage-header">
                <div className="stage-title">
                    <span className="stage-icon">📝</span>
                    {t('Stage 4: Corrected Draft')}
                </div>
                <div className="stage-timer-skeleton"><Skeleton variant="text" width="60px" /></div>
            </div>
            <div className="stage-4-description">
                <Skeleton variant="text" width="80%" />
            </div>
            <div className="corrected-draft-response">
                <div className="corrected-draft-header">
                    <div className="corrected-draft-identity">
                        <Skeleton variant="avatar" />
                        <div style={{ gap: '4px', display: 'flex', flexDirection: 'column' }}>
                            <Skeleton variant="text" width="140px" height="1.2em" />
                            <Skeleton variant="text" width="100px" height="0.8em" />
                        </div>
                    </div>
                </div>
                <div className="corrected-draft-text" style={{ marginTop: '16px' }}>
                    <Skeleton variant="text" width="100%" />
                    <Skeleton variant="text" width="95%" />
                    <Skeleton variant="text" width="90%" />
                    <Skeleton variant="text" width="97%" />
                    <br />
                    <Skeleton variant="text" width="100%" />
                    <Skeleton variant="text" width="88%" />
                </div>
            </div>
        </div>
    );
}

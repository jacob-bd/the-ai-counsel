import { useState } from 'react';
import Skeleton from './common/Skeleton';
import { getModelVisuals, getShortModelName } from '../utils/modelHelpers';
import ThinkBlockRenderer from './ThinkBlockRenderer';
import StageTimer from './StageTimer';
import ModelVisualIcon from './ModelVisualIcon';
import { copyToClipboard } from '../utils/clipboard';
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
                    Stage 4: Corrected Draft
                </div>
                <StageTimer startTime={startTime} endTime={endTime} label="Duration" />
            </div>
            <p className="stage-4-description">
                The chairman has rewritten the original document incorporating all corrections,
                fixing flawed claims, and applying recommendations from the deliberation while fully
                preserving the original structure and content.
            </p>
            {correctedDraft?.error && (
                <div className="stage-4-validation-error">
                    <strong>⚠️ Preservation Validation Failed</strong>
                    <p>{correctedDraft.error_message || "The draft failed structural or length validation. Showing the fallback draft below."}</p>
                </div>
            )}
            <div className="corrected-draft-response">
                <div className="corrected-draft-header">
                    <div className="corrected-draft-identity">
                        <span className="corrected-draft-avatar" style={{ backgroundColor: visuals.color }}>
                            <ModelVisualIcon visuals={visuals} scale={0.72} />
                        </span>
                        <div className="corrected-draft-info">
                            <span className="corrected-draft-role">
                                <span>📝</span> Corrected Draft
                            </span>
                            <span className="corrected-draft-model">{shortName}</span>
                            <span className="corrected-draft-provider-badge">{visuals.name}</span>
                        </div>
                    </div>
                    <button
                        className={`copy-button ${isCopied ? 'copied' : ''}`}
                        onClick={handleCopy}
                        title="Copy corrected draft to clipboard"
                    >
                        {isCopied ? (
                            <><span className="icon">✓</span><span className="label">Copied</span></>
                        ) : (
                            <><span className="icon">📋</span><span className="label">Copy</span></>
                        )}
                    </button>
                </div>
                <div className="corrected-draft-text markdown-content">
                    <ThinkBlockRenderer
                        content={highlightRevisionMarkers(
                            typeof correctedDraft?.response === 'string'
                                ? correctedDraft.response
                                : String(correctedDraft?.response || 'No corrected draft generated.')
                        )}
                    />
                </div>
            </div>
        </div>
    );
}

export function Stage4Skeleton() {
    return (
        <div className="stage-container stage-4 skeleton-mode">
            <div className="stage-header">
                <div className="stage-title">
                    <span className="stage-icon">📝</span>
                    Stage 4: Corrected Draft
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

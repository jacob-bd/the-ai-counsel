import { useState } from 'react';
import Skeleton from './common/Skeleton';
import { getModelVisuals, getShortModelName } from '../utils/modelHelpers';
import ThinkBlockRenderer from './ThinkBlockRenderer';
import StageTimer from './StageTimer';
import ModelVisualIcon from './ModelVisualIcon';
import { copyToClipboard } from '../utils/clipboard';
import './Stage3.css';

function deAnonymizeText(text, labelToModel) {
    if (!labelToModel) return text;

    let result = text;
    // Replace each "Response X" with the actual model name
    Object.entries(labelToModel).forEach(([label, model]) => {
        const modelShortName = getShortModelName(model);
        result = result.replace(new RegExp(label, 'g'), `**${modelShortName}**`);
    });
    return result;
}

export default function Stage3({ finalResponse, labelToModel, startTime, endTime }) {
    const [isCopied, setIsCopied] = useState(false);

    if (!finalResponse) {
        return null;
    }

    const visuals = getModelVisuals(finalResponse?.model);
    const shortName = getShortModelName(finalResponse?.model);

    const handleCopy = async () => {
        const textToCopy = typeof finalResponse?.response === 'string'
            ? finalResponse.response
            : String(finalResponse?.response || '');

        if (!textToCopy) return;

        const copied = await copyToClipboard(textToCopy);
        if (copied) {
            setIsCopied(true);
            setTimeout(() => setIsCopied(false), 2000);
        }
    };

    const displayContent = typeof finalResponse?.response === 'string'
        ? finalResponse.response
        : String(finalResponse?.response || 'No response');

    // De-anonymize names for user viewing
    const deAnonymizedContent = labelToModel
        ? deAnonymizeText(displayContent, labelToModel)
        : displayContent;

    return (
        <div className="stage-container stage-3">
            <div className="stage-header">
                <div className="stage-title">
                    <span className="stage-icon">⚖️</span>
                    Stage 3: Final Council Answer
                </div>
                <StageTimer startTime={startTime} endTime={endTime} label="Duration" />
            </div>
            <div className="final-response">
                <div className="chairman-header">
                    <div className="chairman-identity">
                        <span className="chairman-avatar" style={{ backgroundColor: visuals.color }}>
                            <ModelVisualIcon visuals={visuals} scale={0.72} />
                        </span>
                        <div className="chairman-info">
                            <span className="chairman-role">
                                <span>👨‍⚖️</span> Chairman's Verdict
                            </span>
                            <span className="chairman-model">{shortName}</span>
                            <span className="chairman-provider-badge">{visuals.name}</span>
                        </div>
                    </div>

                    <button
                        className={`copy-button ${isCopied ? 'copied' : ''}`}
                        onClick={handleCopy}
                        title="Copy to clipboard"
                    >
                        {isCopied ? (
                            <>
                                <span className="icon">✓</span>
                                <span className="label">Copied</span>
                            </>
                        ) : (
                            <>
                                <span className="icon">📋</span>
                                <span className="label">Copy</span>
                            </>
                        )}
                    </button>
                </div>
                <div className="final-text markdown-content">
                    <ThinkBlockRenderer
                        content={deAnonymizedContent}
                    />
                </div>
            </div>
        </div>
    );
}

export function Stage3Skeleton() {
    return (
        <div className="stage-container stage-3 skeleton-mode">
            <div className="stage-header">
                <div className="stage-title">
                    <span className="stage-icon">⚖️</span>
                    Stage 3: Final Council Answer
                </div>
                <div className="stage-timer-skeleton">
                    <Skeleton variant="text" width="60px" />
                </div>
            </div>
            <div className="final-response">
                <div className="chairman-header">
                    <div className="chairman-identity">
                        <Skeleton variant="avatar" />
                        <div className="chairman-info" style={{ gap: '4px', display: 'flex', flexDirection: 'column' }}>
                            <Skeleton variant="text" width="140px" height="1.2em" />
                            <Skeleton variant="text" width="100px" height="0.8em" />
                            <Skeleton variant="text" width="80px" height="0.8em" />
                        </div>
                    </div>
                    <Skeleton variant="rect" width="60px" height="32px" style={{ borderRadius: '16px' }} />
                </div>
                <div className="final-text markdown-content">
                    <Skeleton variant="text" width="100%" />
                    <Skeleton variant="text" width="95%" />
                    <Skeleton variant="text" width="92%" />
                    <Skeleton variant="text" width="98%" />
                    <br />
                    <Skeleton variant="text" width="100%" />
                    <Skeleton variant="text" width="85%" />
                    <Skeleton variant="text" width="90%" />
                </div>
            </div>
        </div>
    );
}

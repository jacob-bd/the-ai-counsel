import React from 'react';
import { createPortal } from 'react-dom';
import {
    getProviderInfo,
    getModelBrandInfo,
    getModelDisplayName,
    getCouncilLayoutClass,
    PROVIDER_CONFIG,
} from '../utils/councilGridUtils';
import './CouncilGrid.css';

export default function CouncilGrid({
    models = [],
    chairman = null,
    status = 'idle', // 'idle', 'thinking', 'complete'
    progress = {},    // { currentModel: 'id', completed: ['id1', 'id2'] }
    showChairman = true,
    chairmanDisabled = false,
    usePlaceholders = true,
}) {
    // Filter out empty/null model IDs; optional decorative placeholders when empty
    const validModels = models.filter(m => m && m.trim() !== '');
    const displayModels = validModels.length > 0
        ? validModels
        : (usePlaceholders ? ['placeholder-1', 'placeholder-2', 'placeholder-3'] : []);

    const [tooltip, setTooltip] = React.useState({ visible: false, x: 0, y: 0, content: '' });

    const handleMouseEnter = (e, modelId) => {
        const content = getModelDisplayName(modelId);
        setTooltip({
            visible: true,
            x: e.clientX,
            y: e.clientY,
            content
        });
    };

    const handleMouseMove = (e) => {
        setTooltip(prev => ({
            ...prev,
            x: e.clientX,
            y: e.clientY
        }));
    };

    const handleMouseLeave = () => {
        setTooltip(prev => ({ ...prev, visible: false }));
    };

    const chairmanInfo = chairman ? getModelBrandInfo(chairman) : null;
    const layoutClass = getCouncilLayoutClass(displayModels.length, showChairman);
    const gridClass = layoutClass ? `council-grid ${layoutClass}` : 'council-grid';

    return (
        <div className={gridClass}>
            {/* Tooltip Portal */}
            {tooltip.visible && createPortal(
                <div
                    className="custom-tooltip"
                    style={{ left: tooltip.x, top: tooltip.y }}
                >
                    {tooltip.content}
                </div>,
                document.body
            )}

            {/* Regular Council Members */}
            {displayModels.map((modelId, index) => {
                const isPlaceholder = modelId.startsWith('placeholder');
                const providerInfo = isPlaceholder ? PROVIDER_CONFIG.default : getProviderInfo(modelId);
                const brandInfo = isPlaceholder ? PROVIDER_CONFIG.default : getModelBrandInfo(modelId);
                const displayName = getModelDisplayName(modelId);

                // Determine state
                let cardState = 'idle';
                if (status === 'thinking') {
                    if (progress.completed?.includes(modelId)) {
                        cardState = 'done';
                    } else if (progress.currentModel === modelId) {
                        cardState = 'active';
                    } else {
                        cardState = 'waiting';
                    }
                } else if (status === 'complete') {
                    cardState = 'done';
                } else if (status === 'idle') {
                    cardState = 'ready';
                }

                return (
                    <div
                        key={index}
                        className={`council-card ${cardState}`}
                        style={{ '--provider-color': brandInfo.color }}
                        onMouseEnter={(e) => handleMouseEnter(e, modelId)}
                        onMouseMove={handleMouseMove}
                        onMouseLeave={handleMouseLeave}
                    >
                        <div className="role-badge member">Member #{index + 1}</div>
                        <div className="council-avatar">
                            {brandInfo.logo ? (
                                <img src={brandInfo.logo} alt={brandInfo.label} className="provider-logo" />
                            ) : (
                                <span className="avatar-icon">{brandInfo.icon}</span>
                            )}
                            {cardState === 'active' && <div className="thinking-ring"></div>}
                            {cardState === 'done' ? (
                                <div className="done-badge">✓</div>
                            ) : (
                                status === 'thinking' && !isPlaceholder && cardState !== 'active' && (
                                    <div className="working-badge" title="Still working...">⏳</div>
                                )
                            )}
                        </div>
                        <div className="council-info">
                            <span className="model-name">
                                {displayName}
                            </span>
                            <span className="provider-label">{providerInfo.label}</span>
                        </div>
                    </div>
                );
            })}

            {/* Chairman Card */}
            {showChairman && (
                <div
                    className={`council-card chairman ${status === 'thinking' ? 'waiting' : 'ready'} ${chairmanDisabled ? 'chairman-disabled' : ''}`}
                    style={{ '--provider-color': (chairman && !chairmanDisabled) ? getModelBrandInfo(chairman).color : '#94a3b8' }}
                    onMouseEnter={(e) => status !== 'thinking' && !chairmanDisabled && handleMouseEnter(e, chairman || 'Chairman')}
                    onMouseMove={handleMouseMove}
                    onMouseLeave={handleMouseLeave}
                >
                    <div className="role-badge chairman">Chairman</div>
                    <div className="council-avatar">
                        {chairmanInfo && chairmanInfo.logo && !chairmanDisabled ? (
                            <img
                                src={chairmanInfo.logo}
                                alt={chairmanInfo.label}
                                className="provider-logo"
                            />
                        ) : (
                            <span className="avatar-icon">{chairmanDisabled ? '⚖️' : (chairmanInfo ? chairmanInfo.icon : '⚖️')}</span>
                        )}
                        {status === 'thinking' && <div className="thinking-ring"></div>}
                        {status === 'thinking' && (
                            <div className="working-badge" title="Verdict pending...">⏳</div>
                        )}
                    </div>
                    <div className="council-info">
                        <span className="model-name">
                            {chairmanDisabled ? 'Not Active' : (chairman ? getModelDisplayName(chairman) : 'Model')}
                        </span>
                        <span className="provider-label">
                            {status === 'thinking' ? 'Verdict Pending...' : chairmanDisabled ? 'Full Deliberation only' : 'Final Verdict'}
                        </span>
                    </div>
                </div>
            )}
        </div>
    );
}

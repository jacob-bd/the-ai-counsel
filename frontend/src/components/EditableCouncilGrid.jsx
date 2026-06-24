import React, { useEffect, useMemo, useRef } from 'react';
import SearchableModelSelect from './SearchableModelSelect';
import {
  getProviderInfo,
  getModelBrandInfo,
  getModelDisplayName,
  getAddSlot,
  getDraftSlot,
  getMemberSlot,
  getMemberDisplayNumber,
  getLineupGridMetrics,
  slotToGridStyle,
  PROVIDER_CONFIG,
} from '../utils/councilGridUtils';
import './CouncilGrid.css';
import './EditableCouncilGrid.css';

export const NEW_MEMBER_INDEX = 'new';

function isReactSelectTarget(target) {
  if (!target?.closest) return false;
  return Boolean(
    target.closest('[class*="model-select"]')
    || target.closest('[id*="react-select"]')
  );
}

function ModelPicker({ modelId, models, modelsLoading, onSelect, onCloseEditor }) {
  return (
    <div className="council-card__picker" onClick={(e) => e.stopPropagation()}>
      <SearchableModelSelect
        models={models}
        value={modelId || ''}
        onChange={(id) => {
          if (id) onSelect(id);
        }}
        placeholder={modelsLoading ? 'Loading models…' : 'Search models…'}
        isLoading={modelsLoading}
        isDisabled={modelsLoading || models.length === 0}
        autoOpen
      />
      <button type="button" className="council-card__picker-close" onClick={onCloseEditor}>
        Cancel
      </button>
    </div>
  );
}

function EditableCouncilCard({
  role,
  modelId,
  displayNumber,
  memberIndex,
  gridSlot,
  gridMinCol = 0,
  isEditing,
  models,
  modelsLoading,
  onEdit,
  onRemove,
  onSelectModel,
  onCloseEditor,
}) {
  const isChairman = role === 'chairman';
  const hasModel = Boolean(modelId);
  const providerInfo = hasModel ? getProviderInfo(modelId) : PROVIDER_CONFIG.default;
  const brandInfo = hasModel ? getModelBrandInfo(modelId) : PROVIDER_CONFIG.default;
  const memberLabel = displayNumber ?? (typeof memberIndex === 'number' ? memberIndex + 1 : 1);
  const emptyColor = isChairman ? '#94a3b8' : '#64748b';

  const cardClass = [
    'council-card',
    'ready',
    'council-card--editable',
    isChairman && 'chairman',
    isEditing && 'council-card--editing',
    !hasModel && 'council-card--empty',
  ].filter(Boolean).join(' ');

  const handleEdit = (e) => {
    e.stopPropagation();
    onEdit(isChairman ? { type: 'chairman' } : { type: 'member', index: memberIndex });
  };

  return (
    <div
      className={cardClass}
      style={{
        '--provider-color': hasModel ? brandInfo.color : emptyColor,
        ...(gridSlot != null ? slotToGridStyle(gridSlot, gridMinCol) : {}),
      }}
    >
      <div className={`role-badge ${isChairman ? 'chairman' : 'member'}`}>
        {isChairman ? 'Chairman' : `Member #${memberLabel}`}
      </div>

      {!isChairman && onRemove && (
        <button
          type="button"
          className="council-card__remove"
          onClick={(e) => {
            e.stopPropagation();
            onRemove(memberIndex);
          }}
          aria-label={`Remove member ${memberLabel}`}
        >
          ✕
        </button>
      )}

      <div className="council-avatar">
        {hasModel && brandInfo.logo ? (
          <img src={brandInfo.logo} alt={brandInfo.label} className="provider-logo" />
        ) : (
          <span className="avatar-icon">{isChairman ? '⚖️' : brandInfo.icon}</span>
        )}
      </div>

      <div className="council-info">
        <span className={`model-name ${!hasModel ? 'model-name--placeholder' : ''}`}>
          {hasModel ? getModelDisplayName(modelId) : 'Choose model'}
        </span>
        <span className="provider-label">
          {isChairman ? 'Final Verdict' : (hasModel ? providerInfo.label : 'Pick a model')}
        </span>
      </div>

      {!isEditing && (
        <button
          type="button"
          className={`council-card__edit${isChairman ? ' council-card__edit--chairman' : ''}`}
          onClick={handleEdit}
        >
          Edit
        </button>
      )}

      {isEditing && (
        <ModelPicker
          modelId={modelId}
          models={models}
          modelsLoading={modelsLoading}
          onSelect={onSelectModel}
          onCloseEditor={onCloseEditor}
        />
      )}
    </div>
  );
}

export default function EditableCouncilGrid({
  members = [],
  chairman = '',
  showChairman = true,
  maxMembers = 8,
  models = [],
  modelsLoading = false,
  activeEditor = null,
  addingMember = false,
  onActiveEditorChange,
  onMemberSelect,
  onMemberRemove,
  onChairmanSelect,
  onAddMemberClick,
  onCloseEditor,
}) {
  const gridRef = useRef(null);

  useEffect(() => {
    if (!activeEditor) return undefined;

    const handleClickOutside = (e) => {
      if (isReactSelectTarget(e.target)) return;
      if (gridRef.current?.contains(e.target)) return;
      onCloseEditor?.();
    };

    // Defer so the same click that opened the editor does not close it immediately.
    const timer = window.setTimeout(() => {
      document.addEventListener('click', handleClickOutside);
    }, 0);

    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('click', handleClickOutside);
    };
  }, [activeEditor, onCloseEditor]);

  useEffect(() => {
    if (!addingMember) return;
    const draftCard = gridRef.current?.querySelector('.council-card--empty');
    draftCard?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [addingMember]);

  const canAddMember = members.length < maxMembers && !addingMember;
  const addSlot = getAddSlot(members.length);
  const draftSlot = getDraftSlot(members.length);

  const occupiedSlots = useMemo(() => {
    const slots = [];
    if (canAddMember && addSlot != null) slots.push(addSlot);
    if (addingMember && draftSlot != null) slots.push(draftSlot);
    members.forEach((_, index) => {
      slots.push(getMemberSlot(index, members.length));
    });
    return slots;
  }, [canAddMember, addSlot, addingMember, draftSlot, members]);

  const lineupGrid = useMemo(
    () => getLineupGridMetrics(occupiedSlots),
    [occupiedSlots]
  );

  const gridSlotStyle = (slot) => slotToGridStyle(slot, lineupGrid.minCol);

  const isEditingMember = (index) =>
    activeEditor?.type === 'member' && activeEditor.index === index;

  const gridClassName = [
    'council-grid',
    'council-grid--editable',
    showChairman && 'council-grid--with-chairman',
  ].filter(Boolean).join(' ');

  return (
    <div ref={gridRef} className={gridClassName}>
      <div
        className="council-grid__lineup"
        style={{
          gridTemplateColumns: `repeat(${lineupGrid.colCount}, 148px)`,
          gridTemplateRows: `repeat(${lineupGrid.rowCount}, auto)`,
          width: lineupGrid.width,
        }}
      >
        {canAddMember && addSlot != null && (
          <button
            type="button"
            className="council-card council-card--add"
            style={gridSlotStyle(addSlot)}
            onClick={(e) => {
              e.stopPropagation();
              onAddMemberClick();
            }}
            disabled={modelsLoading || models.length === 0}
            aria-label="Add council member"
          >
            <span className="council-card-add-icon" aria-hidden="true">+</span>
            <span className="council-card-add-label">Add member</span>
          </button>
        )}

        {addingMember && (
          <EditableCouncilCard
            role="member"
            memberIndex={NEW_MEMBER_INDEX}
            displayNumber={members.length + 1}
            gridSlot={draftSlot}
            gridMinCol={lineupGrid.minCol}
            modelId=""
            isEditing
            models={models}
            modelsLoading={modelsLoading}
            onEdit={onActiveEditorChange}
            onSelectModel={(id) => onMemberSelect(NEW_MEMBER_INDEX, id)}
            onCloseEditor={onCloseEditor}
          />
        )}

        {members.map((modelId, index) => (
          <EditableCouncilCard
            key={`member-${index}-${modelId}`}
            role="member"
            memberIndex={index}
            displayNumber={getMemberDisplayNumber(index, members.length)}
            gridSlot={getMemberSlot(index, members.length)}
            gridMinCol={lineupGrid.minCol}
            modelId={modelId}
            isEditing={isEditingMember(index)}
            models={models}
            modelsLoading={modelsLoading}
            onEdit={onActiveEditorChange}
            onRemove={onMemberRemove}
            onSelectModel={(id) => onMemberSelect(index, id)}
            onCloseEditor={onCloseEditor}
          />
        ))}
      </div>

      {showChairman && (
        <EditableCouncilCard
          role="chairman"
          modelId={chairman}
          isEditing={activeEditor?.type === 'chairman'}
          models={models}
          modelsLoading={modelsLoading}
          onEdit={onActiveEditorChange}
          onSelectModel={onChairmanSelect}
          onCloseEditor={onCloseEditor}
        />
      )}
    </div>
  );
}

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { api } from '../api';
import CouncilGrid from './CouncilGrid';
import EditableCouncilGrid, { NEW_MEMBER_INDEX } from './EditableCouncilGrid';
import { deduplicateModels } from '../utils/modelHelpers';
import { shouldLoadCustomEndpointModels } from '../utils/providerSources';
import './CouncilSetup.css';

const MAX_MEMBERS = 8;
const MAX_PRESETS = 20;

const DIRECT_PROVIDER_KEY_FLAGS = {
  openai: 'openai_api_key_set',
  anthropic: 'anthropic_api_key_set',
  google: 'google_api_key_set',
  mistral: 'mistral_api_key_set',
  deepseek: 'deepseek_api_key_set',
  groq: 'groq_api_key_set',
  nvidia: 'nvidia_api_key_set',
  'opencode-zen': 'opencode_api_key_set',
  'opencode-go': 'opencode_api_key_set',
  notion2api: 'notion2api_api_key_set',
  // Backend returns capitalized labels with a space; allow both forms.
  'opencode zen': 'opencode_api_key_set',
  'opencode go': 'opencode_api_key_set',
};

function filterDirectModels(directModels, settings) {
  const ep = settings.enabled_providers || {};
  const dt = settings.direct_provider_toggles || {};
  return directModels.filter((model) => {
    if (model.provider === 'Groq') {
      return settings.groq_api_key_set && (ep.groq !== false);
    }
    if (model.provider?.toLowerCase() === 'notion2api' || model.source === 'notion2api' || String(model.id || '').startsWith('notion2api:')) {
      return settings.notion2api_api_key_set && (ep.notion2api !== false);
    }
    if (!ep.direct) return false;
    const providerKey = (model.provider || '').toLowerCase().replace(/\s+/g, '-');
    if (dt[providerKey] === false) return false;
    const flag = DIRECT_PROVIDER_KEY_FLAGS[providerKey];
    return flag ? settings[flag] : false;
  });
}

function getConfiguredModelSources(settings) {
  const ep = settings.enabled_providers || {};
  const hasDirect = !!(
    settings.openai_api_key_set
    || settings.anthropic_api_key_set
    || settings.google_api_key_set
    || settings.mistral_api_key_set
    || settings.deepseek_api_key_set
    || settings.groq_api_key_set
    || settings.nvidia_api_key_set
    || settings.opencode_api_key_set
    || settings.notion2api_api_key_set
  );
  return {
    openrouter: !!settings.openrouter_api_key_set && (ep.openrouter !== false),
    ollama: !!settings.ollama_base_url && (ep.ollama !== false),
    direct: hasDirect && ((ep.direct !== false) || (settings.notion2api_api_key_set && ep.notion2api !== false)),
    custom: shouldLoadCustomEndpointModels(settings),
  };
}

function filterMembers(models) {
  return (models || []).filter((m) => m && m.trim());
}

function buildSnapshot(members, chairman) {
  return {
    council_models: [...members],
    chairman_model: chairman || '',
  };
}

function snapshotsEqual(a, b) {
  if (!a || !b) return false;
  return JSON.stringify(a) === JSON.stringify(b);
}

function newPresetId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `preset-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export default function CouncilSetup({
  councilModels = [],
  chairmanModel = '',
  executionMode = 'full',
  editable = true,
  onCouncilChange,
  onOpenSettings,
}) {
  const [models, setModels] = useState([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [presets, setPresets] = useState([]);
  const [activePresetId, setActivePresetId] = useState(null);
  const [presetPopoverOpen, setPresetPopoverOpen] = useState(false);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveForm, setSaveForm] = useState({
    name: '',
    isDefault: false,
    updateExisting: false,
  });
  const [presetSaving, setPresetSaving] = useState(false);
  const [activeEditor, setActiveEditor] = useState(null);
  const [addingMember, setAddingMember] = useState(false);
  const presetPopoverRef = useRef(null);
  const loadedSnapshotRef = useRef(null);
  const initialLoadDone = useRef(false);
  const onCouncilChangeRef = useRef(onCouncilChange);
  onCouncilChangeRef.current = onCouncilChange;

  const members = useMemo(() => filterMembers(councilModels), [councilModels]);
  const showChairman = editable || executionMode === 'full';

  const currentSnapshot = useMemo(
    () => buildSnapshot(members, chairmanModel),
    [members, chairmanModel]
  );

  const isPresetDirty = activePresetId != null
    && !snapshotsEqual(currentSnapshot, loadedSnapshotRef.current);

  const activePreset = useMemo(
    () => presets.find((p) => p.id === activePresetId) || null,
    [presets, activePresetId]
  );

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (presetPopoverRef.current && !presetPopoverRef.current.contains(e.target)) {
        setPresetPopoverOpen(false);
      }
    };
    if (presetPopoverOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [presetPopoverOpen]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const settings = await api.getSettings();
        const loadSources = getConfiguredModelSources(settings);
        const ollamaUrl = settings.ollama_base_url || 'http://localhost:11434';

        const [orModels, ollamaModels, directModels, customModels] = await Promise.all([
          loadSources.openrouter
            ? api.getModels().then((d) => d.models || []).catch(() => [])
            : [],
          loadSources.ollama
            ? api.getOllamaModels(ollamaUrl).then((d) => (d.models || []).map((m) => ({
              ...m,
              id: m.id.startsWith('ollama:') ? m.id : `ollama:${m.id}`,
              name: `${m.name || m.id} (Local)`,
              provider: 'Ollama',
            }))).catch(() => [])
            : [],
          loadSources.direct
            ? api.getDirectModels()
              .then((d) => filterDirectModels(Array.isArray(d) ? d : (d.models || []), settings))
              .catch(() => [])
            : [],
          loadSources.custom
            ? api.getCustomEndpointModels().then((d) => d.models || []).catch(() => [])
            : [],
        ]);

        if (cancelled) return;

        const combined = [...orModels, ...ollamaModels, ...directModels, ...customModels];
        const deduplicated = deduplicateModels(combined);
        setModels(deduplicated.sort((a, b) => (a.name || '').localeCompare(b.name || '')));

        const loadedPresets = Array.isArray(settings.council_presets) ? settings.council_presets : [];
        setPresets(loadedPresets);

        if (!initialLoadDone.current && editable) {
          initialLoadDone.current = true;
          const currentMembers = filterMembers(councilModels);
          if (currentMembers.length === 0) {
            const defaultPreset = loadedPresets.find((p) => p.is_default) || null;
            if (defaultPreset) {
              const presetMembers = filterMembers(defaultPreset.council_models);
              const presetChairman = defaultPreset.chairman_model || '';
              await onCouncilChangeRef.current?.({
                councilModels: presetMembers,
                chairmanModel: presetChairman,
              });
              setActivePresetId(defaultPreset.id);
              loadedSnapshotRef.current = buildSnapshot(presetMembers, presetChairman);
            }
          }
        }
      } catch (err) {
        console.error('Failed to load council models:', err);
      } finally {
        if (!cancelled) setModelsLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, [editable]);

  const persistCouncil = useCallback(async (nextMembers, nextChairman) => {
    const cappedMembers = nextMembers.slice(0, MAX_MEMBERS);
    await onCouncilChange?.({
      councilModels: cappedMembers,
      chairmanModel: nextChairman,
    });
  }, [onCouncilChange]);

  const markPresetDirty = () => {
    if (activePresetId) loadedSnapshotRef.current = null;
  };

  const persistPresets = async (nextPresets) => {
    await api.updateSettings({ council_presets: nextPresets });
    setPresets(nextPresets);
  };

  const applyPreset = useCallback(async (preset, { markClean = true, touchLastUsed = true } = {}) => {
    const presetMembers = filterMembers(preset.council_models);
    const presetChairman = preset.chairman_model || '';
    await persistCouncil(presetMembers, presetChairman);
    setActivePresetId(preset.id);
    setPresetPopoverOpen(false);

    if (markClean) {
      loadedSnapshotRef.current = buildSnapshot(presetMembers, presetChairman);
    }

    if (touchLastUsed) {
      const now = new Date().toISOString();
      const nextPresets = presets.map((p) => (
        p.id === preset.id ? { ...p, last_used_at: now } : p
      ));
      persistPresets(nextPresets).catch((err) => {
        console.error('Failed to update council preset last used:', err);
      });
    }
  }, [persistCouncil, presets]);

  const handleSelectCustomSetup = () => {
    setActivePresetId(null);
    loadedSnapshotRef.current = null;
    setPresetPopoverOpen(false);
  };

  const handleMemberChange = async (index, modelId) => {
    const next = [...members];
    next[index] = modelId;
    await persistCouncil(next, chairmanModel);
    markPresetDirty();
  };

  const handleRemoveMember = async (index) => {
    const next = members.filter((_, i) => i !== index);
    handleCloseEditor();
    markPresetDirty();
    await persistCouncil(next, chairmanModel);
  };

  const handleAddMember = () => {
    if (members.length >= MAX_MEMBERS) return;
    setAddingMember(true);
    setActiveEditor({ type: 'member', index: NEW_MEMBER_INDEX });
  };

  const handleCloseEditor = () => {
    setActiveEditor(null);
    setAddingMember(false);
  };

  const handleMemberSelect = async (index, modelId) => {
    if (!modelId) return;

    try {
      if (index === NEW_MEMBER_INDEX) {
        if (members.length >= MAX_MEMBERS) return;
        await persistCouncil([modelId, ...members], chairmanModel);
        markPresetDirty();
      } else {
        await handleMemberChange(index, modelId);
      }
    } finally {
      setAddingMember(false);
      setActiveEditor(null);
    }
  };

  const handleChairmanSelect = async (modelId) => {
    if (!modelId) return;
    await persistCouncil(members, modelId);
    setActiveEditor(null);
    markPresetDirty();
  };

  const openSavePresetModal = () => {
    setSaveForm({
      name: activePreset?.name || '',
      isDefault: activePreset?.is_default || presets.length === 0,
      updateExisting: false,
    });
    setSaveModalOpen(true);
    setPresetPopoverOpen(false);
  };

  const handleNewCouncil = async () => {
    setActivePresetId(null);
    loadedSnapshotRef.current = null;
    setActiveEditor(null);
    setAddingMember(false);
    await persistCouncil([], '');
  };

  const closeSavePresetModal = () => {
    setSaveModalOpen(false);
    setPresetSaving(false);
  };

  const buildPresetFromForm = (id, name, { isDefault }) => ({
    id,
    name: name.trim(),
    council_models: members,
    chairman_model: chairmanModel || '',
    is_default: isDefault,
    last_used_at: new Date().toISOString(),
  });

  const handleSavePreset = async () => {
    const name = saveForm.name.trim();
    if (!name || presetSaving) return;

    setPresetSaving(true);
    try {
      let nextPresets = [...presets];
      const shouldUpdate = saveForm.updateExisting && activePresetId;

      if (shouldUpdate) {
        nextPresets = nextPresets.map((p) => {
          if (p.id === activePresetId) {
            return buildPresetFromForm(p.id, name, saveForm);
          }
          if (saveForm.isDefault) {
            return { ...p, is_default: false };
          }
          return p;
        });
      } else {
        const id = newPresetId();
        const newPreset = buildPresetFromForm(id, name, saveForm);
        nextPresets = [
          newPreset,
          ...(saveForm.isDefault ? presets.map((p) => ({ ...p, is_default: false })) : presets),
        ].slice(0, MAX_PRESETS);
        setActivePresetId(id);
      }

      await persistPresets(nextPresets);
      loadedSnapshotRef.current = currentSnapshot;
      closeSavePresetModal();
    } catch (err) {
      console.error('Failed to save council preset:', err);
      setPresetSaving(false);
    }
  };

  const handleDeletePreset = async (presetId) => {
    try {
      const nextPresets = presets.filter((p) => p.id !== presetId);
      await persistPresets(nextPresets);
      if (activePresetId === presetId) {
        setActivePresetId(null);
        loadedSnapshotRef.current = null;
      }
      setPresetPopoverOpen(false);
    } catch (err) {
      console.error('Failed to delete council preset:', err);
    }
  };

  const handleSetDefaultPreset = async (presetId) => {
    try {
      const nextPresets = presets.map((p) => ({
        ...p,
        is_default: p.id === presetId,
      }));
      await persistPresets(nextPresets);
    } catch (err) {
      console.error('Failed to set default council preset:', err);
    }
  };

  if (!editable) {
    if (members.length === 0) return null;
    return (
      <CouncilGrid
        models={members}
        chairman={chairmanModel}
        status="idle"
        showChairman={showChairman}
        chairmanDisabled={!showChairman}
        usePlaceholders={false}
      />
    );
  }

  return (
    <div className="council-setup">
      <div className="council-setup__preset-row">
        <div className="council-setup__preset-picker" ref={presetPopoverRef}>
          <button
            type="button"
            className="council-setup__preset-btn"
            onClick={() => setPresetPopoverOpen((v) => !v)}
            aria-haspopup="listbox"
            aria-expanded={presetPopoverOpen}
          >
            <span className="council-setup__preset-btn-icon" aria-hidden="true">📁</span>
            <span className="council-setup__preset-btn-label">
              {activePreset ? activePreset.name : 'Custom lineup'}
            </span>
            <span className="council-setup__preset-chevron">›</span>
          </button>
          {presetPopoverOpen && (
            <div className="council-setup__preset-popover" role="listbox">
              <button
                type="button"
                className={`council-setup__preset-option ${!activePresetId ? 'council-setup__preset-option--selected' : ''}`}
                onClick={handleSelectCustomSetup}
              >
                Custom lineup
              </button>
              {presets.length === 0 ? (
                <div className="council-setup__preset-empty">No saved presets yet</div>
              ) : (
                presets.map((preset) => (
                  <div key={preset.id} className="council-setup__preset-option-row">
                    <button
                      type="button"
                      className={`council-setup__preset-option ${activePresetId === preset.id ? 'council-setup__preset-option--selected' : ''}`}
                      onClick={() => applyPreset(preset)}
                    >
                      {preset.is_default && <span className="council-setup__preset-star" aria-hidden="true">⭐</span>}
                      <span>{preset.name}</span>
                    </button>
                    <div className="council-setup__preset-option-actions">
                      {!preset.is_default && (
                        <button
                          type="button"
                          className="council-setup__preset-action-btn"
                          title="Set as default"
                          aria-label={`Set ${preset.name} as default`}
                          onClick={() => handleSetDefaultPreset(preset.id)}
                        >
                          ☆
                        </button>
                      )}
                      <button
                        type="button"
                        className="council-setup__preset-action-btn council-setup__preset-action-btn--delete"
                        title="Delete preset"
                        aria-label={`Delete ${preset.name}`}
                        onClick={() => handleDeletePreset(preset.id)}
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))
              )}
              <div className="council-setup__preset-popover-footer">
                <button
                  type="button"
                  className="council-setup__preset-footer-btn"
                  onClick={openSavePresetModal}
                >
                  Save current as…
                </button>
              </div>
            </div>
          )}
        </div>
        <button
          type="button"
          className="council-setup__new-council-btn"
          onClick={handleNewCouncil}
          title="Clear all current members and chairman to start fresh"
        >
          + New Council · Clear Current
        </button>
        {(isPresetDirty || !activePresetId) && (
          <button
            type="button"
            className="council-setup__preset-save-link"
            onClick={openSavePresetModal}
          >
            Save preset…
          </button>
        )}
      </div>

      {!modelsLoading && models.length === 0 && (
        <p className="council-setup__model-empty">
          No models available.{' '}
          <button type="button" className="council-setup__link" onClick={() => onOpenSettings?.('llm_keys')}>
            Configure API keys
          </button>
        </p>
      )}

      <EditableCouncilGrid
        members={members}
        chairman={chairmanModel}
        showChairman={showChairman}
        maxMembers={MAX_MEMBERS}
        models={models}
        modelsLoading={modelsLoading}
        activeEditor={activeEditor}
        addingMember={addingMember}
        onActiveEditorChange={setActiveEditor}
        onMemberSelect={handleMemberSelect}
        onMemberRemove={handleRemoveMember}
        onChairmanSelect={handleChairmanSelect}
        onAddMemberClick={handleAddMember}
        onCloseEditor={handleCloseEditor}
      />

      {isPresetDirty && (
        <p className="council-setup__preset-dirty">Unsaved changes from preset</p>
      )}

      {saveModalOpen && (
        <div className="council-setup__modal-backdrop" onClick={closeSavePresetModal}>
          <div
            className="council-setup__modal"
            role="dialog"
            aria-labelledby="council-preset-save-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="council-preset-save-title">Save council preset</h3>
            <label className="council-setup__modal-label">
              Preset name
              <input
                type="text"
                value={saveForm.name}
                onChange={(e) => setSaveForm((f) => ({ ...f, name: e.target.value }))}
                maxLength={80}
                autoFocus
              />
            </label>
            <label className="council-setup__modal-check">
              <input
                type="checkbox"
                checked={saveForm.isDefault}
                onChange={(e) => setSaveForm((f) => ({ ...f, isDefault: e.target.checked }))}
              />
              Set as default lineup
            </label>
            {activePresetId && (
              <>
                <label className="council-setup__modal-check">
                  <input
                    type="checkbox"
                    checked={saveForm.updateExisting}
                    onChange={(e) => setSaveForm((f) => ({ ...f, updateExisting: e.target.checked }))}
                  />
                  Overwrite existing preset
                </label>
                {saveForm.updateExisting && (
                  <p className="council-setup__modal-warning">
                    Saving will replace &ldquo;{activePreset?.name}&rdquo; with your current lineup.
                  </p>
                )}
              </>
            )}
            <div className="council-setup__modal-actions">
              <button type="button" className="council-setup__modal-cancel" onClick={closeSavePresetModal}>
                Cancel
              </button>
              <button
                type="button"
                className="council-setup__modal-save"
                onClick={handleSavePreset}
                disabled={!saveForm.name.trim() || presetSaving}
              >
                {presetSaving ? 'Saving…' : (saveForm.updateExisting ? 'Overwrite preset' : 'Save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

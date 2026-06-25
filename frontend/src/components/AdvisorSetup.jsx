import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { api, buildAvailableSearchProviders } from '../api';
import SearchableModelSelect from './SearchableModelSelect';
import { getShortModelName, deduplicateModels } from '../utils/modelHelpers';
import { shouldLoadCustomEndpointModels } from '../utils/providerSources';
import DocumentUpload from './DocumentUpload';
import './AdvisorSetup.css';

const RECOMMENDED_PERSONA_IDS = ['skeptic', 'pragmatist', 'innovator'];
const MIN_ROUNDS = 3;
const MAX_ROUNDS = 10;
const MAX_PRESETS = 20;

function clampRounds(value, fallback = MIN_ROUNDS) {
  const rounds = typeof value === 'number' ? value : fallback;
  return Math.min(MAX_ROUNDS, Math.max(MIN_ROUNDS, rounds));
}

function normalizePresetMode(mode) {
  return mode === 'advanced' ? 'advanced' : 'simple';
}

function buildPresetSnapshot({
  selectedPersonaIds,
  modelMode,
  chosenModel,
  tiebreakerModel,
  modelAssignments,
  rounds,
  searchProvider,
}) {
  const sortedPersonaIds = [...selectedPersonaIds].sort();
  const assignments =
    modelMode === 'advanced'
      ? Object.fromEntries(
          sortedPersonaIds
            .filter((id) => modelAssignments[id])
            .sort()
            .map((id) => [id, modelAssignments[id]])
        )
      : null;

  return {
    persona_ids: sortedPersonaIds,
    mode: modelMode,
    default_model: chosenModel || '',
    tiebreaker_model: tiebreakerModel || '',
    model_assignments: assignments && Object.keys(assignments).length > 0 ? assignments : null,
    max_rounds: rounds,
    search_provider: searchProvider,
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

function hasAnyDirectProviderKey(settings) {
  return !!(
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
}

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

/** Filter direct models respecting global provider toggles. */
function filterDirectModelsForAdvisor(directModels, settings) {
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

/** Model sources respect global provider toggles. */
function getAdvisorModelSources(settings) {
  const ep = settings.enabled_providers || {};
  return {
    openrouter: !!settings.openrouter_api_key_set && (ep.openrouter !== false),
    ollama: !!settings.ollama_base_url && (ep.ollama !== false),
    direct: hasAnyDirectProviderKey(settings) && ((ep.direct !== false) || (settings.notion2api_api_key_set && ep.notion2api !== false)),
    custom: shouldLoadCustomEndpointModels(settings),
  };
}

export default function AdvisorSetup({
  onStartDebate,
  isLoading = false,
}) {
  const [personas, setPersonas] = useState([]);
  const [personasLoading, setPersonasLoading] = useState(true);
  const [models, setModels] = useState([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [selectedPersonaIds, setSelectedPersonaIds] = useState([]);
  const [modelMode, setModelMode] = useState('simple');
  const [chosenModel, setChosenModel] = useState('');
  const [tiebreakerModel, setTiebreakerModel] = useState('');
  const [modelAssignments, setModelAssignments] = useState({});
  const [rounds, setRounds] = useState(3);
  const [editingPersona, setEditingPersona] = useState(null);
  const [editForm, setEditForm] = useState({ name: '', role: '', description: '', system_prompt: '', avatar_emoji: '' });
  const [editSaving, setEditSaving] = useState(false);
  const [searchProvider, setSearchProvider] = useState(null);
  const [availableSearchProviders, setAvailableSearchProviders] = useState([{ id: 'duckduckgo', name: 'DuckDuckGo' }]);
  const [searchPopoverOpen, setSearchPopoverOpen] = useState(false);
  const searchPopoverRef = useRef(null);
  const [question, setQuestion] = useState('');
  const [documentPayload, setDocumentPayload] = useState({ documents: [], attachments: [], warnings: [] });
  const [documentsBusy, setDocumentsBusy] = useState(false);
  const [documentResetKey, setDocumentResetKey] = useState(0);
  const [personasExpanded, setPersonasExpanded] = useState(true);
  const [presets, setPresets] = useState([]);
  const [activePresetId, setActivePresetId] = useState(null);
  const [presetPopoverOpen, setPresetPopoverOpen] = useState(false);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveForm, setSaveForm] = useState({
    name: '',
    isDefault: false,
    includeConfig: true,
    updateExisting: true,
  });
  const [presetSaving, setPresetSaving] = useState(false);
  const presetPopoverRef = useRef(null);
  const loadedSnapshotRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (searchPopoverRef.current && !searchPopoverRef.current.contains(e.target)) {
        setSearchPopoverOpen(false);
      }
      if (presetPopoverRef.current && !presetPopoverRef.current.contains(e.target)) {
        setPresetPopoverOpen(false);
      }
    };
    if (searchPopoverOpen || presetPopoverOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [searchPopoverOpen, presetPopoverOpen]);

  useEffect(() => {
    const fetchModels = async () => {
      try {
        const [personasResult, settings] = await Promise.all([
          api.getPersonas().catch(() => []),
          api.getSettings(),
        ]);
        setPersonas(personasResult);

        setAvailableSearchProviders(buildAvailableSearchProviders(settings));

        const loadSources = getAdvisorModelSources(settings);
        const ollamaUrl = settings.ollama_base_url || 'http://localhost:11434';

        const [orModels, ollamaModels, directModels, customModels] = await Promise.all([
          loadSources.openrouter
            ? api.getModels().then(d => d.models || []).catch(() => [])
            : [],
          loadSources.ollama
            ? api.getOllamaModels(ollamaUrl).then(d => (d.models || []).map(m => ({
                ...m,
                id: m.id.startsWith('ollama:') ? m.id : `ollama:${m.id}`,
                name: `${m.name || m.id} (Local)`,
                provider: 'Ollama',
              }))).catch(() => [])
            : [],
          loadSources.direct
            ? api.getDirectModels()
              .then(d => filterDirectModelsForAdvisor(Array.isArray(d) ? d : (d.models || []), settings))
              .catch(() => [])
            : [],
          loadSources.custom
            ? api.getCustomEndpointModels().then(d => d.models || []).catch(() => [])
            : [],
        ]);

        const combined = [...orModels, ...ollamaModels, ...directModels, ...customModels];
        const deduplicated = deduplicateModels(combined);
        const sorted = deduplicated.sort((a, b) => (a.name || '').localeCompare(b.name || ''));

        setModels(sorted);

        const loadedPresets = Array.isArray(settings.advisor_presets) ? settings.advisor_presets : [];
        setPresets(loadedPresets);

        let initialModel = settings.advisor_default_model || (sorted.length > 0 ? sorted[0].id : '');
        let initialTiebreaker = settings.advisor_tiebreaker_model || initialModel;
        let initialRounds = clampRounds(settings.advisor_default_rounds);

        setChosenModel(initialModel);
        setTiebreakerModel(initialTiebreaker);
        setRounds(initialRounds);

        const defaultPreset = loadedPresets.find((p) => p.is_default) || null;
        if (defaultPreset) {
          const personaIds = (defaultPreset.persona_ids || []).slice(0, 4);
          const mode = normalizePresetMode(defaultPreset.mode);
          if (defaultPreset.default_model) {
            initialModel = defaultPreset.default_model;
            setChosenModel(defaultPreset.default_model);
          }
          if (defaultPreset.tiebreaker_model) {
            initialTiebreaker = defaultPreset.tiebreaker_model;
            setTiebreakerModel(defaultPreset.tiebreaker_model);
          } else if (defaultPreset.default_model) {
            initialTiebreaker = defaultPreset.default_model;
            setTiebreakerModel(defaultPreset.default_model);
          }
          const modelAssignmentsForPreset =
            mode === 'advanced' && defaultPreset.model_assignments
              ? { ...defaultPreset.model_assignments }
              : {};
          if (defaultPreset.max_rounds) {
            initialRounds = clampRounds(defaultPreset.max_rounds);
            setRounds(initialRounds);
          }

          setSelectedPersonaIds(personaIds);
          setModelMode(mode);
          setModelAssignments(modelAssignmentsForPreset);
          setSearchProvider(defaultPreset.search_provider ?? null);
          setActivePresetId(defaultPreset.id);
          loadedSnapshotRef.current = buildPresetSnapshot({
            selectedPersonaIds: personaIds,
            modelMode: mode,
            chosenModel: initialModel,
            tiebreakerModel: initialTiebreaker,
            modelAssignments: modelAssignmentsForPreset,
            rounds: initialRounds,
            searchProvider: defaultPreset.search_provider ?? null,
          });
        }
      } catch (err) {
        console.error('Failed to load advisor models:', err);
      } finally {
        setPersonasLoading(false);
        setModelsLoading(false);
      }
    };

    fetchModels();
  }, []);

  // ── Helpers ──────────────────────────────────────────────────────────────

  const togglePersona = (id) => {
    setSelectedPersonaIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((x) => x !== id);
      }
      if (prev.length >= 4) return prev; // max 4
      return [...prev, id];
    });
  };

  const handleUseRecommended = () => {
    setSelectedPersonaIds(RECOMMENDED_PERSONA_IDS);
    if (!chosenModel && models.length > 0) {
      setChosenModel(models[0].id);
    }
  };

  const persistAdvisorSetting = async (field, value, setter) => {
    setter(value);
    try {
      const currentSettings = await api.getSettings();
      await api.updateSettings({ ...currentSettings, [field]: value });
    } catch (err) {
      console.error(`Failed to auto-save ${field}:`, err);
    }
  };

  const handleSimpleModelChange = (modelId) => {
    persistAdvisorSetting('advisor_default_model', modelId, setChosenModel);
  };

  const handleModelAssignment = (personaId, modelId) => {
    setModelAssignments((prev) => ({ ...prev, [personaId]: modelId }));
  };

  const handleTiebreakerModelChange = (modelId) => {
    persistAdvisorSetting('advisor_tiebreaker_model', modelId, setTiebreakerModel);
  };

  const handleRoundsStep = (delta) => {
    setRounds((prev) => clampRounds(prev + delta));
  };

  const currentSnapshot = useMemo(
    () => buildPresetSnapshot({
      selectedPersonaIds,
      modelMode,
      chosenModel,
      tiebreakerModel,
      modelAssignments,
      rounds,
      searchProvider,
    }),
    [selectedPersonaIds, modelMode, chosenModel, tiebreakerModel, modelAssignments, rounds, searchProvider]
  );

  const isPresetDirty = activePresetId != null && !snapshotsEqual(currentSnapshot, loadedSnapshotRef.current);

  const activePreset = useMemo(
    () => presets.find((p) => p.id === activePresetId) || null,
    [presets, activePresetId]
  );

  const persistPresets = async (nextPresets) => {
    await api.updateSettings({ advisor_presets: nextPresets });
    setPresets(nextPresets);
  };

  const applyPresetToForm = useCallback((preset, { markClean = true, touchLastUsed = true } = {}) => {
    const personaIds = (preset.persona_ids || []).slice(0, 4);
    const mode = normalizePresetMode(preset.mode);
    const nextModel = preset.default_model || chosenModel;
    const nextTiebreaker = preset.tiebreaker_model || preset.default_model || tiebreakerModel;
    const nextAssignments =
      mode === 'advanced' && preset.model_assignments
        ? { ...preset.model_assignments }
        : {};
    const nextRounds = preset.max_rounds ? clampRounds(preset.max_rounds) : rounds;
    const nextSearchProvider = preset.search_provider ?? null;

    setSelectedPersonaIds(personaIds);
    setModelMode(mode);
    if (preset.default_model) setChosenModel(nextModel);
    if (preset.tiebreaker_model) setTiebreakerModel(nextTiebreaker);
    else if (preset.default_model) setTiebreakerModel(nextTiebreaker);
    setModelAssignments(nextAssignments);
    if (preset.max_rounds) setRounds(nextRounds);
    setSearchProvider(nextSearchProvider);
    setActivePresetId(preset.id);
    setPresetPopoverOpen(false);

    if (markClean) {
      loadedSnapshotRef.current = buildPresetSnapshot({
        selectedPersonaIds: personaIds,
        modelMode: mode,
        chosenModel: nextModel,
        tiebreakerModel: nextTiebreaker,
        modelAssignments: nextAssignments,
        rounds: nextRounds,
        searchProvider: nextSearchProvider,
      });
    }

    if (touchLastUsed) {
      const now = new Date().toISOString();
      const nextPresets = presets.map((p) => (
        p.id === preset.id ? { ...p, last_used_at: now } : p
      ));
      persistPresets(nextPresets).catch((err) => {
        console.error('Failed to update preset last used:', err);
      });
    }
  }, [chosenModel, tiebreakerModel, rounds, presets]);

  const handleSelectCustomSetup = () => {
    setActivePresetId(null);
    loadedSnapshotRef.current = null;
    setPresetPopoverOpen(false);
  };

  const openSavePresetModal = () => {
    setSaveForm({
      name: activePreset?.name || '',
      isDefault: activePreset?.is_default || presets.length === 0,
      includeConfig: true,
      updateExisting: Boolean(activePresetId),
    });
    setSaveModalOpen(true);
    setPresetPopoverOpen(false);
  };

  const closeSavePresetModal = () => {
    setSaveModalOpen(false);
    setPresetSaving(false);
  };

  const buildPresetFromForm = (id, name, { isDefault, includeConfig }) => ({
    id,
    name: name.trim(),
    persona_ids: selectedPersonaIds,
    mode: modelMode,
    default_model: chosenModel || '',
    tiebreaker_model: tiebreakerModel || chosenModel || '',
    model_assignments: modelMode === 'advanced' ? currentSnapshot.model_assignments : null,
    max_rounds: includeConfig ? rounds : MIN_ROUNDS,
    search_provider: includeConfig ? searchProvider : null,
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
      console.error('Failed to save advisor preset:', err);
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
      console.error('Failed to delete advisor preset:', err);
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
      console.error('Failed to set default preset:', err);
    }
  };

  const modelSummaryLine = useMemo(() => {
    if (selectedPersonaIds.length === 0) return null;
    const names = selectedPersonaIds
      .map((id) => personas.find((p) => p.id === id)?.name)
      .filter(Boolean);
    if (names.length === 0) return null;

    if (modelMode === 'simple' && chosenModel) {
      return `${names.join(' · ')} → ${getShortModelName(chosenModel)}`;
    }

    if (modelMode === 'advanced') {
      const parts = selectedPersonaIds.map((id) => {
        const persona = personas.find((p) => p.id === id);
        const model = modelAssignments[id];
        if (!persona || !model) return null;
        return `${persona.name} → ${getShortModelName(model)}`;
      }).filter(Boolean);
      if (parts.length === 0) return null;
      return parts.join(' · ');
    }

    return null;
  }, [selectedPersonaIds, personas, modelMode, chosenModel, modelAssignments]);

  const openEditModal = (e, persona) => {
    e.stopPropagation();
    setEditingPersona(persona);
    setEditForm({
      name: persona.name,
      role: persona.role,
      description: persona.description,
      system_prompt: persona.system_prompt,
      avatar_emoji: persona.avatar_emoji,
    });
  };

  const closeEditModal = () => {
    setEditingPersona(null);
    setEditSaving(false);
  };

  const runEditAction = async (apiFn, errorMsg) => {
    if (!editingPersona || editSaving) return;
    setEditSaving(true);
    try {
      const result = await apiFn(editingPersona.id);
      setPersonas((prev) => prev.map((p) => p.id === result.id ? result : p));
      closeEditModal();
    } catch (err) {
      console.error(errorMsg, err);
      setEditSaving(false);
    }
  };

  const handleEditSave = () => runEditAction(
    (id) => api.updatePersona(id, editForm),
    'Failed to save persona:'
  );

  const handleEditReset = () => runEditAction(
    api.resetPersona,
    'Failed to reset persona:'
  );

  const canStart =
    selectedPersonaIds.length >= 2 &&
    (modelMode === 'simple' ? !!chosenModel : selectedPersonaIds.every((id) => !!modelAssignments[id])) &&
    question.trim().length > 0 &&
    !documentsBusy;

  const getHint = () => {
    if (canStart) return '↵ Enter to start · Shift+Enter for new line';
    if (question.trim().length === 0) return 'Fill in the form below, then start your debate';
    if (selectedPersonaIds.length < 2) return '⚠ Select at least 2 advisors below';
    if (modelMode === 'simple' && !chosenModel) return '⚠ Choose a model below';
    return '⚠ Assign a model to each advisor';
  };

  const handleSubmit = () => {
    if (!canStart || isLoading) return;
    const payload = {
      question: question.trim(),
      personaIds: selectedPersonaIds,
      defaultModel: chosenModel,
      tiebreakerModel: modelMode === 'simple' ? chosenModel : (tiebreakerModel || null),
      modelAssignments: modelMode === 'advanced' ? modelAssignments : null,
      maxRounds: rounds,
      searchProvider,
      documents: documentPayload.documents || [],
      attachments: documentPayload.attachments || [],
    };
    onStartDebate(payload);
    setDocumentPayload({ documents: [], attachments: [], warnings: [] });
    setDocumentResetKey((key) => key + 1);
  };

  // ── Render ───────────────────────────────────────────────────────────────

  const selectedCount = selectedPersonaIds.length;

  return (
    <div className="advisor-setup">
      {/* Question Textarea + Start Debate — primary input card */}
      <div className="advisor-setup__section advisor-setup__question-card">
        <label className="advisor-setup__section-label" htmlFor="advisor-question">
          Debate Question
        </label>
        <textarea
          id="advisor-question"
          className="advisor-setup__question"
          placeholder="What should your advisors debate? (Shift+Enter for new line)"
          rows={4}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
        />
        <div className="advisor-setup__question-footer">
          <span className="advisor-setup__question-hint">
            {getHint()}
          </span>
          <button
            type="button"
            className={`advisor-setup__start-btn advisor-setup__start-btn--inline ${canStart && !isLoading ? 'advisor-setup__start-btn--ready' : ''}`}
            onClick={handleSubmit}
            disabled={!canStart || isLoading}
          >
            {isLoading ? (
              <><span className="advisor-setup__spinner" aria-hidden="true" /> Starting…</>
            ) : (
              'Start Debate ➤'
            )}
          </button>
        </div>
        <DocumentUpload
          disabled={isLoading}
          resetKey={documentResetKey}
          onChange={setDocumentPayload}
          onBusyChange={setDocumentsBusy}
        />
      </div>

      {/* Rounds + Web Search — compact config directly below question */}
      <div className="advisor-setup__section">
        <div className="advisor-setup__config-row">
          <div className="advisor-setup__rounds">
            <span className="advisor-setup__config-label">Rounds</span>
            <div className="advisor-setup__stepper">
              <button
                type="button"
                className="advisor-setup__stepper-btn"
                onClick={() => handleRoundsStep(-1)}
                disabled={rounds <= 3}
                aria-label="Decrease rounds"
              >
                −
              </button>
              <span className="advisor-setup__stepper-value">{rounds}</span>
              <button
                type="button"
                className="advisor-setup__stepper-btn"
                onClick={() => handleRoundsStep(1)}
                disabled={rounds >= 10}
                aria-label="Increase rounds"
              >
                +
              </button>
            </div>
          </div>

          <div className="advisor-setup__websearch-picker" ref={searchPopoverRef}>
            <span className="advisor-setup__config-label">Web Search</span>
            <button
              type="button"
              className={`advisor-setup__search-btn ${searchProvider ? 'advisor-setup__search-btn--active' : ''}`}
              onClick={() => setSearchPopoverOpen((v) => !v)}
              aria-haspopup="listbox"
              aria-expanded={searchPopoverOpen}
            >
              <span>🌐</span>
              <span>{searchProvider ? (availableSearchProviders.find(p => p.id === searchProvider)?.name || searchProvider) : 'Off'}</span>
              <span className="advisor-setup__search-chevron">›</span>
            </button>
            {searchPopoverOpen && (
              <div className="advisor-setup__search-popover" role="listbox">
                <button
                  type="button"
                  className={`advisor-setup__search-option ${!searchProvider ? 'advisor-setup__search-option--selected' : ''}`}
                  onClick={() => { setSearchProvider(null); setSearchPopoverOpen(false); }}
                >
                  <span>✕</span> Off
                </button>
                {availableSearchProviders.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className={`advisor-setup__search-option ${searchProvider === p.id ? 'advisor-setup__search-option--selected' : ''}`}
                    onClick={() => { setSearchProvider(p.id); setSearchPopoverOpen(false); }}
                  >
                    <span>🌐</span> {p.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Model Assignment */}
      <div className="advisor-setup__section">
        <div className="advisor-setup__section-header">
          <span className="advisor-setup__section-label">Model Assignment</span>
          <div className="advisor-setup__mode-tabs">
            <button
              type="button"
              className={`advisor-setup__mode-tab ${modelMode === 'simple' ? 'advisor-setup__mode-tab--active' : ''}`}
              onClick={() => setModelMode('simple')}
            >
              Simple
            </button>
            <button
              type="button"
              className={`advisor-setup__mode-tab ${modelMode === 'advanced' ? 'advisor-setup__mode-tab--active' : ''}`}
              onClick={() => setModelMode('advanced')}
            >
              Advanced
            </button>
          </div>
        </div>

        <div className="advisor-setup__preset-row">
          <div className="advisor-setup__preset-picker" ref={presetPopoverRef}>
            <button
              type="button"
              className="advisor-setup__preset-btn"
              onClick={() => setPresetPopoverOpen((v) => !v)}
              aria-haspopup="listbox"
              aria-expanded={presetPopoverOpen}
            >
              <span className="advisor-setup__preset-btn-icon" aria-hidden="true">📁</span>
              <span className="advisor-setup__preset-btn-label">
                {activePreset ? activePreset.name : 'Custom setup'}
              </span>
              <span className="advisor-setup__preset-chevron">›</span>
            </button>
            {presetPopoverOpen && (
              <div className="advisor-setup__preset-popover" role="listbox">
                <button
                  type="button"
                  className={`advisor-setup__preset-option ${!activePresetId ? 'advisor-setup__preset-option--selected' : ''}`}
                  onClick={handleSelectCustomSetup}
                >
                  Custom setup
                </button>
                {presets.length === 0 ? (
                  <div className="advisor-setup__preset-empty">No saved presets yet</div>
                ) : (
                  presets.map((preset) => (
                    <div key={preset.id} className="advisor-setup__preset-option-row">
                      <button
                        type="button"
                        className={`advisor-setup__preset-option ${activePresetId === preset.id ? 'advisor-setup__preset-option--selected' : ''}`}
                        onClick={() => applyPresetToForm(preset)}
                      >
                        {preset.is_default && <span className="advisor-setup__preset-star" aria-hidden="true">⭐</span>}
                        <span>{preset.name}</span>
                      </button>
                      <div className="advisor-setup__preset-option-actions">
                        {!preset.is_default && (
                          <button
                            type="button"
                            className="advisor-setup__preset-action-btn"
                            title="Set as default"
                            aria-label={`Set ${preset.name} as default`}
                            onClick={() => handleSetDefaultPreset(preset.id)}
                          >
                            ☆
                          </button>
                        )}
                        <button
                          type="button"
                          className="advisor-setup__preset-action-btn advisor-setup__preset-action-btn--delete"
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
                <div className="advisor-setup__preset-popover-footer">
                  <button
                    type="button"
                    className="advisor-setup__preset-footer-btn"
                    onClick={openSavePresetModal}
                  >
                    Save current as…
                  </button>
                </div>
              </div>
            )}
          </div>
          {(isPresetDirty || !activePresetId) && (
            <button
              type="button"
              className="advisor-setup__preset-save-link"
              onClick={openSavePresetModal}
            >
              Save preset…
            </button>
          )}
        </div>

        {!modelsLoading && models.length === 0 && (
          <p className="advisor-setup__model-empty">
            No models available. Add and test API keys in Settings → LLM API Keys (Ollama URL, NVIDIA, OpenRouter, etc.).
          </p>
        )}

        {modelSummaryLine && (
          <p className="advisor-setup__model-summary">{modelSummaryLine}</p>
        )}
        {isPresetDirty && (
          <p className="advisor-setup__preset-dirty">Unsaved changes from preset</p>
        )}

        {modelMode === 'simple' ? (
          <div className="advisor-setup__model-simple">
            <label className="advisor-setup__model-label">
              All advisors and the verdict/tiebreaker use the same model
            </label>
            <SearchableModelSelect
              models={models}
              value={chosenModel}
              onChange={handleSimpleModelChange}
              placeholder={modelsLoading ? 'Loading models…' : `Search ${models.length} models…`}
              isLoading={modelsLoading}
              isDisabled={modelsLoading}
            />
          </div>
        ) : (
          <div className="advisor-setup__model-advanced">
            {selectedPersonaIds.length === 0 ? (
              <p className="advisor-setup__model-advanced-empty">
                Select at least one advisor above to assign models.
              </p>
            ) : (
              selectedPersonaIds.map((id) => {
                const persona = personas.find((p) => p.id === id);
                if (!persona) return null;
                return (
                  <div key={id} className="advisor-setup__model-row">
                    <span className="advisor-setup__model-row-persona">
                      <span>{persona.avatar_emoji}</span>
                      <span>{persona.name}</span>
                    </span>
                    <SearchableModelSelect
                      models={models}
                      value={modelAssignments[id] || ''}
                      onChange={(modelId) => handleModelAssignment(id, modelId)}
                      placeholder={modelsLoading ? 'Loading…' : 'Search models…'}
                      isLoading={modelsLoading}
                      isDisabled={modelsLoading}
                    />
                  </div>
                );
              })
            )}
            <div className="advisor-setup__model-row advisor-setup__model-row--verdict">
              <span className="advisor-setup__model-row-persona">
                <span>⚖️</span>
                <span>Verdict / Tiebreaker</span>
              </span>
              <SearchableModelSelect
                models={models}
                value={tiebreakerModel || ''}
                onChange={handleTiebreakerModelChange}
                placeholder={modelsLoading ? 'Loading…' : 'Search models…'}
                isLoading={modelsLoading}
                isDisabled={modelsLoading}
              />
            </div>
          </div>
        )}
      </div>

      {/* Persona Gallery */}
      <div className="advisor-setup__section">
        <button
          type="button"
          className="advisor-setup__section-header advisor-setup__section-header--collapsible"
          onClick={() => setPersonasExpanded((v) => !v)}
          aria-expanded={personasExpanded}
        >
          <span className="advisor-setup__section-label">Choose Advisors</span>
          <div className="advisor-setup__section-header-right">
            <span className={`advisor-setup__count-badge ${selectedCount >= 2 ? 'advisor-setup__count-badge--valid' : ''}`}>
              {selectedCount} / 4 selected
            </span>
            <span className={`advisor-setup__chevron ${personasExpanded ? '' : 'advisor-setup__chevron--collapsed'}`}>
              ›
            </span>
          </div>
        </button>

        <div className={`advisor-setup__collapsible ${personasExpanded ? 'advisor-setup__collapsible--open' : ''}`}>
          <div className="advisor-setup__collapsible-inner">
            {/* Use Recommended Button */}
            <div className="advisor-setup__recommended-row">
              <button
                className="advisor-setup__recommended-btn"
                onClick={handleUseRecommended}
                type="button"
              >
                <span className="advisor-setup__recommended-icon">⚡</span>
                Use Recommended Panel
                <span className="advisor-setup__recommended-hint">Skeptic · Pragmatist · Innovator</span>
              </button>
            </div>

            {personasLoading ? (
              <div className="advisor-setup__personas-loading">Loading advisors...</div>
            ) : (
              <div className="advisor-setup__persona-gallery">
                {personas.map((persona) => {
                  const selected = selectedPersonaIds.includes(persona.id);
                  return (
                    <div
                      key={persona.id}
                      role="button"
                      tabIndex={!selected && selectedCount >= 4 ? -1 : 0}
                      className={`advisor-setup__persona-card ${selected ? 'advisor-setup__persona-card--selected' : ''} ${!selected && selectedCount >= 4 ? 'advisor-setup__persona-card--disabled' : ''} ${persona.is_customized ? 'advisor-setup__persona-card--customized' : ''}`}
                      onClick={() => togglePersona(persona.id)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); togglePersona(persona.id); } }}
                      style={selected ? { '--persona-color': persona.color } : {}}
                      aria-pressed={selected}
                    >
                      <button
                        type="button"
                        className="advisor-setup__persona-edit-btn"
                        onClick={(e) => openEditModal(e, persona)}
                        title="Edit persona"
                        aria-label={`Edit ${persona.name}`}
                        tabIndex={0}
                      >
                        ✏️
                      </button>
                      <span className="advisor-setup__persona-emoji">{persona.avatar_emoji}</span>
                      <span className="advisor-setup__persona-name">{persona.name}</span>
                      <span className="advisor-setup__persona-role">{persona.role}</span>
                      <span className="advisor-setup__persona-desc">{persona.description}</span>
                      {persona.is_customized && (
                        <span className="advisor-setup__persona-custom-badge" title="Customized">✦</span>
                      )}
                      {selected && (
                        <span className="advisor-setup__persona-check" style={{ backgroundColor: persona.color }}>
                          ✓
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Save Preset Modal */}
      {saveModalOpen && (
        <div className="advisor-setup__edit-overlay" onClick={closeSavePresetModal}>
          <div className="advisor-setup__edit-modal advisor-setup__edit-modal--compact" onClick={(e) => e.stopPropagation()}>
            <div className="advisor-setup__edit-header">
              <span className="advisor-setup__edit-emoji">📁</span>
              <span className="advisor-setup__edit-title">Save Preset</span>
              <button type="button" className="advisor-setup__edit-close" onClick={closeSavePresetModal} aria-label="Close">✕</button>
            </div>

            <div className="advisor-setup__edit-body">
              <label className="advisor-setup__edit-field">
                <span className="advisor-setup__edit-label">Preset Name</span>
                <input
                  type="text"
                  className="advisor-setup__edit-input"
                  value={saveForm.name}
                  onChange={(e) => setSaveForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. Startup GTM Debate"
                  maxLength={80}
                  autoFocus
                />
              </label>

              {activePresetId && (
                <label className="advisor-setup__preset-checkbox">
                  <input
                    type="checkbox"
                    checked={saveForm.updateExisting}
                    onChange={(e) => setSaveForm((f) => ({ ...f, updateExisting: e.target.checked }))}
                  />
                  <span>Update existing preset</span>
                </label>
              )}

              <label className="advisor-setup__preset-checkbox">
                <input
                  type="checkbox"
                  checked={saveForm.isDefault}
                  onChange={(e) => setSaveForm((f) => ({ ...f, isDefault: e.target.checked }))}
                />
                <span>Set as default preset</span>
              </label>

              <label className="advisor-setup__preset-checkbox">
                <input
                  type="checkbox"
                  checked={saveForm.includeConfig}
                  onChange={(e) => setSaveForm((f) => ({ ...f, includeConfig: e.target.checked }))}
                />
                <span>Include rounds + web search settings</span>
              </label>
            </div>

            <div className="advisor-setup__edit-footer">
              <div className="advisor-setup__edit-footer-right">
                <button
                  type="button"
                  className="advisor-setup__edit-btn advisor-setup__edit-btn--cancel"
                  onClick={closeSavePresetModal}
                  disabled={presetSaving}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="advisor-setup__edit-btn advisor-setup__edit-btn--save"
                  onClick={handleSavePreset}
                  disabled={presetSaving || !saveForm.name.trim()}
                >
                  {presetSaving ? 'Saving…' : 'Save Preset'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit Persona Modal */}
      {editingPersona && (
        <div className="advisor-setup__edit-overlay" onClick={closeEditModal}>
          <div className="advisor-setup__edit-modal" onClick={(e) => e.stopPropagation()}>
            <div className="advisor-setup__edit-header">
              <span className="advisor-setup__edit-emoji">{editingPersona.avatar_emoji}</span>
              <span className="advisor-setup__edit-title">Edit Persona</span>
              <button type="button" className="advisor-setup__edit-close" onClick={closeEditModal} aria-label="Close">✕</button>
            </div>

            <div className="advisor-setup__edit-body">
              <div className="advisor-setup__edit-emoji-row">
                <label className="advisor-setup__edit-field advisor-setup__edit-field--emoji">
                  <span className="advisor-setup__edit-label">Emoji / Icon</span>
                  <input
                    type="text"
                    className="advisor-setup__edit-input advisor-setup__edit-emoji-input"
                    value={editForm.avatar_emoji}
                    onChange={(e) => setEditForm((f) => ({ ...f, avatar_emoji: e.target.value }))}
                    placeholder="e.g. 🔍"
                    maxLength={4}
                  />
                </label>
                <div className="advisor-setup__edit-emoji-preview">
                  {editForm.avatar_emoji || editingPersona?.avatar_emoji}
                </div>
              </div>

              <label className="advisor-setup__edit-field">
                <span className="advisor-setup__edit-label">Name</span>
                <input
                  type="text"
                  className="advisor-setup__edit-input"
                  value={editForm.name}
                  onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                />
              </label>

              <label className="advisor-setup__edit-field">
                <span className="advisor-setup__edit-label">Role</span>
                <input
                  type="text"
                  className="advisor-setup__edit-input"
                  value={editForm.role}
                  onChange={(e) => setEditForm((f) => ({ ...f, role: e.target.value }))}
                />
              </label>

              <label className="advisor-setup__edit-field">
                <span className="advisor-setup__edit-label">Description</span>
                <textarea
                  className="advisor-setup__edit-textarea advisor-setup__edit-textarea--short"
                  rows={2}
                  value={editForm.description}
                  onChange={(e) => setEditForm((f) => ({ ...f, description: e.target.value }))}
                />
              </label>

              <label className="advisor-setup__edit-field">
                <span className="advisor-setup__edit-label">System Prompt</span>
                <textarea
                  className="advisor-setup__edit-textarea"
                  rows={7}
                  value={editForm.system_prompt}
                  onChange={(e) => setEditForm((f) => ({ ...f, system_prompt: e.target.value }))}
                />
              </label>
            </div>

            <div className="advisor-setup__edit-footer">
              {editingPersona.is_customized && (
                <button
                  type="button"
                  className="advisor-setup__edit-btn advisor-setup__edit-btn--reset"
                  onClick={handleEditReset}
                  disabled={editSaving}
                >
                  Reset to Default
                </button>
              )}
              <div className="advisor-setup__edit-footer-right">
                <button
                  type="button"
                  className="advisor-setup__edit-btn advisor-setup__edit-btn--cancel"
                  onClick={closeEditModal}
                  disabled={editSaving}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="advisor-setup__edit-btn advisor-setup__edit-btn--save"
                  onClick={handleEditSave}
                  disabled={editSaving}
                >
                  {editSaving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

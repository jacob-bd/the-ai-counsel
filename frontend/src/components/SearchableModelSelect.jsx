import { useMemo } from 'react';
import Select, { components as SelectComponents } from 'react-select';
import {
  getModelPickerDisplayName,
  getModelRawId,
  modelSearchMatches,
} from '../utils/modelHelpers';

const PROVIDER_ORDER = [
  'OpenAI (Direct)',
  'Anthropic (Direct)',
  'Google (Direct)',
  'Mistral (Direct)',
  'DeepSeek (Direct)',
  'Groq (Direct)',
  'Notion2API (Direct)',
  'OpenRouter (Cloud)',
  'Local (Ollama)',
];

function getGroupLabel(model) {
  const isOpenRouter = model.source === 'openrouter' || model.provider === 'OpenRouter';
  const isOllama = model.id?.startsWith('ollama:') || model.provider === 'Ollama';
  const isNotion2Api = model.source === 'notion2api'
    || model.provider?.toLowerCase() === 'notion2api'
    || model.id?.startsWith('notion2api:');

  if (isOpenRouter) return 'OpenRouter (Cloud)';
  if (isOllama) return 'Local (Ollama)';
  if (isNotion2Api) return 'Notion2API (Direct)';
  return `${model.provider || 'Direct'} (Direct)`;
}

function ModelOption(props) {
  const { data, isSelected } = props;
  const tooltip = data.rawId && data.rawId !== data.label
    ? `${data.label} — ${data.rawId}`
    : data.label;

  return (
    <SelectComponents.Option {...props}>
      <div title={tooltip} style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ flex: 1, minWidth: 0, fontWeight: isSelected ? 650 : 500 }}>
            {data.label}
          </span>
          {isSelected && (
            <span aria-label="Selected" style={{ color: '#93c5fd', fontWeight: 800 }}>
              ✓
            </span>
          )}
        </div>
        {data.rawId && data.rawId !== data.label && (
          <div
            style={{
              marginTop: '2px',
              color: isSelected ? '#bfdbfe' : '#94a3b8',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
              fontSize: '10px',
              lineHeight: 1.25,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {data.rawId}
          </div>
        )}
      </div>
    </SelectComponents.Option>
  );
}

function ModelSingleValue(props) {
  const { data } = props;
  const tooltip = data.rawId && data.rawId !== data.label
    ? `${data.label} — ${data.rawId}`
    : data.label;

  return (
    <SelectComponents.SingleValue {...props}>
      <span
        title={tooltip}
        style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
      >
        {data.label}
      </span>
    </SelectComponents.SingleValue>
  );
}

/** Friendly labels are presentation-only; exact model IDs remain the values. */
export default function SearchableModelSelect({
  models,
  value,
  onChange,
  placeholder = 'Search and select a model...',
  isDisabled = false,
  isLoading = false,
  allModels = null,
  autoOpen = false,
}) {
  const options = useMemo(() => {
    const grouped = {};

    for (const model of Array.isArray(models) ? models : []) {
      if (!model?.id) continue;
      const groupLabel = getGroupLabel(model);
      if (!grouped[groupLabel]) grouped[groupLabel] = [];

      const label = getModelPickerDisplayName(model);
      const rawId = getModelRawId(model);
      grouped[groupLabel].push({
        value: model.id,
        label,
        rawId,
        model,
        searchText: [label, rawId, model.id, model.name, model.provider, model.source]
          .filter(Boolean)
          .join(' '),
      });
    }

    return Object.keys(grouped)
      .sort((a, b) => {
        const indexA = PROVIDER_ORDER.indexOf(a);
        const indexB = PROVIDER_ORDER.indexOf(b);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return a.localeCompare(b);
      })
      .map((group) => ({
        label: group,
        options: grouped[group].sort((a, b) => (
          a.label.localeCompare(b.label) || a.rawId.localeCompare(b.rawId)
        )),
      }));
  }, [models]);

  const selectedOption = useMemo(() => {
    const available = options.flatMap((group) => group.options);
    const selected = available.find((option) => option.value === value);
    if (selected || !value || !Array.isArray(allModels)) return selected || null;

    const currentModel = allModels.find((model) => model.id === value);
    if (!currentModel) return null;

    const label = getModelPickerDisplayName(currentModel);
    const rawId = getModelRawId(currentModel);
    return {
      value: currentModel.id,
      label,
      rawId,
      model: currentModel,
      searchText: [label, rawId, currentModel.id, currentModel.name].filter(Boolean).join(' '),
    };
  }, [allModels, options, value]);

  const customStyles = useMemo(() => ({
    control: (base, state) => ({
      ...base,
      backgroundColor: 'rgba(30, 41, 59, 0.8)',
      borderColor: state.isFocused ? '#3b82f6' : 'rgba(148, 163, 184, 0.2)',
      borderRadius: '8px',
      minHeight: '38px',
      boxShadow: state.isFocused ? '0 0 0 2px rgba(59, 130, 246, 0.3)' : 'none',
      '&:hover': { borderColor: '#3b82f6' },
    }),
    menu: (base) => ({
      ...base,
      backgroundColor: 'rgba(30, 41, 59, 0.99)',
      borderRadius: '8px',
      border: '1px solid rgba(148, 163, 184, 0.25)',
      boxShadow: '0 10px 40px rgba(0, 0, 0, 0.5)',
      zIndex: 100,
      minWidth: 'min(400px, calc(100vw - 24px))',
      maxWidth: 'calc(100vw - 24px)',
    }),
    menuPortal: (base) => ({ ...base, zIndex: 9999 }),
    menuList: (base) => ({ ...base, maxHeight: '320px', padding: '4px' }),
    group: (base) => ({ ...base, paddingTop: '8px', paddingBottom: '4px' }),
    groupHeading: (base) => ({
      ...base,
      color: '#94a3b8',
      fontSize: '11px',
      fontWeight: '700',
      textTransform: 'uppercase',
      letterSpacing: '0.5px',
      marginBottom: '4px',
      paddingLeft: '8px',
    }),
    option: (base, state) => ({
      ...base,
      backgroundColor: state.isSelected
        ? 'rgba(37, 99, 235, 0.48)'
        : state.isFocused
          ? 'rgba(148, 163, 184, 0.12)'
          : 'transparent',
      borderLeft: state.isSelected ? '3px solid #60a5fa' : '3px solid transparent',
      color: state.isSelected ? '#ffffff' : '#e2e8f0',
      padding: '9px 12px',
      borderRadius: '4px',
      cursor: 'pointer',
      fontSize: '13px',
      '&:active': { backgroundColor: 'rgba(59, 130, 246, 0.34)' },
    }),
    singleValue: (base) => ({
      ...base,
      color: '#e2e8f0',
      fontSize: '13px',
      maxWidth: 'calc(100% - 4px)',
    }),
    input: (base) => ({ ...base, color: '#e2e8f0' }),
    placeholder: (base) => ({ ...base, color: '#64748b', fontSize: '13px' }),
    indicatorSeparator: () => ({ display: 'none' }),
    dropdownIndicator: (base) => ({
      ...base,
      color: '#64748b',
      padding: '6px',
      '&:hover': { color: '#94a3b8' },
    }),
    clearIndicator: (base) => ({
      ...base,
      color: '#64748b',
      padding: '6px',
      '&:hover': { color: '#f87171' },
    }),
    noOptionsMessage: (base) => ({ ...base, color: '#64748b', fontSize: '13px' }),
    loadingMessage: (base) => ({ ...base, color: '#64748b' }),
  }), []);

  return (
    <Select
      options={options}
      value={selectedOption}
      onChange={(option) => onChange(option ? option.value : '')}
      placeholder={placeholder}
      isDisabled={isDisabled}
      isLoading={isLoading}
      isClearable
      isSearchable
      autoFocus={autoOpen}
      defaultMenuIsOpen={autoOpen}
      openMenuOnFocus={autoOpen}
      closeMenuOnSelect
      blurInputOnSelect
      menuPlacement="auto"
      menuShouldScrollIntoView
      styles={customStyles}
      components={{ Option: ModelOption, SingleValue: ModelSingleValue }}
      menuPortalTarget={typeof document !== 'undefined' ? document.body : null}
      classNamePrefix="model-select"
      aria-label="Model selector"
      noOptionsMessage={() => 'No models found'}
      loadingMessage={() => 'Loading models...'}
      filterOption={(option, inputValue) => modelSearchMatches(option.data.searchText, inputValue)}
    />
  );
}

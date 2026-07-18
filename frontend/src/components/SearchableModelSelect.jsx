import { useMemo } from 'react';
import Select from 'react-select';

/**
 * Searchable model selector using react-select.
 * Provides type-to-filter functionality for large model lists.
 */
export default function SearchableModelSelect({
  models,
  value,
  onChange,
  placeholder = "Search and select a model...",
  isDisabled = false,
  isLoading = false,
  allModels = null, // Optional: all models to find current value if filtered out
  autoOpen = false,
}) {
  // Convert models to react-select format with grouping
  const groupedOptions = models.reduce((acc, model) => {
    // Determine group label
    let groupLabel;
    // Use source field if available, otherwise fallback to provider check
    const isOpenRouter = model.source === 'openrouter' || model.provider === 'OpenRouter';
    const isOllama = model.id?.startsWith('ollama:') || model.provider === 'Ollama';
    const isXaiOAuth = model.id?.startsWith('xai-oauth:') || model.source === 'xai-oauth';
    const isOpenAiOAuth = model.id?.startsWith('openai-oauth:') || model.source === 'openai-oauth';
    const isCopilot = model.id?.startsWith('github-copilot:') || model.source === 'github-copilot';

    if (isOpenRouter) {
      groupLabel = 'OpenRouter (Cloud)';
    } else if (isOllama) {
      groupLabel = 'Local (Ollama)';
    } else if (isXaiOAuth) {
      groupLabel = 'xAI SuperGrok (Subscription)';
    } else if (isOpenAiOAuth) {
      groupLabel = 'ChatGPT Plus/Pro (Subscription)';
    } else if (isCopilot) {
      groupLabel = 'GitHub Copilot (Subscription)';
    } else {
      groupLabel = `${model.provider || 'Direct'} (Direct)`;
    }

    if (!acc[groupLabel]) {
      acc[groupLabel] = [];
    }
    acc[groupLabel].push({
      value: model.id,
      label: model.name,
      model: model, // Keep full model data for reference
    });
    return acc;
  }, {});

  // Convert to react-select grouped format
  const providerOrder = [
    'OpenAI (Direct)', 'Anthropic (Direct)', 'Google (Direct)', 'Mistral (Direct)', 'DeepSeek (Direct)',
    'Groq (Direct)',
    'xAI SuperGrok (Subscription)', 'ChatGPT Plus/Pro (Subscription)', 'GitHub Copilot (Subscription)',
    'OpenRouter (Cloud)',
    'Local (Ollama)'
  ];

  const options = Object.keys(groupedOptions)
    .sort((a, b) => {
      const indexA = providerOrder.indexOf(a);
      const indexB = providerOrder.indexOf(b);
      if (indexA !== -1 && indexB !== -1) return indexA - indexB;
      if (indexA !== -1) return -1;
      if (indexB !== -1) return 1;
      return a.localeCompare(b);
    })
    .map(group => ({
      label: group,
      options: groupedOptions[group],
    }));

  // Find current value in options
  let selectedOption = options
    .flatMap(group => group.options)
    .find(opt => opt.value === value) || null;

  // If current value not found in filtered options, try to find it in allModels
  // This keeps the selection visible even when filtered out
  if (!selectedOption && value && allModels) {
    const currentModel = allModels.find(m => m.id === value);
    if (currentModel) {
      selectedOption = {
        value: currentModel.id,
        label: `${currentModel.name} (filtered)`,
        model: currentModel,
      };
    }
  }

  const customStyles = useMemo(() => ({
    control: (base, state) => ({
      ...base,
      backgroundColor: 'rgba(30, 41, 59, 0.8)',
      borderColor: state.isFocused ? '#3b82f6' : 'rgba(148, 163, 184, 0.2)',
      borderRadius: '8px',
      minHeight: '38px',
      boxShadow: state.isFocused ? '0 0 0 2px rgba(59, 130, 246, 0.3)' : 'none',
      '&:hover': {
        borderColor: '#3b82f6',
      },
    }),
    menu: (base) => ({
      ...base,
      backgroundColor: 'rgba(30, 41, 59, 0.98)',
      borderRadius: '8px',
      border: '1px solid rgba(148, 163, 184, 0.2)',
      boxShadow: '0 10px 40px rgba(0, 0, 0, 0.5)',
      zIndex: 100,
      minWidth: '360px',
    }),
    menuPortal: (base) => ({
      ...base,
      zIndex: 9999,
    }),
    menuList: (base) => ({
      ...base,
      maxHeight: '300px',
      padding: '4px',
    }),
    group: (base) => ({
      ...base,
      paddingTop: '8px',
      paddingBottom: '4px',
    }),
    groupHeading: (base) => ({
      ...base,
      color: '#94a3b8',
      fontSize: '11px',
      fontWeight: '600',
      textTransform: 'uppercase',
      letterSpacing: '0.5px',
      marginBottom: '4px',
      paddingLeft: '8px',
    }),
    option: (base, state) => ({
      ...base,
      backgroundColor: state.isSelected
        ? 'rgba(59, 130, 246, 0.3)'
        : state.isFocused
          ? 'rgba(59, 130, 246, 0.15)'
          : 'transparent',
      color: state.isSelected ? '#ffffff' : '#e2e8f0',
      padding: '8px 12px',
      borderRadius: '4px',
      cursor: 'pointer',
      fontSize: '13px',
      '&:active': {
        backgroundColor: 'rgba(59, 130, 246, 0.4)',
      },
    }),
    singleValue: (base) => ({
      ...base,
      color: '#e2e8f0',
      fontSize: '13px',
    }),
    input: (base) => ({
      ...base,
      color: '#e2e8f0',
    }),
    placeholder: (base) => ({
      ...base,
      color: '#64748b',
      fontSize: '13px',
    }),
    indicatorSeparator: () => ({
      display: 'none',
    }),
    dropdownIndicator: (base) => ({
      ...base,
      color: '#64748b',
      padding: '6px',
      '&:hover': {
        color: '#94a3b8',
      },
    }),
    clearIndicator: (base) => ({
      ...base,
      color: '#64748b',
      padding: '6px',
      '&:hover': {
        color: '#f87171',
      },
    }),
    noOptionsMessage: (base) => ({
      ...base,
      color: '#64748b',
      fontSize: '13px',
    }),
    loadingMessage: (base) => ({
      ...base,
      color: '#64748b',
    }),
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
      styles={customStyles}
      menuPortalTarget={document.body}
      classNamePrefix="model-select"
      noOptionsMessage={() => "No models found"}
      loadingMessage={() => "Loading models..."}
      filterOption={(option, inputValue) => {
        if (!inputValue) return true;
        // Normalize dashes/underscores to spaces so "kimi k2" matches "kimi-k2"
        const normalize = (s) => s.toLowerCase().replace(/[-_]/g, ' ');
        const q = normalize(inputValue);
        return normalize(option.label).includes(q) || normalize(option.value).includes(q);
      }}
    />
  );
}

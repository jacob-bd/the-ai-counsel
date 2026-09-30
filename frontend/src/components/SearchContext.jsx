import { useState } from 'react';
import { useI18n } from '../i18n';
import './SearchContext.css';

/**
 * Parse search results string into structured data
 * Format: "Result N:\nTitle: ...\nURL: ...\nSource: ...\nSummary: ..."
 */
function parseSearchResults(searchContext) {
  if (!searchContext) return [];

  const results = [];
  const blocks = searchContext.split(/Result \d+:/);

  for (const block of blocks) {
    if (!block.trim()) continue;

    const titleMatch = block.match(/Title:\s*(.+)/);
    const urlMatch = block.match(/URL:\s*(.+)/);
    const sourceMatch = block.match(/Source:\s*(.+)/);
    const summaryMatch = block.match(/Summary:\s*([\s\S]*?)(?=\n\n|$)/);

    if (titleMatch && urlMatch) {
      results.push({
        title: titleMatch[1].trim(),
        url: urlMatch[1].trim(),
        source: sourceMatch ? sourceMatch[1].trim() : '',
        summary: summaryMatch ? summaryMatch[1].trim() : ''
      });
    }
  }

  return results;
}

export default function SearchContext({ searchQuery, extractedQuery, searchContext }) {
  const { t } = useI18n();
  const [isExpanded, setIsExpanded] = useState(false);

  if (!searchContext) return null;

  const sources = parseSearchResults(searchContext);

  // Truncate display query for preview
  const displayQuery = searchQuery && searchQuery.length > 60
    ? searchQuery.substring(0, 60) + '...'
    : searchQuery;

  return (
    <div className="search-context">
      {/* Accordion Header */}
      <button
        className={`search-accordion-header ${isExpanded ? 'expanded' : ''}`}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className="search-icon">🔍</span>
        <span className="search-label">{t('Web Search')}</span>
        {searchQuery && (
          <span
            className="search-query-preview"
            title={extractedQuery ? t('Search terms sent: {terms}', { terms: extractedQuery }) : searchQuery}
          >
            "{displayQuery}"
          </span>
        )}
        <span className="accordion-arrow">{isExpanded ? '▼' : '▶'}</span>
      </button>

      {/* Accordion Content */}
      {isExpanded && (
        <div className="search-accordion-content">
          <div className="search-results-raw">
            <pre>{searchContext}</pre>
          </div>
        </div>
      )}

      {/* Sources - Always visible */}
      {sources.length > 0 && (
        <div className="search-sources">
          <span className="sources-label">{t('Sources:')}</span>
          <div className="sources-list">
            {sources.map((source, index) => (
              <a
                key={index}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="source-link"
                title={source.title + (source.summary ? '\n\n' + source.summary : '')}
              >
                {source.source || source.title || t('Source {number}', { number: index + 1 })}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

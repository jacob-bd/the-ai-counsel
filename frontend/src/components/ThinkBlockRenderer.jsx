import { useState } from 'react';
import { MarkdownRenderer } from './MarkdownContent';
import { useI18n } from '../i18n';
import './ThinkBlockRenderer.css';

// Collapsible think block component
function ThinkBlock({ content }) {
  const { t } = useI18n();
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className={`think-block ${isExpanded ? 'expanded' : 'collapsed'}`}>
      <button
        className="think-toggle"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className="think-icon">💭</span>
        <span className="think-label">{t('Reasoning')}</span>
        <span className="think-chevron">{isExpanded ? '▼' : '▶'}</span>
      </button>
      {isExpanded && (
        <div className="think-content">
          <MarkdownRenderer>{content}</MarkdownRenderer>
        </div>
      )}
    </div>
  );
}

// Helper to parse and render content with <think> tags styled differently
export default function ThinkBlockRenderer({ content }) {
  const { t } = useI18n();
  if (!content || typeof content !== 'string') {
    return <MarkdownRenderer>{String(content || t('No response'))}</MarkdownRenderer>;
  }

  // Regex to match <think>...</think> blocks (handles multiline)
  const thinkRegex = /<think>([\s\S]*?)<\/think>/gi;
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = thinkRegex.exec(content)) !== null) {
    // Add text before the think block
    if (match.index > lastIndex) {
      const textBefore = content.slice(lastIndex, match.index).trim();
      if (textBefore) {
        parts.push({ type: 'text', content: textBefore });
      }
    }
    // Add the think block
    parts.push({ type: 'think', content: match[1].trim() });
    lastIndex = match.index + match[0].length;
  }

  // Add remaining text after last think block
  if (lastIndex < content.length) {
    const textAfter = content.slice(lastIndex).trim();
    if (textAfter) {
      parts.push({ type: 'text', content: textAfter });
    }
  }

  // If no think blocks found, render normally
  if (parts.length === 0) {
    return <MarkdownRenderer>{content}</MarkdownRenderer>;
  }

  return (
    <>
      {parts.map((part, index) => (
        part.type === 'think' ? (
          <ThinkBlock key={index} content={part.content} />
        ) : (
          <div key={index} className="response-answer">
            <MarkdownRenderer>{part.content}</MarkdownRenderer>
          </div>
        )
      ))}
    </>
  );
}

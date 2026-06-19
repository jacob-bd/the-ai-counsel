import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

const REMARK_PLUGINS = [remarkGfm];
// rehype-raw allows raw HTML elements (e.g. <details>, <summary>, <mark>)
// that models commonly emit in their responses.
const REHYPE_PLUGINS = [rehypeRaw];

export function MarkdownRenderer({ children }) {
  const content = typeof children === 'string' ? children : String(children || '');

  return (
    <ReactMarkdown remarkPlugins={REMARK_PLUGINS} rehypePlugins={REHYPE_PLUGINS}>
      {content}
    </ReactMarkdown>
  );
}

export default function MarkdownContent({ children, className = '' }) {
  const content = typeof children === 'string' ? children : String(children || '');
  const classes = ['markdown-content', className].filter(Boolean).join(' ');

  return (
    <div className={classes}>
      <MarkdownRenderer>{content}</MarkdownRenderer>
    </div>
  );
}

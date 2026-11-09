'use client';

import React from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check } from 'lucide-react';

interface CodeViewerProps {
  code: string;
  language: string;
  filename?: string;
}

// Custom theme overriding oneDark to match our charcoal palette
const charcoalTheme = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...(oneDark['pre[class*="language-"]'] || {}),
    background: 'var(--bg-primary)',
    margin: 0,
    fontSize: '13px',
    lineHeight: '1.6',
    fontFamily: 'var(--font-mono)',
  },
  'code[class*="language-"]': {
    ...(oneDark['code[class*="language-"]'] || {}),
    background: 'none',
    fontFamily: 'var(--font-mono)',
  },
};

export function CodeViewer({ code, language, filename }: CodeViewerProps) {
  const [copied, setCopied] = React.useState(false);

  const langMap: Record<string, string> = {
    typescript: 'tsx',
    python: 'python',
    json: 'json',
    css: 'css',
    yaml: 'yaml',
    markdown: 'markdown',
    dockerfile: 'docker',
    text: 'text',
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!code) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-dim)]">
        <p className="text-sm">Select a file to view its contents</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      {filename && (
        <div className="flex items-center justify-between px-3 py-1.5 bg-[var(--bg-secondary)] border-b border-[var(--border-subtle)]">
          <span className="text-xs text-[var(--text-muted)] font-mono">{filename}</span>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-[var(--text-dim)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"
          >
            {copied ? <Check size={12} className="text-[var(--state-completed)]" /> : <Copy size={12} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      )}

      {/* Code */}
      <div className="flex-1 overflow-auto code-viewer">
        <SyntaxHighlighter
          language={langMap[language] || language || 'text'}
          style={charcoalTheme}
          showLineNumbers
          lineNumberStyle={{
            color: 'var(--text-dim)',
            fontSize: '12px',
            minWidth: '3em',
            paddingRight: '1em',
            opacity: 0.5,
          }}
          customStyle={{
            margin: 0,
            padding: '12px 0',
            background: 'var(--bg-primary)',
            minHeight: '100%',
          }}
          wrapLongLines={false}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}

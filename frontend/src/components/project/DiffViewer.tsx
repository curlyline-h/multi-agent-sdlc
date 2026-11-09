'use client';

import React from 'react';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued';
import { FileDiff } from '@/types/project';
import { Plus, Minus, FileCode2 } from 'lucide-react';

interface DiffViewerProps {
  diff: FileDiff;
}

const charcoalDiffStyles = {
  variables: {
    dark: {
      diffViewerBackground: 'var(--bg-primary)',
      diffViewerColor: 'var(--text-secondary)',
      addedBackground: 'rgba(16, 185, 129, 0.08)',
      addedColor: '#34d399',
      removedBackground: 'rgba(239, 68, 68, 0.08)',
      removedColor: '#f87171',
      wordAddedBackground: 'rgba(16, 185, 129, 0.2)',
      wordRemovedBackground: 'rgba(239, 68, 68, 0.2)',
      addedGutterBackground: 'rgba(16, 185, 129, 0.05)',
      removedGutterBackground: 'rgba(239, 68, 68, 0.05)',
      gutterBackground: 'var(--bg-secondary)',
      gutterBackgroundDark: 'var(--bg-tertiary)',
      highlightBackground: 'rgba(99, 102, 241, 0.08)',
      highlightGutterBackground: 'rgba(99, 102, 241, 0.05)',
      codeFoldGutterBackground: 'var(--bg-tertiary)',
      codeFoldBackground: 'var(--bg-secondary)',
      emptyLineBackground: 'var(--bg-primary)',
      codeFoldContentColor: 'var(--text-dim)',
    },
  },
  line: {
    fontSize: '13px',
    fontFamily: 'var(--font-mono)',
  },
  gutter: {
    fontSize: '12px',
    fontFamily: 'var(--font-mono)',
    minWidth: '40px',
    padding: '0 8px',
  },
  contentText: {
    fontFamily: 'var(--font-mono)',
  },
};

export function DiffViewer({ diff }: DiffViewerProps) {
  return (
    <div className="h-full flex flex-col">
      {/* Diff header */}
      <div className="flex items-center gap-3 px-3 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border-subtle)]">
        <FileCode2 size={14} className="text-[var(--text-muted)]" />
        <span className="text-xs font-mono text-[var(--text-secondary)] flex-1 truncate">
          {diff.path}
        </span>
        <div className="flex items-center gap-2 text-xs">
          {diff.additions > 0 && (
            <span className="flex items-center gap-0.5 text-[var(--diff-add-text)]">
              <Plus size={10} /> {diff.additions}
            </span>
          )}
          {diff.deletions > 0 && (
            <span className="flex items-center gap-0.5 text-[var(--diff-remove-text)]">
              <Minus size={10} /> {diff.deletions}
            </span>
          )}
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
              diff.status === 'added'
                ? 'bg-[var(--state-completed-bg)] text-[var(--state-completed)]'
                : diff.status === 'deleted'
                ? 'bg-[var(--state-error-bg)] text-[var(--state-error)]'
                : 'bg-[var(--state-drafting-bg)] text-[var(--state-drafting)]'
            }`}
          >
            {diff.status}
          </span>
        </div>
      </div>

      {/* Diff content */}
      <div className="flex-1 overflow-auto diff-viewer-wrapper">
        <ReactDiffViewer
          oldValue={diff.oldContent}
          newValue={diff.newContent}
          splitView={true}
          useDarkTheme={true}
          compareMethod={DiffMethod.WORDS}
          styles={charcoalDiffStyles}
          leftTitle="Before"
          rightTitle="After"
        />
      </div>
    </div>
  );
}

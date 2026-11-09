import React, { useEffect } from 'react';
import { useProjectViewStore } from '@/store/projectViewStore';
import { getFileContent } from '@/lib/api';
import { FileTree } from './FileTree';
import { CodeViewer } from './CodeViewer';
import { DiffViewer } from './DiffViewer';
import { DocumentViewer } from './DocumentViewer';
import { X, GitCompare, FileText, Code2, Files } from 'lucide-react';

export function ProjectPanel() {
  const {
    selectedFile,
    openTabs,
    activeTabPath,
    showDiff,
    diffs,
    selectedDiff,
    documents,
    selectedDocument,
    setActiveTab,
    closeTab,
    toggleDiffView,
    selectDiff,
    selectDocument,
    selectFile,
  } = useProjectViewStore();

  // Automatically fetch content if selected file content is not loaded yet
  useEffect(() => {
    if (selectedFile && selectedFile.content === undefined && selectedFile.type !== 'directory') {
      getFileContent(selectedFile.path)
        .then((data) => {
          if (data && data.content !== undefined) {
            selectFile({ ...selectedFile, content: data.content });
          }
        })
        .catch((err) => console.warn('Could not fetch file content:', err));
    }
  }, [selectedFile?.path]);

  // If a document is selected, show document viewer
  if (selectedDocument) {
    return (
      <div className="flex h-full bg-[var(--bg-primary)]">
        {/* Document list sidebar */}
        <div className="w-56 border-r border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
          <div className="panel-header">
            <div className="flex items-center gap-2">
              <FileText size={14} className="text-[var(--accent-primary)]" />
              <span>Documents</span>
            </div>
          </div>
          <div className="p-2 space-y-1">
            {documents.map((doc) => (
              <button
                key={doc.id}
                onClick={() => selectDocument(doc)}
                className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors ${
                  selectedDocument.id === doc.id
                    ? 'bg-[var(--accent-primary-glow)] text-[var(--text-primary)]'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
                }`}
              >
                <div className="font-medium truncate">{doc.title}</div>
                <div className="text-[10px] text-[var(--text-dim)] mt-0.5 uppercase">{doc.type.replace('_', ' ')}</div>
              </button>
            ))}
          </div>
        </div>
        {/* Document content */}
        <div className="flex-1">
          <DocumentViewer document={selectedDocument} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full bg-[var(--bg-primary)]">
      {/* ── File Tree Sidebar ────────────────────────────────────────────── */}
      <div className="w-56 border-r border-[var(--border-subtle)] bg-[var(--bg-secondary)] flex flex-col">
        <div className="panel-header">
          <div className="flex items-center gap-2">
            <Files size={14} className="text-[var(--accent-primary)]" />
            <span>Explorer</span>
          </div>
        </div>
        <div className="flex-1 overflow-hidden">
          <FileTree />
        </div>

        {/* Diff files section */}
        {diffs.length > 0 && (
          <div className="border-t border-[var(--border-subtle)]">
            <div className="panel-header">
              <div className="flex items-center gap-2">
                <GitCompare size={14} className="text-[var(--state-drafting)]" />
                <span>Changes</span>
              </div>
              <span className="text-[10px] bg-[var(--state-drafting-bg)] text-[var(--state-drafting)] px-1.5 py-0.5 rounded-full">
                {diffs.length}
              </span>
            </div>
            <div className="p-1 max-h-32 overflow-y-auto">
              {diffs.map((diff) => (
                <button
                  key={diff.path}
                  onClick={() => { selectDiff(diff); toggleDiffView(); }}
                  className={`w-full text-left px-2 py-1 rounded text-xs transition-colors flex items-center gap-2 ${
                    selectedDiff?.path === diff.path
                      ? 'bg-[var(--accent-primary-glow)] text-[var(--text-primary)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
                  }`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                    diff.status === 'added' ? 'bg-[var(--state-completed)]' :
                    diff.status === 'deleted' ? 'bg-[var(--state-error)]' :
                    'bg-[var(--state-drafting)]'
                  }`} />
                  <span className="truncate font-mono">{diff.path.split('/').pop()}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Main Content Area ────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col">
        {/* Tab bar */}
        {openTabs.length > 0 && (
          <div className="flex items-center bg-[var(--bg-secondary)] border-b border-[var(--border-subtle)] overflow-x-auto">
            {openTabs.map((tab) => (
              <div
                key={tab.path}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs border-r border-[var(--border-subtle)] cursor-pointer transition-colors min-w-0 ${
                  activeTabPath === tab.path
                    ? 'bg-[var(--bg-primary)] text-[var(--text-primary)] border-b-2 border-b-[var(--accent-primary)]'
                    : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
                }`}
                onClick={() => setActiveTab(tab.path)}
              >
                <Code2 size={12} />
                <span className="truncate max-w-[120px]">{tab.name}</span>
                {tab.isModified && <span className="w-1.5 h-1.5 rounded-full bg-[var(--state-drafting)]" />}
                <button
                  onClick={(e) => { e.stopPropagation(); closeTab(tab.path); }}
                  className="ml-1 hover:bg-[var(--bg-hover)] rounded p-0.5"
                >
                  <X size={10} />
                </button>
              </div>
            ))}

            {/* Toggle diff view button */}
            <button
              onClick={toggleDiffView}
              className={`ml-auto px-2 py-1 mx-1 rounded text-xs transition-colors flex items-center gap-1 ${
                showDiff
                  ? 'bg-[var(--state-drafting-bg)] text-[var(--state-drafting)]'
                  : 'text-[var(--text-dim)] hover:text-[var(--text-secondary)]'
              }`}
            >
              <GitCompare size={12} />
              Diff
            </button>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {showDiff && selectedDiff ? (
            <DiffViewer diff={selectedDiff} />
          ) : selectedFile ? (
            <CodeViewer
              code={selectedFile.content !== undefined ? selectedFile.content : '// Loading file content...'}
              language={selectedFile.language || 'text'}
              filename={selectedFile.path}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-[var(--text-dim)]">
              <Code2 size={32} className="mb-3 opacity-30" />
              <p className="text-sm">No file selected</p>
              <p className="text-xs mt-1">Select a file from the explorer to view its contents</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

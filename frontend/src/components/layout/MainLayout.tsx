'use client';

import React, { useRef } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { GraphPanel } from '@/components/graph/GraphPanel';
import { ProjectPanel } from '@/components/project/ProjectPanel';
import { TerminalPanel } from '@/components/terminal/TerminalPanel';
import { useLayoutStore } from '@/store/layoutStore';
import { useProjectViewStore } from '@/store/projectViewStore';
import { usePanelResize } from '@/hooks/usePanelResize';

export function MainLayout() {
  const {
    viewMode,
    chatPanelWidth,
    setChatPanelWidth,
    isTerminalVisible,
  } = useLayoutStore();

  const { documents, selectDocument, selectedDocument } = useProjectViewStore();

  const containerRef = useRef<HTMLDivElement>(null);
  const { size: panelSize, handleMouseDown } = usePanelResize({
    direction: 'horizontal',
    initialSize: chatPanelWidth,
    minSize: 25,
    maxSize: 65,
    containerRef,
    onResize: setChatPanelWidth,
  });

  // Handle "docs" view mode
  const handleDocsView = () => {
    if (documents.length > 0 && !selectedDocument) {
      selectDocument(documents[0]);
    }
  };

  // When switching to docs view, select first document
  React.useEffect(() => {
    if (viewMode === 'docs') {
      handleDocsView();
    }
  }, [viewMode]);

  return (
    <div className="flex h-screen bg-[var(--bg-void)] text-[var(--text-primary)] font-[family-name:var(--font-sans)] overflow-hidden">
      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <Sidebar />

      {/* ── Main area ────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* ── Header ───────────────────────────────────────────────────── */}
        <Header />

        {/* ── Content area ─────────────────────────────────────────────── */}
        <div ref={containerRef} className="flex-1 flex overflow-hidden">
          {/* ══ WORKSPACE VIEW: Chat + Graph ══════════════════════════════ */}
          {viewMode === 'workspace' && (
            <>
              {/* Chat panel */}
              <div
                className="flex-shrink-0 border-r border-[var(--border-subtle)]"
                style={{ width: `${panelSize}%` }}
              >
                <ChatPanel />
              </div>

              {/* Resizer */}
              <div
                className="panel-resizer panel-resizer-v"
                onMouseDown={handleMouseDown}
              />

              {/* Graph + Terminal panel */}
              <div className="flex-1 flex flex-col min-w-0">
                <div className="flex-1 overflow-hidden">
                  <GraphPanel />
                </div>
                {isTerminalVisible && <TerminalPanel />}
              </div>
            </>
          )}

          {/* ══ PROJECT VIEW: File explorer + Code ════════════════════════ */}
          {viewMode === 'project' && (
            <div className="flex-1 flex flex-col">
              <div className="flex-1 overflow-hidden">
                <ProjectPanel />
              </div>
              {isTerminalVisible && <TerminalPanel />}
            </div>
          )}

          {/* ══ DOCS VIEW: Document viewer ═════════════════════════════════ */}
          {viewMode === 'docs' && (
            <div className="flex-1 flex flex-col">
              <div className="flex-1 overflow-hidden">
                <ProjectPanel />
              </div>
              {isTerminalVisible && <TerminalPanel />}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

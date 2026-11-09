'use client';

import React, { useRef, useEffect } from 'react';
import { useTerminalStore } from '@/store/terminalStore';
import { Terminal, ChevronUp, ChevronDown } from 'lucide-react';

export function TerminalPanel() {
  const {
    sessions,
    activeSessionId,
    isVisible,
    switchSession,
    toggleVisible,
  } = useTerminalStore();

  const scrollRef = useRef<HTMLDivElement>(null);
  const activeSession = sessions.find((s) => s.id === activeSessionId);

  // Auto-scroll to bottom on new lines
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activeSession?.lines]);

  const getLineColor = (type: string) => {
    switch (type) {
      case 'command':
        return 'text-[var(--accent-hover)]';
      case 'stderr':
      case 'error':
        return 'text-[var(--state-error)]';
      case 'success':
        return 'text-[var(--state-completed)]';
      case 'info':
        return 'text-[var(--state-drafting)]';
      default:
        return 'text-[var(--text-secondary)]';
    }
  };

  return (
    <div className="flex flex-col bg-[var(--bg-primary)] border-t border-[var(--border-subtle)]">
      {/* ── Terminal Header ──────────────────────────────────────────────── */}
      <div className="panel-header cursor-pointer" onClick={toggleVisible}>
        <div className="flex items-center gap-2">
          <Terminal size={14} className="text-[var(--accent-primary)]" />
          <span>Terminal</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Session tabs */}
          {sessions.map((session) => (
            <button
              key={session.id}
              onClick={(e) => {
                e.stopPropagation();
                switchSession(session.id);
              }}
              className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] transition-colors ${
                activeSessionId === session.id
                  ? 'bg-[var(--accent-primary-glow)] text-[var(--accent-hover)]'
                  : 'text-[var(--text-dim)] hover:text-[var(--text-secondary)]'
              }`}
            >
              {session.agentAvatar && <span>{session.agentAvatar}</span>}
              {session.label}
            </button>
          ))}
          {/* Toggle */}
          <button className="p-0.5 hover:bg-[var(--bg-hover)] rounded">
            {isVisible ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>
        </div>
      </div>

      {/* ── Terminal Content ─────────────────────────────────────────────── */}
      {isVisible && (
        <div
          ref={scrollRef}
          className="h-48 overflow-y-auto px-3 py-2 font-mono text-xs leading-5 bg-[var(--bg-void)]"
        >
          {activeSession ? (
            activeSession.lines.length === 0 ? (
              <div className="text-[var(--text-dim)] flex items-center gap-2">
                <span className="animate-pulse">▋</span>
                Waiting for output...
              </div>
            ) : (
              activeSession.lines.map((line) => (
                <div key={line.id} className={`${getLineColor(line.type)} animate-fade-in`}>
                  {line.type === 'command' ? (
                    <span>
                      <span className="text-[var(--state-completed)]">❯</span> {line.content}
                    </span>
                  ) : (
                    line.content || '\u00A0'
                  )}
                </div>
              ))
            )
          ) : (
            <div className="text-[var(--text-dim)]">No terminal session active</div>
          )}
        </div>
      )}
    </div>
  );
}

'use client';

import React from 'react';
import { AgentState, AGENT_STATE_DISPLAY } from '@/types/agent';

interface AgentStateIndicatorProps {
  state: AgentState;
  nodeName?: string | null;
  compact?: boolean;
}

export function AgentStateIndicator({ state, nodeName, compact = false }: AgentStateIndicatorProps) {
  const display = AGENT_STATE_DISPLAY[state];
  if (!display || state === 'idle') return null;

  const bgColors: Record<AgentState, string> = {
    idle: '',
    thinking: 'bg-[var(--state-thinking-bg)] border-[var(--state-thinking)]/20',
    drafting: 'bg-[var(--state-drafting-bg)] border-[var(--state-drafting)]/20',
    reviewing: 'bg-[var(--state-reviewing-bg)] border-[var(--state-reviewing)]/20',
    awaiting_approval: 'bg-[var(--state-approval-bg)] border-[var(--state-approval)]/20',
    executing: 'bg-[var(--state-executing-bg)] border-[var(--state-executing)]/20',
    completed: 'bg-[var(--state-completed-bg)] border-[var(--state-completed)]/20',
    error: 'bg-[var(--state-error-bg)] border-[var(--state-error)]/20',
  };

  if (compact) {
    return (
      <span className={`agent-state-chip ${bgColors[state]} border ${display.cssClass}`}>
        <span className="animate-breathe">{display.icon}</span>
        <span>{display.label}</span>
      </span>
    );
  }

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${bgColors[state]} animate-slide-in-up`}
    >
      <span className="text-base animate-breathe">{display.icon}</span>
      <div className="flex flex-col">
        <span className={`text-xs font-medium ${display.cssClass}`}>
          {display.label}
          {state === 'thinking' && <span className="ml-0.5 animate-pulse">...</span>}
        </span>
        {nodeName && (
          <span className="text-[10px] text-[var(--text-dim)] font-mono">
            → {nodeName}
          </span>
        )}
      </div>
    </div>
  );
}

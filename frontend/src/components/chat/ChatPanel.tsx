'use client';

import React, { useRef, useEffect } from 'react';
import { useChatStore } from '@/store/chatStore';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { AgentStateIndicator } from './AgentStateIndicator';
import { AGENT_DISPLAY } from '@/types/agent';
import { MessageSquare, Wifi, WifiOff } from 'lucide-react';

export function ChatPanel() {
  const {
    messages,
    activeAgent,
    activeAgentState,
    activeAgentNode,
    isConnected,
  } = useChatStore();

  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, activeAgentState]);

  const activeAgentDisplay = activeAgent ? AGENT_DISPLAY[activeAgent] : null;

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      {/* ── Panel Header ─────────────────────────────────────────────────── */}
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <MessageSquare size={14} className="text-[var(--accent-primary)]" />
          <span>Agent Chat</span>
        </div>
        <div className="flex items-center gap-3">
          {/* Active agent indicator */}
          {activeAgent && activeAgentDisplay && (
            <div className="flex items-center gap-1.5 text-[10px]">
              <span>{activeAgentDisplay.avatar}</span>
              <span className="text-[var(--text-secondary)]">{activeAgentDisplay.name}</span>
            </div>
          )}
          {/* Connection indicator */}
          <div className="flex items-center gap-1">
            {isConnected ? (
              <Wifi size={12} className="text-[var(--state-completed)]" />
            ) : (
              <WifiOff size={12} className="text-[var(--state-error)]" />
            )}
          </div>
        </div>
      </div>

      {/* ── Agent State Banner ───────────────────────────────────────────── */}
      {activeAgent && activeAgentState && activeAgentState !== 'idle' && activeAgentState !== 'completed' && (
        <div className="px-3 py-2 border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
          <AgentStateIndicator
            state={activeAgentState}
            nodeName={activeAgentNode}
          />
        </div>
      )}

      {/* ── Messages Area ────────────────────────────────────────────────── */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto py-4 space-y-1"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-[var(--text-dim)]">
            <MessageSquare size={32} className="mb-3 opacity-30" />
            <p className="text-sm">Waiting for pipeline to start...</p>
            <p className="text-xs mt-1">Messages will appear here as agents work</p>
          </div>
        ) : (
          messages.map((msg) => <ChatMessage key={msg.id} message={msg} />)
        )}
      </div>

      {/* ── Input Area ───────────────────────────────────────────────────── */}
      <ChatInput />
    </div>
  );
}

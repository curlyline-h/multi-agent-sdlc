'use client';

import React from 'react';
import { ChatMessage as ChatMessageType } from '@/types/chat';
import { AGENT_DISPLAY } from '@/types/agent';
import { ApprovalCard } from './ApprovalCard';
import { useStreamingText } from '@/hooks/useStreamingText';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isAgent = message.role === 'agent';

  const agentDisplay = message.agentRole ? AGENT_DISPLAY[message.agentRole] : null;

  const { displayedText, isComplete } = useStreamingText({
    text: message.content,
    speed: 12,
    enabled: message.isStreaming === true,
  });

  const content = message.isStreaming ? displayedText : message.content;

  // ── System message ───────────────────────────────────────────────────
  if (isSystem) {
    return (
      <div className="flex justify-center px-4 py-2 animate-fade-in">
        <div className="chat-message-system px-4 py-2 max-w-lg text-center">
          <span className="text-xs">{content}</span>
        </div>
      </div>
    );
  }

  // ── User message ─────────────────────────────────────────────────────
  if (isUser) {
    return (
      <div className="flex justify-end px-4 py-1.5 animate-slide-in-right">
        <div className="chat-message-user px-4 py-2.5 max-w-md">
          <p className="text-sm leading-relaxed">{content}</p>
        </div>
      </div>
    );
  }

  // ── Agent message ────────────────────────────────────────────────────
  return (
    <div className="flex items-start gap-3 px-4 py-2 animate-slide-in-up">
      {/* Agent avatar */}
      <div
        className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-sm"
        style={{
          background: agentDisplay ? `color-mix(in srgb, ${agentDisplay.color} 15%, transparent)` : 'var(--bg-surface)',
          border: `1px solid color-mix(in srgb, ${agentDisplay?.color || 'var(--border-default)'} 30%, transparent)`,
        }}
      >
        {agentDisplay?.avatar || '🤖'}
      </div>

      {/* Message content */}
      <div className="flex-1 min-w-0">
        {/* Agent name + role */}
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            {message.agentName || agentDisplay?.name || 'Agent'}
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-surface)] text-[var(--text-dim)] font-mono">
            {message.agentRole}
          </span>
        </div>

        {/* Message body */}
        <div className="chat-message-agent px-4 py-3">
          <div className="markdown-content text-sm leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
          </div>

          {/* Streaming cursor */}
          {message.isStreaming && !isComplete && (
            <span className="streaming-cursor" />
          )}

          {/* Approval card */}
          {message.approval && <ApprovalCard approval={message.approval} />}
        </div>
      </div>
    </div>
  );
}

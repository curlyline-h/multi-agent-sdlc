'use client';

import React, { useRef, useEffect, useState } from 'react';
import { useChatStore } from '@/store/chatStore';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { AgentStateIndicator } from './AgentStateIndicator';
import { AGENT_DISPLAY } from '@/types/agent';
import { respondToApproval } from '@/lib/api';
import { MessageSquare, Wifi, WifiOff, CheckCircle2, XCircle } from 'lucide-react';

export function ChatPanel() {
  const {
    messages,
    activeAgent,
    activeAgentState,
    activeAgentNode,
    pendingApproval,
    submitApproval,
    isConnected,
  } = useChatStore();

  const [feedback, setFeedback] = useState('');
  const [showFeedback, setShowFeedback] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages or pending approval
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, activeAgentState, pendingApproval]);

  // Reset feedback UI when pendingApproval changes
  useEffect(() => {
    setFeedback('');
    setShowFeedback(false);
    setIsSubmitting(false);
  }, [pendingApproval?.id]);

  const isQuestionApproval =
    pendingApproval?.type === 'clarifying_questions' ||
    pendingApproval?.type === 'question';
  const showBottomApprovalBar =
    Boolean(pendingApproval) &&
    pendingApproval?.status === 'pending' &&
    !isQuestionApproval;

  const handleApprove = async () => {
    if (!pendingApproval || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await respondToApproval(pendingApproval.id, '');
      submitApproval(pendingApproval.id, true);
    } catch (err) {
      console.error('Failed to send approval:', err);
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!pendingApproval || isSubmitting) return;
    if (!showFeedback) {
      setShowFeedback(true);
      return;
    }
    setIsSubmitting(true);
    try {
      await respondToApproval(pendingApproval.id, feedback);
      submitApproval(pendingApproval.id, false, feedback);
    } catch (err) {
      console.error('Failed to send feedback:', err);
      setIsSubmitting(false);
    }
  };

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

      {/* ── Pending Approval Bar (always docked at the end of chat) ──────── */}
      {showBottomApprovalBar && pendingApproval && (
        <div className="px-3 py-2.5 border-t border-[var(--state-approval)]/30 bg-[var(--bg-secondary)] animate-slide-in-up">
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-xs font-semibold text-[var(--state-approval)] truncate">
              {pendingApproval.title || 'Approval Required'}
            </span>
            <span className="text-[10px] text-[var(--text-muted)]">Action required</span>
          </div>

          {showFeedback && (
            <div className="mb-2">
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Describe the changes you'd like..."
                className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-dim)] resize-none focus:outline-none focus:border-[var(--accent-primary)] transition-colors"
                rows={2}
                autoFocus
              />
            </div>
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={handleApprove}
              disabled={isSubmitting}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-[var(--state-completed)] hover:bg-[var(--state-completed)]/90 disabled:opacity-50 text-white text-xs font-medium rounded-lg transition-all"
            >
              <CheckCircle2 size={14} />
              Approve
            </button>
            <button
              onClick={handleReject}
              disabled={isSubmitting}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--bg-surface)] hover:bg-[var(--bg-hover)] disabled:opacity-50 text-[var(--state-approval)] text-xs font-medium rounded-lg border border-[var(--state-approval)]/30 transition-all"
            >
              <XCircle size={14} />
              {showFeedback ? 'Submit Feedback' : 'Request Changes'}
            </button>
          </div>
        </div>
      )}

      {/* ── Input Area ───────────────────────────────────────────────────── */}
      <ChatInput />
    </div>
  );
}

'use client';

import React, { useState, useRef, useCallback } from 'react';
import { Send } from 'lucide-react';
import { useChatStore } from '@/store/chatStore';
import { createProject, respondToApproval, resumeProject } from '@/lib/api';
import { connectRealWorkflow } from '@/lib/realWorkflow';

export function ChatInput() {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { addMessage, pendingApproval, submitApproval } = useChatStore();

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed) return;

    addMessage({
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    });

    setInput('');

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    const activeProjectId = typeof window !== 'undefined' ? localStorage.getItem('activeProjectId') : null;

    if (pendingApproval) {
      try {
        await respondToApproval(pendingApproval.id, trimmed);
        submitApproval(pendingApproval.id, true, trimmed);
      } catch (err) {
        console.error('Failed to send approval response:', err);
      }
    } else if (activeProjectId) {
      try {
        await resumeProject(activeProjectId);
      } catch (err: any) {
        if (err.message && err.message.includes('409')) {
          console.warn('Caught 409: Auto-resolving missing pending approval state...');
          try {
            const { getProjectApprovals } = await import('@/lib/api');
            const approvals = await getProjectApprovals(activeProjectId);
            const pending = approvals.find((a: any) => a.status === 'PENDING');
            if (pending) {
              await respondToApproval(String(pending.id), trimmed);
              submitApproval(String(pending.id), true, trimmed);
            } else {
              console.error('No pending approval found despite 409 error');
            }
          } catch (fallbackErr) {
            console.error('Failed to fallback resolve approval:', fallbackErr);
          }
        } else {
          console.warn('Could not resume project:', err.message || err);
        }
      }
    } else {
      try {
        const proj = await createProject(`SDLC Project ${new Date().toLocaleTimeString()}`, trimmed);
        if (proj && proj.id) {
          connectRealWorkflow(String(proj.id));
        }
      } catch (err) {
        console.error('Failed to trigger orchestrator project:', err);
      }
    }
  }, [input, addMessage, pendingApproval]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    // Auto-resize
    const textarea = e.target;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
  };

  return (
    <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={
            pendingApproval
              ? 'Type your feedback or approve above...'
              : 'Type a message...'
          }
          rows={1}
          className="flex-1 bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-dim)] resize-none focus:outline-none focus:border-[var(--accent-primary)] transition-colors max-h-[120px]"
          style={{ fontFamily: 'var(--font-sans)' }}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim()}
          className="flex items-center justify-center w-9 h-9 rounded-lg bg-[var(--accent-primary)] hover:bg-[var(--accent-hover)] disabled:opacity-30 disabled:cursor-not-allowed text-white transition-all hover:shadow-lg hover:shadow-[var(--accent-primary)]/20"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}

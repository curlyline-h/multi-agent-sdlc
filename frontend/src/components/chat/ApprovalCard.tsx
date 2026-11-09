'use client';

import React, { useState } from 'react';
import { ApprovalRequest } from '@/types/chat';
import { useChatStore } from '@/store/chatStore';
import { respondToApproval } from '@/lib/api';
import { CheckCircle2, XCircle, MessageSquare, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ApprovalCardProps {
  approval: ApprovalRequest;
}

export function ApprovalCard({ approval }: ApprovalCardProps) {
  const [feedback, setFeedback] = useState('');
  const [showFeedback, setShowFeedback] = useState(false);
  const { submitApproval } = useChatStore();

  const isResolved = approval.status !== 'pending';

  const handleApprove = async () => {
    try {
      await respondToApproval(approval.id, '');
      submitApproval(approval.id, true);
    } catch (err) {
      console.error('Failed to send approval:', err);
    }
  };

  const handleReject = async () => {
    if (!showFeedback) {
      setShowFeedback(true);
      return;
    }
    try {
      await respondToApproval(approval.id, feedback);
      submitApproval(approval.id, false, feedback);
    } catch (err) {
      console.error('Failed to send feedback:', err);
    }
  };

  const typeIcons: Record<string, React.ReactNode> = {
    prd: <FileText size={16} />,
    design: <FileText size={16} />,
    general: <MessageSquare size={16} />,
  };

  const isQuestionType = approval.type === 'clarifying_questions' || approval.type === 'question';
  const displayTitle = isQuestionType
    ? 'Clarification Requested'
    : (approval.title || 'Approval Required');

  return (
    <div className={`approval-card mt-3 animate-slide-in-up ${isResolved ? 'opacity-70' : ''}`}>
      {/* Header */}
      <div className="approval-card-header flex items-center gap-2">
        <span className="text-[var(--state-approval)]">
          {typeIcons[approval.type] || <MessageSquare size={16} />}
        </span>
        <span className="text-sm font-semibold text-[var(--text-primary)]">
          {displayTitle}
        </span>
        {isResolved && (
          <span className={`ml-auto text-xs font-medium ${
            approval.status === 'approved' ? 'text-[var(--state-completed)]' : 'text-[var(--state-error)]'
          }`}>
            {approval.status === 'approved' ? '✅ Answered' : '❌ Changes Requested'}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="p-4">
        {approval.message && !isQuestionType && (
          <div className="text-sm text-[var(--text-secondary)] mb-3 prose prose-sm prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {approval.message}
            </ReactMarkdown>
          </div>
        )}

        {approval.questions && approval.questions.length > 0 && (
          <div className="mb-3">
            <p className="text-xs text-[var(--text-muted)] font-medium mb-1 uppercase tracking-wider">
              {isQuestionType ? 'Agent Message / Questions' : 'Questions'}
            </p>
            <div className="space-y-3 mt-2">
              {approval.questions.map((q, i) => (
                <div key={i} className="text-sm text-[var(--text-secondary)] prose prose-sm prose-invert max-w-none bg-[var(--bg-secondary)]/30 rounded-md p-3 border border-[var(--border-subtle)]/50">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{q}</ReactMarkdown>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Feedback textarea */}
        {showFeedback && !isResolved && (
          <div className="mb-3 animate-slide-in-up">
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Describe the changes you'd like..."
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-dim)] resize-none focus:outline-none focus:border-[var(--accent-primary)] transition-colors"
              rows={3}
              autoFocus
            />
          </div>
        )}

        {/* Action buttons */}
        {!isResolved && (
          isQuestionType ? (
            <div className="p-2 bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-subtle)]">
              <p className="text-xs text-[var(--text-muted)] italic flex items-center gap-1.5">
                <span>💬</span>
                <span>Type your response or project requirements in the chat box below to reply.</span>
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={handleApprove}
                className="flex items-center gap-1.5 px-4 py-2 bg-[var(--state-completed)] hover:bg-[var(--state-completed)]/90 text-white text-sm font-medium rounded-lg transition-all hover:shadow-lg hover:shadow-[var(--state-completed)]/20"
              >
                <CheckCircle2 size={14} />
                Approve
              </button>
              <button
                onClick={handleReject}
                className="flex items-center gap-1.5 px-4 py-2 bg-[var(--bg-surface)] hover:bg-[var(--bg-hover)] text-[var(--state-approval)] text-sm font-medium rounded-lg border border-[var(--state-approval)]/30 transition-all"
              >
                <XCircle size={14} />
                {showFeedback ? 'Submit Feedback' : 'Request Changes'}
              </button>
            </div>
          )
        )}

        {/* Show submitted feedback */}
        {isResolved && approval.feedback && (
          <div className="mt-2 p-2 bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-subtle)]">
            <p className="text-xs text-[var(--text-muted)] font-medium mb-1">
              {isQuestionType ? 'Answer:' : 'Feedback:'}
            </p>
            <p className="text-sm text-[var(--text-secondary)]">{approval.feedback}</p>
          </div>
        )}
      </div>
    </div>
  );
}

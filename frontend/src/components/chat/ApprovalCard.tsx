'use client';

import React from 'react';
import { ApprovalRequest } from '@/types/chat';
import { MessageSquare, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ApprovalCardProps {
  approval: ApprovalRequest;
}

export function ApprovalCard({ approval }: ApprovalCardProps) {
  const isResolved = approval.status !== 'pending';

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

        {/* Action hint (Approve / Request Changes buttons are docked at the end of chat) */}
        {!isResolved && (
          isQuestionType ? (
            <div className="p-2 bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-subtle)]">
              <p className="text-xs text-[var(--text-muted)] italic flex items-center gap-1.5">
                <span>💬</span>
                <span>Type your response or project requirements in the chat box below to reply.</span>
              </p>
            </div>
          ) : (
            <div className="p-2 bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-subtle)]">
              <p className="text-xs text-[var(--text-muted)] italic">
                Use the Approve / Request Changes buttons at the bottom of the chat to respond.
              </p>
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

'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ProjectDocument } from '@/types/project';
import { FileText, CheckCircle2, Clock, AlertCircle } from 'lucide-react';

interface DocumentViewerProps {
  document: ProjectDocument;
}

export function DocumentViewer({ document }: DocumentViewerProps) {
  const statusConfig = {
    draft: { icon: <Clock size={12} />, label: 'Draft', color: 'text-[var(--state-drafting)]', bg: 'bg-[var(--state-drafting-bg)]' },
    review: { icon: <AlertCircle size={12} />, label: 'In Review', color: 'text-[var(--state-approval)]', bg: 'bg-[var(--state-approval-bg)]' },
    approved: { icon: <CheckCircle2 size={12} />, label: 'Approved', color: 'text-[var(--state-completed)]', bg: 'bg-[var(--state-completed-bg)]' },
    rejected: { icon: <AlertCircle size={12} />, label: 'Changes Requested', color: 'text-[var(--state-error)]', bg: 'bg-[var(--state-error-bg)]' },
  };

  const status = statusConfig[document.status];

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 bg-[var(--bg-secondary)] border-b border-[var(--border-subtle)]">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-[var(--accent-primary)]" />
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              {document.title}
            </h2>
          </div>
          <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${status.color} ${status.bg}`}>
            {status.icon}
            {status.label}
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-[var(--text-dim)]">
          <span className="font-mono uppercase">{document.type.replace('_', ' ')}</span>
          {document.agentRole && <span>by {document.agentRole}</span>}
          <span>{new Date(document.updatedAt).toLocaleDateString()}</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="markdown-content max-w-3xl mx-auto">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {document.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

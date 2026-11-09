import { AgentRole, AgentState } from './agent';

// ── Chat Message Types ───────────────────────────────────────────────────

export type MessageRole = 'user' | 'agent' | 'system';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  agentRole?: AgentRole;
  agentName?: string;
  agentState?: AgentState;
  timestamp: number;
  isStreaming?: boolean;
  streamedContent?: string; // Partially streamed content
  approval?: ApprovalRequest;
}

// ── Approval Types ───────────────────────────────────────────────────────

export type ApprovalType = 'prd' | 'clarification' | 'clarifying_questions' | 'question' | 'design' | 'schema' | 'api' | 'directory' | 'deployment' | 'general';

export interface ApprovalRequest {
  id: string;
  type: ApprovalType;
  title: string;
  message?: string;
  questions?: string[];
  draft?: string; // The document content to review
  section?: string; // Which section/aspect to review
  status: 'pending' | 'approved' | 'rejected';
  feedback?: string;
}

// ── Streaming Types ──────────────────────────────────────────────────────

export interface StreamingChunk {
  messageId: string;
  token: string;
  done: boolean;
}

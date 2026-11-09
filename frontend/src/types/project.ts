export interface Project {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  status: 'idle' | 'running' | 'completed' | 'failed';
}

// ── File System Types ────────────────────────────────────────────────────

export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  language?: string;
  content?: string;
  children?: FileNode[];
  isModified?: boolean;
  additions?: number;
  deletions?: number;
}

// ── Diff Types ───────────────────────────────────────────────────────────

export interface FileDiff {
  path: string;
  oldContent: string;
  newContent: string;
  additions: number;
  deletions: number;
  status: 'added' | 'modified' | 'deleted';
}

// ── Document Types (PRD, Design Docs, Implementation Plans) ──────────────

export type DocumentType = 'prd' | 'design' | 'implementation_plan' | 'task_breakdown' | 'security_report' | 'review';

export interface ProjectDocument {
  id: string;
  title: string;
  type: DocumentType;
  content: string; // Markdown content
  status: 'draft' | 'review' | 'approved' | 'rejected';
  agentRole?: string;
  updatedAt: string;
}

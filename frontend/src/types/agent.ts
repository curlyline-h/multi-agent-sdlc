// ── Agent State represents what the agent is currently doing ──────────────
export type AgentState =
  | 'idle'
  | 'thinking'
  | 'drafting'
  | 'reviewing'
  | 'awaiting_approval'
  | 'executing'
  | 'completed'
  | 'error';

// ── Agent roles matching the orchestrator graph ──────────────────────────
export type AgentRole =
  | 'planner'
  | 'product_manager'
  | 'architect'
  | 'task_breakdown'
  | 'database_engineer'
  | 'backend_dev'
  | 'frontend_dev'
  | 'qa'
  | 'reviewer'
  | 'security'
  | 'devops'
  | 'dispatcher';

export interface AgentMetric {
  runsCount: number;
  successRate: number;
  avgLatencyMs: number;
  tokensUsed: number;
}

export interface Agent {
  id: string;
  name: string;
  role: AgentRole;
  status: AgentState;
  avatar: string; // emoji or icon identifier
  color: string; // CSS variable name for accent color
  currentNode?: string; // Current subgraph node being executed
  metrics: AgentMetric;
}

// ── Agent metadata for display ───────────────────────────────────────────
export const AGENT_DISPLAY: Record<AgentRole, { name: string; avatar: string; color: string }> = {
  planner: { name: 'Planning Agent', avatar: '📋', color: 'var(--node-planning)' },
  product_manager: { name: 'Product Manager', avatar: '📊', color: 'var(--node-pm)' },
  architect: { name: 'Architect Agent', avatar: '🏗️', color: 'var(--node-architect)' },
  task_breakdown: { name: 'Task Breakdown', avatar: '📦', color: 'var(--node-task)' },
  database_engineer: { name: 'Database Engineer', avatar: '🗃️', color: 'var(--node-dev)' },
  backend_dev: { name: 'Backend Developer', avatar: '⚙️', color: 'var(--node-dev)' },
  frontend_dev: { name: 'Frontend Developer', avatar: '🎨', color: 'var(--node-dev)' },
  qa: { name: 'QA Agent', avatar: '🧪', color: 'var(--node-qa)' },
  reviewer: { name: 'Code Reviewer', avatar: '🔍', color: 'var(--node-reviewer)' },
  security: { name: 'Security Agent', avatar: '🛡️', color: 'var(--node-security)' },
  devops: { name: 'DevOps Agent', avatar: '🚀', color: 'var(--node-devops)' },
  dispatcher: { name: 'Dispatcher', avatar: '📡', color: 'var(--node-dispatcher)' },
};

// ── Agent state display metadata ─────────────────────────────────────────
export const AGENT_STATE_DISPLAY: Record<AgentState, { label: string; icon: string; cssClass: string }> = {
  idle: { label: 'Idle', icon: '⏸️', cssClass: 'text-[var(--text-dim)]' },
  thinking: { label: 'Thinking', icon: '🧠', cssClass: 'text-[var(--state-thinking)]' },
  drafting: { label: 'Drafting', icon: '📝', cssClass: 'text-[var(--state-drafting)]' },
  reviewing: { label: 'Reviewing', icon: '🔍', cssClass: 'text-[var(--state-reviewing)]' },
  awaiting_approval: { label: 'Awaiting Approval', icon: '⏳', cssClass: 'text-[var(--state-approval)]' },
  executing: { label: 'Executing', icon: '⚡', cssClass: 'text-[var(--state-executing)]' },
  completed: { label: 'Completed', icon: '✅', cssClass: 'text-[var(--state-completed)]' },
  error: { label: 'Error', icon: '❌', cssClass: 'text-[var(--state-error)]' },
};

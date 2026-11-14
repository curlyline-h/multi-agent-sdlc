import { WorkflowEdge, WorkflowNode } from '@/types/workflow';

export const PIPELINE_PHASES = [
  'planning_stage',
  'pm_phase_a_stage',
  'architect_stage',
  'task_breakdown_stage',
  'pm_phase_b_stage',
  'dispatcher_stage',
  'database_engineer_stage',
  'backend_dev_stage',
  'frontend_dev_stage',
  'qa_stage',
  'reviewer_stage',
  'security_stage',
  'devops_stage',
] as const;

export const PARENT_GRAPH_NODES: WorkflowNode[] = [
  { id: 'planning_stage', label: 'Planning', status: 'pending', agentType: 'planner', position: { x: 50, y: 80 } },
  { id: 'pm_phase_a_stage', label: 'PM (PRD)', status: 'pending', agentType: 'product_manager', position: { x: 250, y: 80 } },
  { id: 'architect_stage', label: 'Architect', status: 'pending', agentType: 'architect', position: { x: 450, y: 80 } },
  { id: 'task_breakdown_stage', label: 'Task Breakdown', status: 'pending', agentType: 'task_breakdown', position: { x: 650, y: 80 } },
  { id: 'pm_phase_b_stage', label: 'PM (Jira/Slack)', status: 'pending', agentType: 'product_manager', position: { x: 850, y: 80 } },
  { id: 'dispatcher_stage', label: 'Dispatcher', status: 'pending', agentType: 'orchestrator', position: { x: 450, y: 220 } },
  { id: 'database_engineer_stage', label: 'Database', status: 'pending', agentType: 'database_engineer', position: { x: 100, y: 360 } },
  { id: 'backend_dev_stage', label: 'Backend Dev', status: 'pending', agentType: 'backend_dev', position: { x: 300, y: 360 } },
  { id: 'frontend_dev_stage', label: 'Frontend Dev', status: 'pending', agentType: 'frontend_dev', position: { x: 500, y: 360 } },
  { id: 'qa_stage', label: 'QA Testing', status: 'pending', agentType: 'qa', position: { x: 700, y: 360 } },
  { id: 'reviewer_stage', label: 'Code Review', status: 'pending', agentType: 'reviewer', position: { x: 200, y: 490 } },
  { id: 'security_stage', label: 'Security', status: 'pending', agentType: 'security', position: { x: 450, y: 490 } },
  { id: 'devops_stage', label: 'DevOps', status: 'pending', agentType: 'devops', position: { x: 700, y: 490 } },
];

export const PARENT_GRAPH_EDGES: WorkflowEdge[] = [
  { id: 'e1', from: 'planning_stage', to: 'pm_phase_a_stage' },
  { id: 'e2', from: 'pm_phase_a_stage', to: 'architect_stage' },
  { id: 'e3', from: 'architect_stage', to: 'task_breakdown_stage' },
  { id: 'e4', from: 'task_breakdown_stage', to: 'pm_phase_b_stage' },
  { id: 'e5', from: 'pm_phase_b_stage', to: 'dispatcher_stage' },
  { id: 'e6', from: 'dispatcher_stage', to: 'database_engineer_stage' },
  { id: 'e7', from: 'dispatcher_stage', to: 'backend_dev_stage' },
  { id: 'e8', from: 'dispatcher_stage', to: 'frontend_dev_stage' },
  { id: 'e9', from: 'dispatcher_stage', to: 'qa_stage' },
  { id: 'e10', from: 'dispatcher_stage', to: 'reviewer_stage' },
  { id: 'e11', from: 'dispatcher_stage', to: 'security_stage' },
  { id: 'e12', from: 'dispatcher_stage', to: 'devops_stage' },
];

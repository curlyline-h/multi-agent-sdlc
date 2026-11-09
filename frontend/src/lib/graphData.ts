import { WorkflowNode, WorkflowEdge } from '@/types/workflow';

export const PIPELINE_PHASES = [
  'Requirements & Planning',
  'Architecture & Design',
  'Task Breakdown',
  'Implementation',
  'Review & Testing',
  'Deployment'
];

export const PARENT_GRAPH_NODES: WorkflowNode[] = [
  { id: 'planning_stage', label: 'Planning Agent', status: 'pending', agentType: 'planning', position: { x: 50, y: 150 }, nodeColor: '#6366f1' },
  { id: 'pm_phase_a_stage', label: 'Product Manager', status: 'pending', agentType: 'pm', position: { x: 260, y: 150 }, nodeColor: '#8b5cf6' },
  { id: 'architect_stage', label: 'System Architect', status: 'pending', agentType: 'architect', position: { x: 470, y: 150 }, nodeColor: '#ec4899' },
  { id: 'task_breakdown_stage', label: 'Task Breakdown', status: 'pending', agentType: 'task_breakdown', position: { x: 680, y: 150 }, nodeColor: '#3b82f6' },
  { id: 'dispatcher_stage', label: 'Dispatcher Hub', status: 'pending', agentType: 'dispatcher', position: { x: 890, y: 150 }, nodeColor: '#06b6d4' },
  { id: 'backend_dev_stage', label: 'Backend Dev', status: 'pending', agentType: 'backend_dev', position: { x: 1100, y: 50 }, nodeColor: '#10b981' },
  { id: 'frontend_dev_stage', label: 'Frontend Dev', status: 'pending', agentType: 'frontend_dev', position: { x: 1100, y: 150 }, nodeColor: '#14b8a6' },
  { id: 'database_engineer_stage', label: 'Database Engineer', status: 'pending', agentType: 'database_engineer', position: { x: 1100, y: 250 }, nodeColor: '#f59e0b' },
  { id: 'reviewer_stage', label: 'Code Reviewer', status: 'pending', agentType: 'reviewer', position: { x: 1320, y: 80 }, nodeColor: '#a855f7' },
  { id: 'security_stage', label: 'Security Agent', status: 'pending', agentType: 'security', position: { x: 1320, y: 220 }, nodeColor: '#ef4444' },
  { id: 'qa_stage', label: 'QA Engineer', status: 'pending', agentType: 'qa', position: { x: 1530, y: 150 }, nodeColor: '#84cc16' },
  { id: 'devops_stage', label: 'DevOps & Deploy', status: 'pending', agentType: 'devops', position: { x: 1740, y: 150 }, nodeColor: '#eab308' },
];

export const PARENT_GRAPH_EDGES: WorkflowEdge[] = [
  { id: 'e1', from: 'planning_stage', to: 'pm_phase_a_stage', animated: true },
  { id: 'e2', from: 'pm_phase_a_stage', to: 'architect_stage', animated: true },
  { id: 'e3', from: 'architect_stage', to: 'task_breakdown_stage', animated: true },
  { id: 'e4', from: 'task_breakdown_stage', to: 'dispatcher_stage', animated: true },
  { id: 'e5', from: 'dispatcher_stage', to: 'backend_dev_stage', animated: true },
  { id: 'e6', from: 'dispatcher_stage', to: 'frontend_dev_stage', animated: true },
  { id: 'e7', from: 'dispatcher_stage', to: 'database_engineer_stage', animated: true },
  { id: 'e8', from: 'backend_dev_stage', to: 'reviewer_stage', animated: true },
  { id: 'e9', from: 'frontend_dev_stage', to: 'reviewer_stage', animated: true },
  { id: 'e10', from: 'database_engineer_stage', to: 'security_stage', animated: true },
  { id: 'e11', from: 'reviewer_stage', to: 'qa_stage', animated: true },
  { id: 'e12', from: 'security_stage', to: 'qa_stage', animated: true },
  { id: 'e13', from: 'qa_stage', to: 'devops_stage', animated: true },
];

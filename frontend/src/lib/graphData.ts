import { SubgraphDefinition, WorkflowEdge, WorkflowNode } from '@/types/workflow';

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

interface SubgraphSpec {
  agentRole: string;
  label: string;
  steps: Array<{ id: string; label: string }>;
}

const SUBGRAPH_SPECS: Record<string, SubgraphSpec> = {
  planning_stage: {
    agentRole: 'planner',
    label: 'Planning Agent Subgraph',
    steps: [
      { id: 'clarification', label: 'Clarify' },
      { id: 'ask_clarification', label: 'Ask User' },
      { id: 'research', label: 'Research' },
      { id: 'generate_draft', label: 'Draft Plan' },
      { id: 'critique', label: 'Critique' },
      { id: 'user_approval', label: 'Approval' },
      { id: 'finalize', label: 'Finalize' },
    ],
  },
  pm_phase_a_stage: {
    agentRole: 'product_manager',
    label: 'PM (PRD) Subgraph',
    steps: [
      { id: 'research', label: 'Research' },
      { id: 'write_prd', label: 'Write PRD' },
      { id: 'user_approval', label: 'Approval' },
      { id: 'finalize_prd', label: 'Finalize PRD' },
    ],
  },
  architect_stage: {
    agentRole: 'architect',
    label: 'Architect Subgraph',
    steps: [
      { id: 'research', label: 'Research' },
      { id: 'design_draft', label: 'Design Draft' },
      { id: 'validate_design', label: 'Validate' },
      { id: 'self_critique', label: 'Critique' },
      { id: 'approve_schema', label: 'Schema Gate' },
      { id: 'approve_api', label: 'API Gate' },
      { id: 'approve_structure', label: 'Structure Gate' },
      { id: 'finalize_design', label: 'Finalize' },
    ],
  },
  task_breakdown_stage: {
    agentRole: 'task_breakdown',
    label: 'Task Breakdown Subgraph',
    steps: [
      { id: 'decompose_tasks', label: 'Decompose' },
      { id: 'validate_dag', label: 'Validate DAG' },
    ],
  },
  pm_phase_b_stage: {
    agentRole: 'product_manager',
    label: 'PM (Jira/Slack) Subgraph',
    steps: [
      { id: 'create_slack_channel', label: 'Slack Channel' },
      { id: 'create_jira_epic', label: 'Jira Epic' },
      { id: 'create_jira_tickets', label: 'Jira Tickets' },
      { id: 'notify_slack', label: 'Notify Slack' },
    ],
  },
  database_engineer_stage: {
    agentRole: 'database_engineer',
    label: 'Database Engineer Subgraph',
    steps: [
      { id: 'pop_task', label: 'Pop Task' },
      { id: 'setup_db', label: 'Setup DB' },
      { id: 'write_migrations', label: 'Migrations' },
      { id: 'execute_migrations', label: 'Execute' },
      { id: 'validate_schema', label: 'Validate' },
      { id: 'push_to_github', label: 'Push PR' },
      { id: 'mark_task_complete', label: 'Complete' },
    ],
  },
  backend_dev_stage: {
    agentRole: 'backend_dev',
    label: 'Backend Dev Subgraph',
    steps: [
      { id: 'pop_task', label: 'Pop Task' },
      { id: 'write_code', label: 'Write Code' },
      { id: 'lint_code', label: 'Build & Lint' },
      { id: 'run_tests', label: 'Unit Tests' },
      { id: 'mark_task_complete', label: 'Complete' },
      { id: 'push_to_github', label: 'Push PR' },
    ],
  },
  frontend_dev_stage: {
    agentRole: 'frontend_dev',
    label: 'Frontend Dev Subgraph',
    steps: [
      { id: 'pop_task', label: 'Pop Task' },
      { id: 'write_ui_code', label: 'Write UI' },
      { id: 'lint_code', label: 'Build & Lint' },
      { id: 'run_tests', label: 'Tests' },
      { id: 'browser_check', label: 'Browser Check' },
      { id: 'mark_task_complete', label: 'Complete' },
      { id: 'push_to_github', label: 'Push PR' },
    ],
  },
  qa_stage: {
    agentRole: 'qa',
    label: 'QA Testing Subgraph',
    steps: [
      { id: 'pop_task', label: 'Pop Task' },
      { id: 'generate_tests', label: 'Generate Tests' },
      { id: 'execute_tests', label: 'Execute Tests' },
      { id: 'analyze_failures', label: 'Analyze' },
      { id: 'mark_task_complete', label: 'Complete' },
    ],
  },
  reviewer_stage: {
    agentRole: 'reviewer',
    label: 'Code Reviewer Subgraph',
    steps: [
      { id: 'pop_task', label: 'Pop Task' },
      { id: 'analyze_complexity', label: 'Complexity' },
      { id: 'review_code', label: 'Review Code' },
      { id: 'submit_review', label: 'Submit Review' },
      { id: 'mark_task_complete', label: 'Complete' },
    ],
  },
  security_stage: {
    agentRole: 'security',
    label: 'Security Audit Subgraph',
    steps: [
      { id: 'pop_task', label: 'Pop Task' },
      { id: 'run_sast', label: 'SAST Scan' },
      { id: 'check_deps', label: 'Dep Audit' },
      { id: 'analyze_vulnerabilities', label: 'Analyze' },
      { id: 'enforce_security_gate', label: 'Security Gate' },
      { id: 'mark_task_complete', label: 'Complete' },
    ],
  },
  devops_stage: {
    agentRole: 'devops',
    label: 'DevOps Subgraph',
    steps: [
      { id: 'pop_task', label: 'Pop Task' },
      { id: 'generate_deployment_plan', label: 'IaC Plan' },
      { id: 'validate_plan', label: 'Validate IaC' },
      { id: 'approve_deployment', label: 'Approval' },
      { id: 'execute_deployment', label: 'Deploy' },
      { id: 'push_to_github', label: 'Push PR' },
      { id: 'verify_health', label: 'Health Check' },
      { id: 'mark_task_complete', label: 'Complete' },
    ],
  },
};

export function buildSubgraphDefinition(stageId: string): SubgraphDefinition | null {
  const spec = SUBGRAPH_SPECS[stageId];
  if (!spec) return null;
  const nodes: WorkflowNode[] = spec.steps.map((step, idx) => ({
    id: step.id,
    label: step.label,
    status: 'pending',
    agentType: spec.agentRole,
    position: { x: 40 + idx * 170, y: 80 },
  }));
  const edges: WorkflowEdge[] = spec.steps.slice(0, -1).map((step, idx) => ({
    id: `se-${stageId}-${idx}`,
    from: step.id,
    to: spec.steps[idx + 1].id,
  }));
  return {
    id: stageId,
    agentRole: spec.agentRole,
    label: spec.label,
    nodes,
    edges,
  };
}

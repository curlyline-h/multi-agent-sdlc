export type GraphNodeStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'interrupted';

export interface WorkflowNode {
  id: string;
  label: string;
  status: GraphNodeStatus;
  agentType: string;
  position?: { x: number; y: number };
  nodeColor?: string;
}

export interface WorkflowEdge {
  id: string;
  from: string;
  to: string;
  label?: string;
  animated?: boolean;
}

export interface SubgraphDefinition {
  id: string;
  agentRole: string;
  label: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

export interface Workflow {
  id: string;
  projectId: string;
  status: 'pending' | 'running' | 'awaiting_approval' | 'completed' | 'failed';
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  activeNodeId?: string;
  activeSubgraph?: SubgraphDefinition;
  activeSubgraphNodeId?: string;
  createdAt: string;
  currentPhase?: string;
  currentPhaseIndex?: number;
  totalPhases?: number;
}

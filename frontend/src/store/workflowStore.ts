'use client';

import { create } from 'zustand';
import { Workflow, SubgraphDefinition, GraphNodeStatus } from '@/types/workflow';

interface WorkflowState {
  workflows: Workflow[];
  currentWorkflow: Workflow | null;
  activeSubgraph: SubgraphDefinition | null;

  // Actions
  setWorkflows: (workflows: Workflow[]) => void;
  setCurrentWorkflow: (workflow: Workflow | null) => void;
  setActiveNode: (nodeId: string) => void;
  completeNode: (nodeId: string) => void;
  setNodeStatus: (nodeId: string, status: GraphNodeStatus) => void;
  setActiveSubgraph: (subgraph: SubgraphDefinition | null) => void;
  setSubgraphActiveNode: (nodeId: string) => void;
  completeSubgraphNode: (nodeId: string) => void;
  setSubgraphNodeStatus: (nodeId: string, status: GraphNodeStatus) => void;
  updatePhase: (phase: string, index: number, total: number) => void;
}

export const useWorkflowStore = create<WorkflowState>((set) => ({
  workflows: [],
  currentWorkflow: null,
  activeSubgraph: null,

  setWorkflows: (workflows) => set({ workflows }),
  setCurrentWorkflow: (currentWorkflow) => set({ currentWorkflow }),

  setActiveNode: (nodeId) =>
    set((state) => {
      if (!state.currentWorkflow) return {};
      return {
        currentWorkflow: {
          ...state.currentWorkflow,
          activeNodeId: nodeId,
          status: 'running',
          nodes: state.currentWorkflow.nodes.map((n) => {
            if (n.id === nodeId) return { ...n, status: 'running' as const };
            if (n.status === 'running') return { ...n, status: 'completed' as const };
            return n;
          }),
        },
      };
    }),

  completeNode: (nodeId) =>
    set((state) => {
      if (!state.currentWorkflow) return {};
      return {
        currentWorkflow: {
          ...state.currentWorkflow,
          nodes: state.currentWorkflow.nodes.map((n) =>
            n.id === nodeId ? { ...n, status: 'completed' as const } : n
          ),
        },
      };
    }),

  setNodeStatus: (nodeId, status) =>
    set((state) => {
      if (!state.currentWorkflow) return {};
      return {
        currentWorkflow: {
          ...state.currentWorkflow,
          nodes: state.currentWorkflow.nodes.map((n) =>
            n.id === nodeId ? { ...n, status } : n
          ),
        },
      };
    }),

  setActiveSubgraph: (subgraph) => set({ activeSubgraph: subgraph }),

  setSubgraphActiveNode: (nodeId) =>
    set((state) => {
      if (!state.activeSubgraph) return {};
      return {
        activeSubgraph: {
          ...state.activeSubgraph,
          nodes: state.activeSubgraph.nodes.map((n) => {
            if (n.id === nodeId) return { ...n, status: 'running' as const };
            if (n.status === 'running') return { ...n, status: 'completed' as const };
            return n;
          }),
        },
      };
    }),

  completeSubgraphNode: (nodeId) =>
    set((state) => {
      if (!state.activeSubgraph) return {};
      return {
        activeSubgraph: {
          ...state.activeSubgraph,
          nodes: state.activeSubgraph.nodes.map((n) =>
            n.id === nodeId ? { ...n, status: 'completed' as const } : n
          ),
        },
      };
    }),

  setSubgraphNodeStatus: (nodeId, status) =>
    set((state) => {
      if (!state.activeSubgraph) return {};
      return {
        activeSubgraph: {
          ...state.activeSubgraph,
          nodes: state.activeSubgraph.nodes.map((n) =>
            n.id === nodeId ? { ...n, status } : n
          ),
        },
      };
    }),

  updatePhase: (phase, index, total) =>
    set((state) => {
      if (!state.currentWorkflow) return {};
      return {
        currentWorkflow: {
          ...state.currentWorkflow,
          currentPhase: phase,
          currentPhaseIndex: index,
          totalPhases: total,
        },
      };
    }),
}));

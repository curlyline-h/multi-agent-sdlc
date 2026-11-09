'use client';

import React from 'react';
import { useWorkflowStore } from '@/store/workflowStore';
import { useChatStore } from '@/store/chatStore';
import { useProjectViewStore } from '@/store/projectViewStore';
import { AGENT_DISPLAY } from '@/types/agent';
import { AgentStateIndicator } from '@/components/chat/AgentStateIndicator';
import { PIPELINE_PHASES, PARENT_GRAPH_NODES, PARENT_GRAPH_EDGES } from '@/lib/graphData';
import { Workflow } from '@/types/workflow';
import { disconnectRealWorkflow } from '@/lib/realWorkflow';
import { Wifi, WifiOff, Activity, Plus } from 'lucide-react';

export function Header() {
  const { currentWorkflow, setCurrentWorkflow, setActiveSubgraph } = useWorkflowStore();
  const { activeAgent, activeAgentState, isConnected } = useChatStore();

  const agentDisplay = activeAgent ? AGENT_DISPLAY[activeAgent] : null;

  const handleNewProject = () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('activeProjectId');
    }

    // Disconnect previous websocket
    disconnectRealWorkflow();

    // Reset chat store
    useChatStore.getState().resetAll();

    // Reset workflow graph and subgraph
    const resetWorkflow: Workflow = {
      id: `wf-${Date.now()}`,
      projectId: 'new-project',
      status: 'pending',
      nodes: PARENT_GRAPH_NODES.map((n) => ({ ...n, status: 'pending' as const })),
      edges: [...PARENT_GRAPH_EDGES],
      createdAt: new Date().toISOString(),
      currentPhase: 'Requirements & Planning',
      currentPhaseIndex: 0,
      totalPhases: 6,
    };
    setCurrentWorkflow(resetWorkflow);
    setActiveSubgraph(null);

    // Reset project view (files, diffs, documents)
    useProjectViewStore.getState().setFileTree([]);
    useProjectViewStore.getState().setDiffs([]);
    useProjectViewStore.getState().setDocuments([]);
  };

  // Calculate pipeline progress
  const completedNodes = currentWorkflow?.nodes.filter((n) => n.status === 'completed').length || 0;
  const totalNodes = currentWorkflow?.nodes.length || PIPELINE_PHASES.length;
  const progress = totalNodes > 0 ? (completedNodes / totalNodes) * 100 : 0;

  return (
    <header className="h-[var(--header-height)] border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 flex items-center justify-between flex-shrink-0">
      {/* Left: Project info + Start New Project button */}
      <div className="flex items-center gap-4">
        <div>
          <h1 className="text-sm font-semibold text-[var(--text-primary)] leading-none">
            SDLC Orchestrator
          </h1>
          <p className="text-[10px] text-[var(--text-dim)] mt-0.5 font-mono">
            {currentWorkflow?.currentPhase || 'Initializing...'}
          </p>
        </div>

        <button
          onClick={handleNewProject}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--accent-primary)] hover:bg-[var(--accent-hover)] text-white text-xs font-medium rounded-lg shadow-sm transition-all hover:scale-105 active:scale-95 cursor-pointer ml-2"
          title="Start a new SDLC Project Workflow"
        >
          <Plus size={14} />
          <span>New Project</span>
        </button>
      </div>

      {/* Center: Pipeline progress */}
      <div className="flex items-center gap-3 flex-1 max-w-md mx-8">
        <Activity size={12} className="text-[var(--text-dim)]" />
        <div className="flex-1">
          <div className="h-1.5 bg-[var(--bg-hover)] rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-[var(--accent-primary)] to-[var(--state-completed)] rounded-full transition-all duration-1000 ease-out"
              style={{ width: `${Math.max(progress, 2)}%` }}
            />
          </div>
        </div>
        <span className="text-[10px] text-[var(--text-dim)] font-mono whitespace-nowrap">
          {completedNodes}/{totalNodes} nodes
        </span>
      </div>

      {/* Right: Active agent + connection */}
      <div className="flex items-center gap-3">
        {activeAgent && agentDisplay && activeAgentState && (
          <AgentStateIndicator state={activeAgentState} compact />
        )}

        {/* Connection status */}
        <div className="flex items-center gap-1.5 pl-3 border-l border-[var(--border-subtle)]">
          {isConnected ? (
            <>
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--state-completed)] opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--state-completed)]" />
              </span>
              <span className="text-[10px] text-[var(--text-dim)]">Connected</span>
            </>
          ) : (
            <>
              <WifiOff size={12} className="text-[var(--state-error)]" />
              <span className="text-[10px] text-[var(--state-error)]">Disconnected</span>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

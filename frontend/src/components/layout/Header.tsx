'use client';

import React, { useEffect, useState } from 'react';
import { useWorkflowStore } from '@/store/workflowStore';
import { useChatStore } from '@/store/chatStore';
import { useProjectViewStore } from '@/store/projectViewStore';
import { useTerminalStore } from '@/store/terminalStore';
import { AGENT_DISPLAY } from '@/types/agent';
import { AgentStateIndicator } from '@/components/chat/AgentStateIndicator';
import { PIPELINE_PHASES, PARENT_GRAPH_NODES, PARENT_GRAPH_EDGES } from '@/lib/graphData';
import { Workflow } from '@/types/workflow';
import { connectRealWorkflow, disconnectRealWorkflow } from '@/lib/realWorkflow';
import { listProjects, stopProject } from '@/lib/api';
import { Wifi, WifiOff, Activity, Plus, History, Square } from 'lucide-react';

export function Header() {
  const { currentWorkflow, setCurrentWorkflow, setActiveSubgraph } = useWorkflowStore();
  const { activeAgent, activeAgentState, isConnected } = useChatStore();
  const agentDisplay = activeAgent ? AGENT_DISPLAY[activeAgent] : null;
  const [sessions, setSessions] = useState<Array<{ id: number; title?: string; description?: string; current_status?: string }>>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>('');

  useEffect(() => {
    const refresh = () => {
      listProjects().then(setSessions).catch(() => {});
      if (typeof window !== 'undefined') {
        setSelectedSessionId(localStorage.getItem('activeProjectId') || '');
      }
    };
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, []);

  const resetWorkspaceUi = (phaseLabel = 'Ready for Prompt') => {
    disconnectRealWorkflow();
    useChatStore.getState().resetAll();
    const resetWorkflow: Workflow = {
      id: `wf-${Date.now()}`,
      projectId: 'new-project',
      status: 'pending',
      nodes: PARENT_GRAPH_NODES.map((n) => ({ ...n, status: 'pending' as const })),
      edges: [...PARENT_GRAPH_EDGES],
      createdAt: new Date().toISOString(),
      currentPhase: phaseLabel,
      currentPhaseIndex: 0,
      totalPhases: 6,
    };
    setCurrentWorkflow(resetWorkflow);
    setActiveSubgraph(null);
    useProjectViewStore.getState().setFileTree([]);
    useProjectViewStore.getState().setDiffs([]);
    useProjectViewStore.getState().setDocuments([]);
    useTerminalStore.getState().clearSession('agent-terminal');
  };

  const handleNewProject = () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('activeProjectId');
    }
    setSelectedSessionId('');
    resetWorkspaceUi('Ready for Prompt');
  };

  const handleSelectSession = (sessionId: string) => {
    if (!sessionId) {
      handleNewProject();
      return;
    }
    setSelectedSessionId(sessionId);
    resetWorkspaceUi('Loading Session...');
    connectRealWorkflow(sessionId);
  };

  const handleStopSession = async () => {
    const activeId = selectedSessionId || (typeof window !== 'undefined' ? localStorage.getItem('activeProjectId') : '') || '';
    if (activeId) {
      await stopProject(activeId).catch(() => {});
    }
    if (typeof window !== 'undefined') {
      localStorage.removeItem('activeProjectId');
    }
    setSelectedSessionId('');
    resetWorkspaceUi('Stopped (Closed)');
    listProjects().then(setSessions).catch(() => {});
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

        {(selectedSessionId || currentWorkflow?.status === 'running') && (
          <button
            onClick={handleStopSession}
            className="flex items-center gap-1.5 px-2.5 py-1.5 bg-red-600/90 hover:bg-red-500 text-white text-xs font-medium rounded-lg shadow-sm transition-all cursor-pointer"
            title="Stop active session"
          >
            <Square size={12} fill="currentColor" />
            <span>Stop</span>
          </button>
        )}

        {sessions.length > 0 && (
          <div className="flex items-center gap-1.5 bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-lg px-2 py-1">
            <History size={13} className="text-[var(--text-dim)]" />
            <select
              value={selectedSessionId}
              onChange={(e) => handleSelectSession(e.target.value)}
              className="bg-transparent text-xs text-[var(--text-primary)] outline-none cursor-pointer max-w-[190px]"
              title="Switch previous session chat history"
            >
              <option value="" className="bg-[var(--bg-secondary)]">New Session</option>
              {sessions.map((s) => {
                const isStopped = s.current_status === 'STOPPED';
                return (
                  <option
                    key={s.id}
                    value={String(s.id)}
                    className="bg-[var(--bg-secondary)]"
                  >
                    #{s.id}{isStopped ? ' [STOPPED]' : ''}: {(s.description || s.title || 'Project').slice(0, 24)}
                  </option>
                );
              })}
            </select>
          </div>
        )}
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

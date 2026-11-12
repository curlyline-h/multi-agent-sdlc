'use client';

import React, { useEffect, useRef } from 'react';
import { MainLayout } from '@/components/layout/MainLayout';
import { connectRealWorkflow } from '@/lib/realWorkflow';
import { getProject } from '@/lib/api';
import { useWorkflowStore } from '@/store/workflowStore';
import { PARENT_GRAPH_NODES, PARENT_GRAPH_EDGES } from '@/lib/graphData';
import { Workflow } from '@/types/workflow';

export default function DashboardPage() {
  const connectionRef = useRef<{ stop: () => void } | null>(null);

  useEffect(() => {
    // Initialize idle parent graph until user submits a prompt or selects a non-stopped session
    const initialWorkflow: Workflow = {
      id: 'wf-idle',
      projectId: 'new-project',
      status: 'pending',
      nodes: PARENT_GRAPH_NODES.map(n => ({ ...n, status: 'pending' as const })),
      edges: [...PARENT_GRAPH_EDGES],
      createdAt: new Date().toISOString(),
      currentPhase: 'Ready for Prompt',
      currentPhaseIndex: 0,
      totalPhases: 6,
    };
    useWorkflowStore.getState().setCurrentWorkflow(initialWorkflow);

    let cancelled = false;
    const activeId = typeof window !== 'undefined' ? localStorage.getItem('activeProjectId') : null;
    if (activeId && activeId !== 'live-sdlc-project' && activeId !== 'new-project') {
      getProject(activeId)
        .then((proj) => {
          if (cancelled) return;
          if (!proj || proj.current_status === 'STOPPED') {
            localStorage.removeItem('activeProjectId');
            return;
          }
          connectionRef.current = connectRealWorkflow(activeId);
        })
        .catch(() => {
          if (!cancelled) {
            localStorage.removeItem('activeProjectId');
          }
        });
    }

    return () => {
      cancelled = true;
      connectionRef.current?.stop();
    };
  }, []);

  return <MainLayout />;
}


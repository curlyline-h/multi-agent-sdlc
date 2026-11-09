'use client';

import React, { useEffect, useRef } from 'react';
import { MainLayout } from '@/components/layout/MainLayout';
import { connectRealWorkflow } from '@/lib/realWorkflow';
import { getLatestProject } from '@/lib/api';
import { useWorkflowStore } from '@/store/workflowStore';
import { PARENT_GRAPH_NODES, PARENT_GRAPH_EDGES } from '@/lib/graphData';
import { Workflow } from '@/types/workflow';

export default function DashboardPage() {
  const connectionRef = useRef<{ stop: () => void } | null>(null);

  useEffect(() => {
    // Initialize default parent graph UI workflow
    const initialWorkflow: Workflow = {
      id: 'wf-live-001',
      projectId: 'live-sdlc-project',
      status: 'running',
      nodes: PARENT_GRAPH_NODES.map(n => ({ ...n })),
      edges: [...PARENT_GRAPH_EDGES],
      createdAt: new Date().toISOString(),
      currentPhase: 'Requirements & Planning',
      currentPhaseIndex: 0,
      totalPhases: 6,
    };
    useWorkflowStore.getState().setCurrentWorkflow(initialWorkflow);

    async function initConnection() {
      let activeId = typeof window !== 'undefined' ? localStorage.getItem('activeProjectId') : null;
      if (!activeId) {
        const latest = await getLatestProject();
        if (latest && latest.id) {
          activeId = String(latest.id);
        }
      }

      const targetId = activeId || 'live-sdlc-project';
      connectionRef.current = connectRealWorkflow(targetId);
    }

    initConnection();

    return () => {
      connectionRef.current?.stop();
    };
  }, []);

  return <MainLayout />;
}


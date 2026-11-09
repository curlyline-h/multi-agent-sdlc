'use client';

import React, { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  MarkerType,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useWorkflowStore } from '@/store/workflowStore';
import { PARENT_GRAPH_NODES, PARENT_GRAPH_EDGES } from '@/lib/graphData';
import { GitBranch, Layers } from 'lucide-react';

// ── Custom node styles based on status ──────────────────────────────────
function getNodeStyle(status: string, nodeColor?: string) {
  const base = {
    padding: '10px 16px',
    borderRadius: '8px',
    fontSize: '11px',
    fontWeight: 500,
    fontFamily: 'var(--font-sans)',
    minWidth: '120px',
    textAlign: 'center' as const,
    transition: 'all 0.3s ease',
  };

  switch (status) {
    case 'running':
      return {
        ...base,
        background: 'rgba(245, 158, 11, 0.15)',
        border: '2px solid #f59e0b',
        color: '#fef08a',
        boxShadow: '0 0 20px rgba(245, 158, 11, 0.45)',
      };
    case 'completed':
      return {
        ...base,
        background: 'var(--state-completed-bg)',
        border: '1.5px solid var(--state-completed)',
        color: 'var(--state-completed)',
      };
    case 'failed':
      return {
        ...base,
        background: 'var(--state-error-bg)',
        border: '1.5px solid var(--state-error)',
        color: 'var(--state-error)',
      };
    case 'interrupted':
      return {
        ...base,
        background: 'rgba(245, 158, 11, 0.1)',
        border: '1.5px solid #f59e0b',
        color: '#f59e0b',
      };
    default: // pending
      return {
        ...base,
        background: 'var(--bg-tertiary)',
        border: '1px solid var(--border-subtle)',
        color: 'var(--text-dim)',
      };
  }
}

interface GraphViewProps {
  type: 'parent' | 'subgraph';
}

export function GraphView({ type }: GraphViewProps) {
  const { currentWorkflow, activeSubgraph } = useWorkflowStore();

  const sourceNodes = type === 'parent'
    ? (currentWorkflow?.nodes || PARENT_GRAPH_NODES)
    : (activeSubgraph?.nodes || []);

  const sourceEdges = type === 'parent'
    ? (currentWorkflow?.edges || PARENT_GRAPH_EDGES)
    : (activeSubgraph?.edges || []);

  // Convert to ReactFlow format
  const nodes: Node[] = useMemo(
    () =>
      sourceNodes.map((n) => {
        const isRunning =
          n.status === 'running' ||
          (type === 'parent' && activeSubgraph && currentWorkflow?.activeNodeId === n.id);

        const effectiveStatus = isRunning ? 'running' : n.status;

        return {
          id: n.id,
          position: n.position || { x: 0, y: 0 },
          data: {
            label: (
              <div className="flex items-center gap-1.5 justify-center">
                {effectiveStatus === 'completed' && <span className="text-xs">✅</span>}
                {effectiveStatus === 'running' && <span className="text-xs text-amber-400 animate-breathe">⚡</span>}
                {effectiveStatus === 'interrupted' && <span className="text-xs">⏳</span>}
                <span>{n.label}</span>
              </div>
            ),
          },
          style: getNodeStyle(effectiveStatus, n.nodeColor),
          draggable: false,
        };
      }),
    [sourceNodes, type, activeSubgraph, currentWorkflow?.activeNodeId]
  );

  const edges: Edge[] = useMemo(
    () =>
      sourceEdges.map((e) => {
        const sourceNode = sourceNodes.find((n) => n.id === e.from);
        const isSourceRunning =
          sourceNode?.status === 'running' ||
          (type === 'parent' && currentWorkflow?.activeNodeId === sourceNode?.id && Boolean(activeSubgraph));
        const isActive = Boolean(isSourceRunning || sourceNode?.status === 'completed');

        return {
          id: e.id,
          source: e.from,
          target: e.to,
          label: e.label,
          animated: isActive,
          style: {
            stroke: isSourceRunning ? '#f59e0b' : (isActive ? 'var(--accent-primary)' : 'var(--border-default)'),
            strokeWidth: isActive ? 2 : 1,
            opacity: isActive ? 1 : 0.4,
          },
          labelStyle: {
            fontSize: '9px',
            fill: 'var(--text-dim)',
            fontFamily: 'var(--font-mono)',
          },
          labelBgStyle: {
            fill: 'var(--bg-primary)',
            fillOpacity: 0.9,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 12,
            height: 12,
            color: isSourceRunning ? '#f59e0b' : (isActive ? 'var(--accent-primary)' : 'var(--border-default)'),
          },
        };
      }),
    [sourceEdges, sourceNodes, type, currentWorkflow?.activeNodeId, activeSubgraph]
  );

  if (type === 'subgraph' && !activeSubgraph) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-[var(--text-dim)]">
        <Layers size={24} className="mb-2 opacity-30" />
        <p className="text-xs">No active subgraph</p>
        <p className="text-[10px] mt-0.5">Agent subgraph will appear here during execution</p>
      </div>
    );
  }

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        attributionPosition="bottom-left"
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        zoomOnScroll={true}
        panOnScroll={true}
        minZoom={0.3}
        maxZoom={1.5}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="var(--border-subtle)"
        />
        <Controls
          showZoom={true}
          showFitView={true}
          showInteractive={false}
          position="bottom-right"
        />
        {type === 'parent' && (
          <MiniMap
            nodeColor={(node) => {
              const style = node.style as Record<string, string> | undefined;
              return style?.borderColor || 'var(--border-default)';
            }}
            maskColor="rgba(10, 10, 12, 0.8)"
            position="top-right"
          />
        )}
      </ReactFlow>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// GRAPH PANEL — Split view: parent graph + active subgraph
// ═══════════════════════════════════════════════════════════════════════════

export function GraphPanel() {
  const { activeSubgraph, currentWorkflow } = useWorkflowStore();

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      {/* ── Parent Graph ────────────────────────────────────────────────── */}
      <div className={`${activeSubgraph ? 'h-1/2' : 'h-full'} transition-all duration-300`}>
        <div className="panel-header">
          <div className="flex items-center gap-2">
            <GitBranch size={14} className="text-[var(--accent-primary)]" />
            <span>Pipeline Graph</span>
          </div>
          {currentWorkflow?.currentPhase && (
            <span className="text-[10px] text-[var(--accent-hover)] font-mono">
              {currentWorkflow.currentPhase}
            </span>
          )}
        </div>
        <div className="h-[calc(100%-33px)]">
          <GraphView type="parent" />
        </div>
      </div>

      {/* ── Subgraph (if active) ────────────────────────────────────────── */}
      {activeSubgraph && (
        <>
          <div className="panel-resizer panel-resizer-h" />
          <div className="h-1/2">
            <div className="panel-header">
              <div className="flex items-center gap-2">
                <Layers size={14} className="text-[var(--node-planning)]" />
                <span>{activeSubgraph.label}</span>
              </div>
              <span className="text-[10px] text-[var(--text-dim)] font-mono">
                subgraph
              </span>
            </div>
            <div className="h-[calc(100%-33px)]">
              <GraphView type="subgraph" />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

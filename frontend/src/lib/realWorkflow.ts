import { useChatStore } from '@/store/chatStore';
import { useWorkflowStore } from '@/store/workflowStore';
import { useProjectViewStore } from '@/store/projectViewStore';
import { useTerminalStore } from '@/store/terminalStore';
import { useLayoutStore } from '@/store/layoutStore';
import { PIPELINE_PHASES, buildSubgraphDefinition } from '@/lib/graphData';
import {
  getFileContent,
  getFileTree,
  getProject,
  getProjectApprovals,
  getProjectDocuments,
  getProjectFileRecords,
  getProjectGitDiff,
  getProjectLogs,
  getProjectTerminalLogs,
  getProjectWorkflow,
} from '@/lib/api';
import { TerminalLine } from '@/types/terminal';
import { ApprovalRequest } from '@/types/chat';
import { FileDiff } from '@/types/project';
import { AgentRole } from '@/types/agent';

const WS_BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/^http/, 'ws');
const DEFAULT_TERMINAL_ID = 'agent-terminal';

let activeSocket: WebSocket | null = null;
let shouldReconnect = false;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let pingTimer: ReturnType<typeof setInterval> | null = null;
let activeProjectRef: string | null = null;

function clearTimers() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
}

function stageToAgentRole(stageOrRole?: string): AgentRole | null {
  if (!stageOrRole) return null;
  const s = stageOrRole.toLowerCase();
  if (s.includes('plan')) return 'planner';
  if (s.includes('pm_') || s.includes('product')) return 'product_manager';
  if (s.includes('architect')) return 'architect';
  if (s.includes('task_breakdown')) return 'task_breakdown';
  if (s.includes('database')) return 'database_engineer';
  if (s.includes('backend')) return 'backend_dev';
  if (s.includes('frontend')) return 'frontend_dev';
  if (s.includes('qa')) return 'qa';
  if (s.includes('review')) return 'reviewer';
  if (s.includes('security')) return 'security';
  if (s.includes('devops')) return 'devops';
  if (s.includes('dispatch') || s.includes('orchestr')) return 'dispatcher';
  return null;
}

function parseUnifiedDiff(rawDiff: string): FileDiff[] {
  if (!rawDiff || !rawDiff.trim()) return [];
  const blocks = rawDiff.split(/^diff --git /m).filter((b) => b.trim());
  const parsed: FileDiff[] = [];
  for (const block of blocks) {
    const lines = block.split(/\r?\n/);
    const header = lines[0] || '';
    const pathMatch = header.match(/b\/(.+)$/);
    const path = pathMatch ? pathMatch[1].trim() : header.split(' ')[0] || 'unknown';
    const oldLines: string[] = [];
    const newLines: string[] = [];
    let additions = 0;
    let deletions = 0;
    let status: FileDiff['status'] = 'modified';
    for (const line of lines.slice(1)) {
      if (line.startsWith('new file mode')) {
        status = 'added';
      } else if (line.startsWith('deleted file mode')) {
        status = 'deleted';
      } else if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@') || line.startsWith('index ')) {
        continue;
      } else if (line.startsWith('+')) {
        newLines.push(line.slice(1));
        additions += 1;
      } else if (line.startsWith('-')) {
        oldLines.push(line.slice(1));
        deletions += 1;
      } else if (line.startsWith(' ')) {
        const txt = line.slice(1);
        oldLines.push(txt);
        newLines.push(txt);
      }
    }
    parsed.push({
      path,
      oldContent: oldLines.join('\n'),
      newContent: newLines.join('\n'),
      additions,
      deletions,
      status,
    });
  }
  return parsed;
}

function recordsToDiffs(records: any[]): FileDiff[] {
  if (!Array.isArray(records) || records.length === 0) return [];
  const seen = new Set<string>();
  const out: FileDiff[] = [];
  for (const rec of records) {
    const path = String(rec.file_path || '');
    if (!path || seen.has(path)) continue;
    seen.add(path);
    const parsed = rec.diff_snapshot ? parseUnifiedDiff(rec.diff_snapshot) : [];
    if (parsed.length > 0) {
      out.push(parsed[0]);
    } else {
      const action = String(rec.action || 'MODIFIED').toUpperCase();
      out.push({
        path,
        oldContent: '',
        newContent: String(rec.content_snapshot || rec.diff_snapshot || `// ${action}: ${path}`),
        additions: action === 'CREATED' ? 1 : 0,
        deletions: action === 'DELETED' ? 1 : 0,
        status: action === 'CREATED' ? 'added' : action === 'DELETED' ? 'deleted' : 'modified',
      });
    }
  }
  return out;
}

function buildApprovalRequest(raw: any): ApprovalRequest {
  let questions: string[] | undefined = Array.isArray(raw?.questions)
    ? raw.questions.map(String)
    : undefined;
  const rawContent = raw?.content ?? raw?.payload ?? '';
  if (!questions && typeof rawContent === 'string' && rawContent.trim().startsWith('[')) {
    try {
      const parsed = JSON.parse(rawContent);
      if (Array.isArray(parsed)) {
        questions = parsed.map(String);
      }
    } catch {
      // ignore non-JSON payload
    }
  }
  const title = String(raw?.section || raw?.request_details || 'Approval Required');
  const isQuestion = Boolean(questions && questions.length > 0) || title === 'clarifying_questions';
  return {
    id: String(raw?.approval_id ?? raw?.id ?? Date.now()),
    type: isQuestion ? 'clarifying_questions' : 'design',
    title,
    questions,
    draft: !isQuestion && typeof rawContent === 'string' ? rawContent : undefined,
    section: title,
    status: 'pending',
  };
}

function ensureTerminalSession() {
  const termStore = useTerminalStore.getState();
  if (!termStore.sessions.some((s) => s.id === DEFAULT_TERMINAL_ID)) {
    termStore.createSession({
      id: DEFAULT_TERMINAL_ID,
      label: 'Agent Terminal',
      agentName: 'orchestrator',
      lines: [
        {
          id: `init-${Date.now()}`,
          content: 'Connected to SDLC Agent Terminal stream...',
          type: 'info',
          timestamp: Date.now(),
        },
      ],
      isActive: true,
    });
  }
}

function appendTerminalCommand(data: Record<string, any>) {
  ensureTerminalSession();
  const termStore = useTerminalStore.getState();
  const now = Date.now();
  const lines: TerminalLine[] = [];

  if (data.command) {
    lines.push({
      id: `cmd-${now}-${Math.random().toString(36).slice(2, 6)}`,
      content: String(data.command),
      type: 'command',
      timestamp: now,
    });
  }

  const pushOutput = (raw: unknown, type: TerminalLine['type']) => {
    if (!raw) return;
    const text = String(raw).trimEnd();
    if (!text) return;
    for (const line of text.split(/\r?\n/).slice(-40)) {
      lines.push({
        id: `out-${now}-${Math.random().toString(36).slice(2, 7)}`,
        content: line,
        type,
        timestamp: now,
      });
    }
  };

  pushOutput(data.stdout, 'stdout');
  pushOutput(data.stderr, 'stderr');

  if (typeof data.exit_code === 'number') {
    lines.push({
      id: `exit-${now}-${Math.random().toString(36).slice(2, 6)}`,
      content: `Process exited with code ${data.exit_code}`,
      type: data.exit_code === 0 ? 'success' : 'error',
      timestamp: now,
    });
  }

  if (lines.length > 0) {
    termStore.addLines(DEFAULT_TERMINAL_ID, lines);
    termStore.setVisible(true);
    const layout = useLayoutStore.getState();
    if (!layout.isTerminalVisible) {
      layout.toggleTerminal();
    }
  }
}

function activateStageVisuals(stageId: string, subNode?: string) {
  const wfStore = useWorkflowStore.getState();
  const chatStore = useChatStore.getState();

  const existingSub = wfStore.activeSubgraph;
  if (!existingSub || existingSub.id !== stageId) {
    const def = buildSubgraphDefinition(stageId);
    wfStore.setActiveSubgraph(def);
  }
  if (subNode) {
    wfStore.setSubgraphActiveNode(subNode);
  }

  const role = stageToAgentRole(stageId);
  if (role) {
    chatStore.setActiveAgent(role);
    chatStore.setActiveAgentState('executing');
    if (subNode) {
      chatStore.setActiveAgentNode(subNode);
    }
  }
}

export function disconnectRealWorkflow() {
  shouldReconnect = false;
  activeProjectRef = null;
  clearTimers();
  if (activeSocket) {
    activeSocket.onclose = null;
    activeSocket.onerror = null;
    activeSocket.close();
    activeSocket = null;
  }
  useChatStore.getState().setConnected(false);
}

export function connectRealWorkflow(projectId: string): { stop: () => void } {
  disconnectRealWorkflow();

  shouldReconnect = true;
  activeProjectRef = projectId;
  ensureTerminalSession();

  if (typeof window !== 'undefined' && projectId && projectId !== 'live-sdlc-project') {
    localStorage.setItem('activeProjectId', projectId);
  }

  const refreshDocuments = () => {
    if (!projectId || projectId === 'live-sdlc-project' || projectId === 'new-project') return;
    getProjectDocuments(projectId)
      .then((docs) => {
        if (Array.isArray(docs)) {
          useProjectViewStore.getState().setDocuments(docs);
        }
      })
      .catch(() => {});
  };

  const refreshDiffs = () => {
    if (!projectId || projectId === 'live-sdlc-project' || projectId === 'new-project') return;
    Promise.all([getProjectGitDiff(projectId), getProjectFileRecords(projectId)])
      .then(([gitRes, records]) => {
        const parsed = parseUnifiedDiff(gitRes?.diff || '');
        const diffs = parsed.length > 0 ? parsed : recordsToDiffs(records);
        if (diffs.length > 0) {
          useProjectViewStore.getState().setDiffs(diffs);
        }
      })
      .catch(() => {});
  };

  const hydrateState = () => {
    if (projectId && projectId !== 'live-sdlc-project' && projectId !== 'new-project') {
      // Hydrate session chat history if chat panel is currently empty
      if (useChatStore.getState().messages.length === 0) {
        Promise.all([getProject(projectId), getProjectLogs(projectId)])
          .then(([proj, logs]) => {
            const chat = useChatStore.getState();
            if (chat.messages.length > 0) return;
            if (proj?.description) {
              chat.addMessage({
                id: `user-init-${projectId}`,
                role: 'user',
                content: proj.description,
                timestamp: Date.now(),
              } as any);
            }
            if (Array.isArray(logs)) {
              let lastContent = '';
              for (const log of logs) {
                const msgText = log.request_details || log.payload || '';
                if (!msgText || msgText === lastContent) continue;
                lastContent = msgText;
                chat.addMessage({
                  id: `hist-${log.id}`,
                  role: 'agent',
                  agentRole: log.requesting_agent_id || 'orchestrator',
                  content: msgText,
                  timestamp: (log.created_at || log.timestamp) ? new Date(log.created_at || log.timestamp).getTime() : Date.now(),
                } as any);
              }
            }
          })
          .catch(() => {});
      }

      // Single canonical pending-approval hydration
      getProjectApprovals(projectId)
        .then((approvals) => {
          if (!Array.isArray(approvals)) return;
          const pending = approvals.find((a: any) => String(a.status).toUpperCase() === 'PENDING');
          const chat = useChatStore.getState();
          if (pending) {
            const req = buildApprovalRequest(pending);
            chat.setPendingApproval(req);
            chat.setActiveAgentState('awaiting_approval');
            const alreadyShown = chat.messages.some((m) => m.approval?.id === req.id);
            if (!alreadyShown) {
              chat.addMessage({
                id: `approval-${req.id}`,
                role: 'agent',
                agentRole: 'orchestrator',
                content: '',
                approval: req,
                timestamp: Date.now(),
              } as any);
            }
          } else {
            chat.setPendingApproval(null);
          }
        })
        .catch(() => {});

      getProjectTerminalLogs(projectId)
        .then((cmds) => {
          if (Array.isArray(cmds) && cmds.length > 0) {
            for (const c of cmds) {
              appendTerminalCommand(c);
            }
          }
        })
        .catch(() => {});

      getProjectWorkflow(projectId)
        .then((wf) => {
          const store = useWorkflowStore.getState();
          const chat = useChatStore.getState();
          if (!wf) return;

          try {
            const done = JSON.parse(wf.completed_nodes || '[]');
            if (Array.isArray(done)) {
              for (const nodeId of done) {
                if (nodeId && nodeId !== 'START') {
                  store.completeNode(nodeId);
                }
              }
            }
          } catch {
            // ignore invalid completed_nodes JSON
          }

          if (wf.current_state && wf.current_state !== 'START') {
            if (wf.current_state === 'COMPLETED' || wf.status === 'COMPLETED') {
              store.completeNode(wf.current_state);
              store.setActiveSubgraph(null);
              store.updatePhase('COMPLETED', PIPELINE_PHASES.length, PIPELINE_PHASES.length);
              chat.setActiveAgentState('completed');
            } else if (wf.status === 'FAILED') {
              store.setNodeStatus(wf.current_state, 'failed');
              store.updatePhase('Failed', store.currentWorkflow?.currentPhaseIndex || 0, PIPELINE_PHASES.length);
              chat.setActiveAgentState('error');
            } else if (wf.status === 'STOPPED' || wf.status === 'PAUSED') {
              store.setNodeStatus(wf.current_state, 'pending');
              store.setActiveSubgraph(null);
              store.updatePhase('Stopped', store.currentWorkflow?.currentPhaseIndex || 0, PIPELINE_PHASES.length);
              chat.setActiveAgentState('idle');
            } else if (wf.status === 'RUNNING' || wf.status === 'AWAITING_APPROVAL') {
              store.setActiveNode(wf.current_state);
              const idx = PIPELINE_PHASES.indexOf(wf.current_state);
              store.updatePhase(wf.current_state, idx >= 0 ? idx + 1 : 1, PIPELINE_PHASES.length);
              activateStageVisuals(wf.current_state, wf.current_subgraph_node || undefined);
              if (wf.status === 'AWAITING_APPROVAL') {
                chat.setActiveAgentState('awaiting_approval');
              }
            } else {
              store.updatePhase(wf.current_state, 0, PIPELINE_PHASES.length);
            }
          } else {
            store.updatePhase(wf.status === 'STOPPED' ? 'Stopped' : 'Ready for Prompt', 0, PIPELINE_PHASES.length);
          }
        })
        .catch(() => {});

      refreshDocuments();
      refreshDiffs();
    }

    getFileTree(projectId)
      .then((tree) => {
        if (Array.isArray(tree)) {
          useProjectViewStore.getState().setFileTree(tree);
        }
      })
      .catch(() => {});
  };

  hydrateState();

  let reconnectAttempt = 0;

  const openSocket = () => {
    if (!shouldReconnect || activeProjectRef !== projectId) return;

    const ws = new WebSocket(`${WS_BASE}/ws/projects/${projectId}`);
    activeSocket = ws;

    ws.onopen = () => {
      reconnectAttempt = 0;
      useChatStore.getState().setConnected(true);
      clearTimers();
      pingTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          try {
            ws.send(JSON.stringify({ type: 'ping' }));
          } catch {
            // ignore send failure; onclose will handle reconnect
          }
        }
      }, 15000);
    };

    ws.onclose = () => {
      useChatStore.getState().setConnected(false);
      if (pingTimer) {
        clearInterval(pingTimer);
        pingTimer = null;
      }
      if (activeSocket === ws) {
        activeSocket = null;
      }
      if (shouldReconnect && activeProjectRef === projectId) {
        const delayMs = Math.min(10000, 1000 * Math.pow(2, reconnectAttempt));
        reconnectAttempt += 1;
        reconnectTimer = setTimeout(() => {
          hydrateState();
          openSocket();
        }, delayMs);
      }
    };

    ws.onerror = () => {
      useChatStore.getState().setConnected(false);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const eventType = payload.event || payload.type;
        const data = payload.data || payload;

        if (eventType === 'PONG') {
          return;
        }

        if (eventType === 'HUMAN_INTERRUPT') {
          const req = buildApprovalRequest(data);
          const chat = useChatStore.getState();
          chat.setPendingApproval(req);
          chat.setActiveAgentState('awaiting_approval');
          const alreadyShown = chat.messages.some((m) => m.approval?.id === req.id);
          if (!alreadyShown) {
            chat.addMessage({
              id: `approval-${req.id}`,
              role: 'agent',
              agentRole: 'orchestrator',
              content: '',
              approval: req,
              timestamp: Date.now(),
            } as any);
          }
          refreshDocuments();
          return;
        }

        if (eventType === 'LOG_EMITTED') {
          useChatStore.getState().addMessage({
            id: `log-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            role: 'agent',
            agentRole: data.agent_name,
            content: data.message || '',
            timestamp: Date.now(),
          } as any);
          if (data.message) {
            ensureTerminalSession();
            useTerminalStore.getState().addLine(DEFAULT_TERMINAL_ID, {
              id: `tlog-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              content: `[${data.agent_name || 'agent'}] ${String(data.message).replace(/\*\*/g, '')}`,
              type: 'info',
              timestamp: Date.now(),
            });
          }
        } else if (eventType === 'STAGE_CHANGED' && data.stage) {
          const wfStore = useWorkflowStore.getState();
          const chatStore = useChatStore.getState();
          if (data.stage === 'COMPLETED') {
            if (wfStore.currentWorkflow?.activeNodeId) {
              wfStore.completeNode(wfStore.currentWorkflow.activeNodeId);
            }
            wfStore.setActiveSubgraph(null);
            wfStore.updatePhase('COMPLETED', PIPELINE_PHASES.length, PIPELINE_PHASES.length);
            chatStore.setActiveAgentState('completed');
            chatStore.setActiveAgentNode(null);
            refreshDocuments();
            refreshDiffs();
          } else if (data.stage === 'STOPPED' || data.state === 'STOPPED') {
            if (wfStore.currentWorkflow?.activeNodeId) {
              wfStore.setNodeStatus(wfStore.currentWorkflow.activeNodeId, 'pending');
            }
            wfStore.setActiveSubgraph(null);
            wfStore.updatePhase('Stopped', wfStore.currentWorkflow?.currentPhaseIndex || 0, PIPELINE_PHASES.length);
            chatStore.setActiveAgentState('idle');
            chatStore.setActiveAgentNode(null);
          } else {
            wfStore.setActiveNode(data.stage);
            const idx = PIPELINE_PHASES.indexOf(data.stage);
            if (idx >= 0) {
              wfStore.updatePhase(data.stage, idx + 1, PIPELINE_PHASES.length);
            }
            activateStageVisuals(data.stage);
            refreshDocuments();
          }
        } else if (eventType === 'SUBGRAPH_NODE_CHANGED') {
          const wfStore = useWorkflowStore.getState();
          const stageId = data.parent_stage || wfStore.currentWorkflow?.activeNodeId;
          if (stageId) {
            wfStore.setActiveNode(stageId);
            activateStageVisuals(stageId, data.sub_node);
          } else if (data.sub_node) {
            wfStore.setSubgraphActiveNode(data.sub_node);
            useChatStore.getState().setActiveAgentNode(data.sub_node);
          }
        } else if (eventType === 'TERMINAL_COMMAND') {
          appendTerminalCommand(data);
        } else if (eventType === 'FILE_CHANGE') {
          getFileTree(projectId)
            .then((tree) => {
              if (Array.isArray(tree)) {
                useProjectViewStore.getState().setFileTree(tree);
              }
            })
            .catch(() => {});

          // Auto-refresh content if the modified file is currently open in a tab
          if (data.path) {
            const pv = useProjectViewStore.getState();
            const isOpen = pv.openTabs.some(
              (t) => t.path === data.path || t.path.endsWith(`/${data.path}`) || String(data.path).endsWith(`/${t.path}`)
            );
            if (isOpen) {
              getFileContent(data.path, projectId)
                .then((res) => {
                  if (res && res.content !== undefined) {
                    useProjectViewStore.getState().updateFileContent(data.path, res.content);
                  }
                })
                .catch(() => {});
            }
            if (String(data.path).endsWith('.md')) {
              refreshDocuments();
            }
          }
          refreshDiffs();
        } else if (eventType === 'GIT_DIFF' && typeof data.diff === 'string') {
          const parsed = parseUnifiedDiff(data.diff);
          if (parsed.length > 0) {
            useProjectViewStore.getState().setDiffs(parsed);
          }
        } else if (eventType === 'TASKS_UPDATED' && Array.isArray(data.tasks)) {
          const doneCount = Array.isArray(data.completed_task_titles) ? data.completed_task_titles.length : 0;
          ensureTerminalSession();
          useTerminalStore.getState().addLine(DEFAULT_TERMINAL_ID, {
            id: `tasks-${Date.now()}`,
            content: `[dispatcher] Task board synced: ${doneCount}/${data.tasks.length} completed`,
            type: 'info',
            timestamp: Date.now(),
          });
        } else if (eventType === 'ERROR' && data.message) {
          useChatStore.getState().setActiveAgentState('error');
          useChatStore.getState().addMessage({
            id: `err-${Date.now()}`,
            role: 'agent',
            agentRole: 'orchestrator',
            content: `Error: ${data.message}`,
            timestamp: Date.now(),
          } as any);
          appendTerminalCommand({ stderr: data.message, exit_code: 1 });
        }
      } catch {
        // Ignore malformed messages
      }
    };
  };

  openSocket();

  return {
    stop: disconnectRealWorkflow,
  };
}

import { useChatStore } from '@/store/chatStore';
import { useWorkflowStore } from '@/store/workflowStore';
import { useTerminalStore } from '@/store/terminalStore';
import { AgentRole } from '@/types/agent';
import { ApprovalType } from '@/types/chat';

let activeSocket: WebSocket | null = null;

export function disconnectRealWorkflow() {
  if (activeSocket) {
    try {
      activeSocket.close();
    } catch (e) {
      console.warn('Error closing websocket:', e);
    }
    activeSocket = null;
  }
}

export function connectRealWorkflow(projectId: string) {
  disconnectRealWorkflow();

  const wsBase = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/projects';
  const url = wsBase.endsWith('/') ? `${wsBase}${projectId}` : `${wsBase}/${projectId}`;

  console.log(`Connecting WebSocket to: ${url}`);
  const socket = new WebSocket(url);
  activeSocket = socket;

  socket.onopen = () => {
    console.log(`WebSocket connected for project ${projectId}`);
    useChatStore.getState().setConnected(true);
  };

  socket.onclose = () => {
    console.log(`WebSocket disconnected for project ${projectId}`);
    useChatStore.getState().setConnected(false);
  };

  socket.onerror = (err) => {
    console.error('WebSocket encountered error:', err);
    useChatStore.getState().setConnected(false);
  };

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      const { event: eventType, data } = payload;

      if (!eventType) return;

      switch (eventType) {
        case 'AGENT_LOG': {
          const role = (data?.agent_role || 'orchestrator') as AgentRole;
          const msg = data?.message || '';
          useChatStore.getState().addMessage({
            id: `msg-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
            role: 'agent',
            content: msg,
            agentRole: role,
            timestamp: Date.now(),
          });
          useChatStore.getState().setActiveAgent(role);
          useChatStore.getState().setActiveAgentState('executing');

          const activeSessionId = useTerminalStore.getState().activeSessionId;
          if (activeSessionId) {
            useTerminalStore.getState().addLine(activeSessionId, {
              id: `line-${Date.now()}`,
              content: `[${role.toUpperCase()}] ${msg}`,
              type: 'stdout',
              timestamp: Date.now(),
            });
          }
          break;
        }

        case 'HUMAN_INTERRUPT': {
          const approvalId = String(data?.approval_id || Date.now());
          const section = data?.section || 'Approval Required';
          const content = data?.draft || data?.content || data?.message || (typeof data === 'string' ? data : JSON.stringify(data));
          const appType = (data?.type || 'general') as ApprovalType;

          useChatStore.getState().setPendingApproval({
            id: approvalId,
            type: appType,
            title: section,
            message: data?.message || '',
            questions: Array.isArray(data?.questions) ? data.questions : undefined,
            draft: content,
            section: section,
            status: 'pending',
          });
          useChatStore.getState().setActiveAgentState('awaiting_approval');
          break;
        }

        case 'WORKFLOW_UPDATE': {
          if (data?.current_state) {
            useWorkflowStore.getState().setActiveNode(data.current_state);
          }
          if (data?.completed_node) {
            useWorkflowStore.getState().completeNode(data.completed_node);
          }
          break;
        }

        case 'STREAM_TOKEN': {
          if (data?.messageId && data?.token) {
            useChatStore.getState().updateStreamingMessage(data.messageId, data.token);
          }
          break;
        }

        default:
          console.log(`Unhandled WS event: ${eventType}`, data);
      }
    } catch (err) {
      console.warn('Failed to parse WS message:', err, event.data);
    }
  };

  return {
    stop: () => {
      disconnectRealWorkflow();
    },
  };
}

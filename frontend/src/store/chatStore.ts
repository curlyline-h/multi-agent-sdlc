'use client';

import { create } from 'zustand';
import { ChatMessage, ApprovalRequest } from '@/types/chat';
import { AgentRole, AgentState } from '@/types/agent';

interface ChatState {
  messages: ChatMessage[];
  activeAgent: AgentRole | null;
  activeAgentState: AgentState | null;
  activeAgentNode: string | null; // Current subgraph node label
  pendingApproval: ApprovalRequest | null;
  isConnected: boolean;

  // Actions
  addMessage: (message: ChatMessage) => void;
  updateStreamingMessage: (messageId: string, token: string) => void;
  finishStreaming: (messageId: string) => void;
  setActiveAgent: (role: AgentRole | null) => void;
  setActiveAgentState: (state: AgentState | null) => void;
  setActiveAgentNode: (node: string | null) => void;
  setPendingApproval: (approval: ApprovalRequest | null) => void;
  submitApproval: (approvalId: string, approved: boolean, feedback?: string) => void;
  setConnected: (connected: boolean) => void;
  clearMessages: () => void;
  resetAll: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  activeAgent: null,
  activeAgentState: null,
  activeAgentNode: null,
  pendingApproval: null,
  isConnected: true,

  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),

  updateStreamingMessage: (messageId, token) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === messageId
          ? { ...m, streamedContent: (m.streamedContent || '') + token }
          : m
      ),
    })),

  finishStreaming: (messageId) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === messageId
          ? { ...m, isStreaming: false, content: m.streamedContent || m.content, streamedContent: undefined }
          : m
      ),
    })),

  setActiveAgent: (role) => set({ activeAgent: role }),
  setActiveAgentState: (agentState) => set({ activeAgentState: agentState }),
  setActiveAgentNode: (node) => set({ activeAgentNode: node }),

  setPendingApproval: (approval) => set({ pendingApproval: approval }),

  submitApproval: (approvalId, approved, feedback) =>
    set((state) => ({
      pendingApproval: null,
      messages: state.messages.map((m) =>
        m.approval?.id === approvalId
          ? {
              ...m,
              approval: {
                ...m.approval,
                status: approved ? 'approved' : 'rejected',
                feedback,
              },
            }
          : m
      ),
    })),

  setConnected: (connected) => set({ isConnected: connected }),
  clearMessages: () => set({ messages: [], pendingApproval: null }),
  resetAll: () => set({
    messages: [],
    activeAgent: null,
    activeAgentState: null,
    activeAgentNode: null,
    pendingApproval: null,
    isConnected: true, // Hide error banner before a project is created
  }),
}));

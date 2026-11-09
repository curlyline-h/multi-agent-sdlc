'use client';

import { create } from 'zustand';
import { TerminalSession, TerminalLine } from '@/types/terminal';

interface TerminalState {
  sessions: TerminalSession[];
  activeSessionId: string | null;
  isVisible: boolean;

  // Actions
  createSession: (session: TerminalSession) => void;
  removeSession: (id: string) => void;
  addLine: (sessionId: string, line: TerminalLine) => void;
  addLines: (sessionId: string, lines: TerminalLine[]) => void;
  switchSession: (id: string) => void;
  toggleVisible: () => void;
  setVisible: (visible: boolean) => void;
  clearSession: (id: string) => void;
}

export const useTerminalStore = create<TerminalState>((set) => ({
  sessions: [],
  activeSessionId: null,
  isVisible: true,

  createSession: (session) =>
    set((state) => ({
      sessions: [...state.sessions, session],
      activeSessionId: state.activeSessionId || session.id,
    })),

  removeSession: (id) =>
    set((state) => {
      const newSessions = state.sessions.filter((s) => s.id !== id);
      return {
        sessions: newSessions,
        activeSessionId:
          state.activeSessionId === id
            ? newSessions[0]?.id || null
            : state.activeSessionId,
      };
    }),

  addLine: (sessionId, line) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId ? { ...s, lines: [...s.lines, line] } : s
      ),
    })),

  addLines: (sessionId, lines) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId ? { ...s, lines: [...s.lines, ...lines] } : s
      ),
    })),

  switchSession: (id) => set({ activeSessionId: id }),
  toggleVisible: () => set((state) => ({ isVisible: !state.isVisible })),
  setVisible: (visible) => set({ isVisible: visible }),

  clearSession: (id) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === id ? { ...s, lines: [] } : s
      ),
    })),
}));

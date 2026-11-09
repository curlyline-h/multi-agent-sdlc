'use client';

import { create } from 'zustand';

export type ViewMode = 'workspace' | 'project' | 'docs';

interface LayoutState {
  viewMode: ViewMode;
  chatPanelWidth: number; // percentage
  graphPanelHeight: number; // percentage of right panel
  terminalHeight: number; // pixels
  isSidebarExpanded: boolean;
  isTerminalVisible: boolean;
  isGraphVisible: boolean;

  // Actions
  setViewMode: (mode: ViewMode) => void;
  setChatPanelWidth: (width: number) => void;
  setGraphPanelHeight: (height: number) => void;
  setTerminalHeight: (height: number) => void;
  toggleSidebar: () => void;
  toggleTerminal: () => void;
  toggleGraph: () => void;
}

export const useLayoutStore = create<LayoutState>((set) => ({
  viewMode: 'workspace',
  chatPanelWidth: 40,
  graphPanelHeight: 60,
  terminalHeight: 200,
  isSidebarExpanded: false,
  isTerminalVisible: true,
  isGraphVisible: true,

  setViewMode: (mode) => set({ viewMode: mode }),
  setChatPanelWidth: (width) => set({ chatPanelWidth: Math.max(25, Math.min(75, width)) }),
  setGraphPanelHeight: (height) => set({ graphPanelHeight: Math.max(20, Math.min(80, height)) }),
  setTerminalHeight: (height) => set({ terminalHeight: Math.max(100, Math.min(500, height)) }),
  toggleSidebar: () => set((state) => ({ isSidebarExpanded: !state.isSidebarExpanded })),
  toggleTerminal: () => set((state) => ({ isTerminalVisible: !state.isTerminalVisible })),
  toggleGraph: () => set((state) => ({ isGraphVisible: !state.isGraphVisible })),
}));

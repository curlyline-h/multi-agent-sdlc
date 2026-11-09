'use client';

import { create } from 'zustand';
import { FileNode, FileDiff, ProjectDocument } from '@/types/project';

interface ProjectViewState {
  fileTree: FileNode[];
  selectedFile: FileNode | null;
  openTabs: FileNode[];
  activeTabPath: string | null;
  showDiff: boolean;
  diffs: FileDiff[];
  selectedDiff: FileDiff | null;
  documents: ProjectDocument[];
  selectedDocument: ProjectDocument | null;

  // Actions
  setFileTree: (tree: FileNode[]) => void;
  selectFile: (file: FileNode) => void;
  openTab: (file: FileNode) => void;
  closeTab: (path: string) => void;
  setActiveTab: (path: string) => void;
  toggleDiffView: () => void;
  setDiffs: (diffs: FileDiff[]) => void;
  selectDiff: (diff: FileDiff | null) => void;
  setDocuments: (docs: ProjectDocument[]) => void;
  selectDocument: (doc: ProjectDocument | null) => void;
}

export const useProjectViewStore = create<ProjectViewState>((set) => ({
  fileTree: [],
  selectedFile: null,
  openTabs: [],
  activeTabPath: null,
  showDiff: false,
  diffs: [],
  selectedDiff: null,
  documents: [],
  selectedDocument: null,

  setFileTree: (tree) => set({ fileTree: tree }),

  selectFile: (file) =>
    set((state) => {
      const alreadyOpen = state.openTabs.some((t) => t.path === file.path);
      return {
        selectedFile: file,
        activeTabPath: file.path,
        openTabs: alreadyOpen ? state.openTabs : [...state.openTabs, file],
      };
    }),

  openTab: (file) =>
    set((state) => {
      const alreadyOpen = state.openTabs.some((t) => t.path === file.path);
      return {
        activeTabPath: file.path,
        openTabs: alreadyOpen ? state.openTabs : [...state.openTabs, file],
      };
    }),

  closeTab: (path) =>
    set((state) => {
      const newTabs = state.openTabs.filter((t) => t.path !== path);
      const wasActive = state.activeTabPath === path;
      return {
        openTabs: newTabs,
        activeTabPath: wasActive ? (newTabs[newTabs.length - 1]?.path || null) : state.activeTabPath,
        selectedFile: wasActive ? (newTabs[newTabs.length - 1] || null) : state.selectedFile,
      };
    }),

  setActiveTab: (path) =>
    set((state) => ({
      activeTabPath: path,
      selectedFile: state.openTabs.find((t) => t.path === path) || state.selectedFile,
    })),

  toggleDiffView: () => set((state) => ({ showDiff: !state.showDiff })),
  setDiffs: (diffs) => set({ diffs }),
  selectDiff: (diff) => set({ selectedDiff: diff }),
  setDocuments: (docs) => set({ documents: docs }),
  selectDocument: (doc) => set({ selectedDocument: doc }),
}));

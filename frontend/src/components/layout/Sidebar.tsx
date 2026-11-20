'use client';

import React, { useState } from 'react';
import { useLayoutStore, ViewMode } from '@/store/layoutStore';
import { useChatStore } from '@/store/chatStore';
import {
  MessageSquare,
  GitBranch,
  Code2,
  FileText,
  Terminal,
  Settings,
  Zap,
} from 'lucide-react';

interface SidebarItem {
  id: ViewMode | string;
  icon: React.ReactNode;
  label: string;
  isView?: boolean;
}

const items: SidebarItem[] = [
  { id: 'workspace', icon: <MessageSquare size={18} />, label: 'Chat & Graph', isView: true },
  { id: 'project', icon: <Code2 size={18} />, label: 'Project Files', isView: true },
  { id: 'docs', icon: <FileText size={18} />, label: 'Documents', isView: true },
];

const bottomItems: SidebarItem[] = [
  { id: 'terminal-toggle', icon: <Terminal size={18} />, label: 'Terminal' },
  { id: 'settings', icon: <Settings size={18} />, label: 'Settings' },
];

export function Sidebar() {
  const { viewMode, setViewMode, toggleTerminal, isTerminalVisible } = useLayoutStore();
  const { isConnected } = useChatStore();
  const [showSettings, setShowSettings] = useState(false);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const activeProjectId =
    typeof window !== 'undefined' ? localStorage.getItem('activeProjectId') || 'None' : 'None';

  const handleClick = (item: SidebarItem) => {
    if (item.isView) {
      setViewMode(item.id as ViewMode);
      setShowSettings(false);
    } else if (item.id === 'terminal-toggle') {
      toggleTerminal();
    } else if (item.id === 'settings') {
      setShowSettings((prev) => !prev);
    }
  };

  return (
    <aside className="w-[var(--sidebar-width)] bg-[var(--bg-secondary)] border-r border-[var(--border-subtle)] flex flex-col items-center py-3 flex-shrink-0">
      {/* Logo */}
      <div className="mb-4">
        <div className="w-8 h-8 rounded-lg bg-[var(--accent-primary)] flex items-center justify-center">
          <Zap size={16} className="text-white" />
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex flex-col items-center gap-1 flex-1">
        {items.map((item) => (
          <div key={item.id} className="relative group">
            <button
              onClick={() => handleClick(item)}
              className={`sidebar-icon ${
                item.isView && viewMode === item.id ? 'sidebar-icon-active' : ''
              }`}
            >
              {item.icon}
            </button>
            {/* Tooltip */}
            <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 bg-[var(--bg-elevated)] text-[var(--text-primary)] text-[10px] rounded shadow-lg border border-[var(--border-subtle)] whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">
              {item.label}
            </div>
          </div>
        ))}
      </nav>

      {/* Bottom items */}
      <div className="flex flex-col items-center gap-1">
        {bottomItems.map((item) => (
          <div key={item.id} className="relative group">
            <button
              onClick={() => handleClick(item)}
              className={`sidebar-icon ${
                (item.id === 'terminal-toggle' && isTerminalVisible) ||
                (item.id === 'settings' && showSettings)
                  ? 'sidebar-icon-active'
                  : ''
              }`}
            >
              {item.icon}
            </button>
            <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 bg-[var(--bg-elevated)] text-[var(--text-primary)] text-[10px] rounded shadow-lg border border-[var(--border-subtle)] whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">
              {item.label}
            </div>
          </div>
        ))}
      </div>

      {/* Settings Popover */}
      {showSettings && (
        <div className="fixed left-[calc(var(--sidebar-width)+8px)] bottom-3 w-72 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg shadow-2xl p-3 z-50 text-xs">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-[var(--text-primary)]">Runtime Settings</span>
            <button
              onClick={() => setShowSettings(false)}
              className="text-[var(--text-dim)] hover:text-[var(--text-primary)]"
            >
              ✕
            </button>
          </div>
          <div className="space-y-1.5 text-[var(--text-secondary)]">
            <div className="flex justify-between gap-2">
              <span className="text-[var(--text-dim)]">Backend API:</span>
              <span className="font-mono truncate">{apiUrl}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-[var(--text-dim)]">WebSocket:</span>
              <span className={isConnected ? 'text-[var(--state-completed)]' : 'text-[var(--state-error)]'}>
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-[var(--text-dim)]">Active Project:</span>
              <span className="font-mono">#{activeProjectId}</span>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

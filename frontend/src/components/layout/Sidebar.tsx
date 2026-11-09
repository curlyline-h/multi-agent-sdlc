'use client';

import React from 'react';
import { useLayoutStore, ViewMode } from '@/store/layoutStore';
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

  const handleClick = (item: SidebarItem) => {
    if (item.isView) {
      setViewMode(item.id as ViewMode);
    } else if (item.id === 'terminal-toggle') {
      toggleTerminal();
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
                item.id === 'terminal-toggle' && isTerminalVisible ? 'sidebar-icon-active' : ''
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
    </aside>
  );
}

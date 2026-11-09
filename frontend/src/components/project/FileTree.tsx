'use client';

import React, { useState } from 'react';
import { FileNode } from '@/types/project';
import { useProjectViewStore } from '@/store/projectViewStore';
import { getFileContent } from '@/lib/api';
import {
  ChevronRight,
  ChevronDown,
  FileCode2,
  FileJson,
  FileText,
  Folder,
  FolderOpen,
  FileType,
  Search,
} from 'lucide-react';

// ── File icon based on language/extension ────────────────────────────────
function getFileIcon(name: string, language?: string) {
  const safeName = name || '';
  if (language === 'typescript' || safeName.endsWith('.tsx') || safeName.endsWith('.ts'))
    return <FileCode2 size={14} className="text-blue-400" />;
  if (language === 'python' || safeName.endsWith('.py'))
    return <FileCode2 size={14} className="text-yellow-400" />;
  if (language === 'json' || safeName.endsWith('.json'))
    return <FileJson size={14} className="text-amber-400" />;
  if (language === 'css' || safeName.endsWith('.css'))
    return <FileType size={14} className="text-purple-400" />;
  if (language === 'markdown' || safeName.endsWith('.md'))
    return <FileText size={14} className="text-gray-400" />;
  if (safeName.endsWith('.yml') || safeName.endsWith('.yaml'))
    return <FileText size={14} className="text-pink-400" />;
  if (safeName === 'Dockerfile')
    return <FileCode2 size={14} className="text-cyan-400" />;
  return <FileText size={14} className="text-[var(--text-dim)]" />;
}

// ── Tree Item ────────────────────────────────────────────────────────────
function TreeItem({ node, depth = 0 }: { node: FileNode; depth?: number }) {
  const [isOpen, setIsOpen] = useState(depth < 2);
  const { selectFile, activeTabPath } = useProjectViewStore();
  const isDir = node.type === 'directory';
  const isActive = activeTabPath === node.path;

  const handleClick = () => {
    if (isDir) {
      setIsOpen(!isOpen);
    } else {
      selectFile(node);
      if (node.content === undefined) {
        getFileContent(node.path)
          .then((data) => {
            if (data && data.content !== undefined) {
              selectFile({ ...node, content: data.content });
            }
          })
          .catch((err) => console.warn('Could not load file content:', err));
      }
    }
  };

  return (
    <div>
      <div
        className={`file-tree-item ${isActive ? 'file-tree-item-active' : ''}`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={handleClick}
      >
        {/* Expand/collapse chevron for dirs */}
        {isDir ? (
          <span className="text-[var(--text-dim)] w-3.5">
            {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
        ) : (
          <span className="w-3.5" />
        )}

        {/* Icon */}
        {isDir ? (
          isOpen ? (
            <FolderOpen size={14} className="text-[var(--state-approval)]" />
          ) : (
            <Folder size={14} className="text-[var(--state-approval)]" />
          )
        ) : (
          getFileIcon(node.name, node.language)
        )}

        {/* Name */}
        <span className="truncate flex-1">{node.name}</span>

        {/* Modified indicator */}
        {node.isModified && (
          <span className="w-2 h-2 rounded-full bg-[var(--state-drafting)] flex-shrink-0" />
        )}
      </div>

      {/* Children */}
      {isDir && isOpen && node.children && (
        <div>
          {node.children.map((child) => (
            <TreeItem key={child.path} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── File Tree Component ──────────────────────────────────────────────────
export function FileTree() {
  const { fileTree } = useProjectViewStore();
  const [search, setSearch] = useState('');

  return (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="p-2 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-2 px-2 py-1.5 bg-[var(--bg-primary)] rounded-md border border-[var(--border-subtle)]">
          <Search size={12} className="text-[var(--text-dim)]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search files..."
            className="flex-1 bg-transparent text-xs text-[var(--text-primary)] placeholder-[var(--text-dim)] outline-none"
          />
        </div>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto py-1">
        {fileTree.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-[var(--text-dim)]">
            <Folder size={24} className="mb-2 opacity-30" />
            <p className="text-xs">No files yet</p>
          </div>
        ) : (
          fileTree.map((node) => <TreeItem key={node.path} node={node} />)
        )}
      </div>
    </div>
  );
}

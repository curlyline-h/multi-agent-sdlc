// ── Terminal Types ────────────────────────────────────────────────────────

export type TerminalLineType = 'stdout' | 'stderr' | 'command' | 'info' | 'success' | 'error';

export interface TerminalLine {
  id: string;
  content: string;
  type: TerminalLineType;
  timestamp: number;
}

export interface TerminalSession {
  id: string;
  label: string;
  agentName?: string;
  agentAvatar?: string;
  lines: TerminalLine[];
  isActive: boolean;
}

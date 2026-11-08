# Multi-Agent SDLC Frontend — Interactive Dashboard

Build a premium, dark-themed (black/charcoal/gray) Next.js frontend that provides real-time visibility into the multi-agent SDLC pipeline through four core panels: Chat Interface, Graph Visualization, Project Viewer, and Terminal.

## User Review Required

> [!IMPORTANT]
> **Tailwind CSS**: The project already uses Tailwind CSS v4. The plan keeps Tailwind for utility classes (existing pattern) and adds custom CSS variables for the charcoal design system. Please confirm this is acceptable vs. switching to pure vanilla CSS.

> [!IMPORTANT]
> **New Dependencies**: This plan introduces several new packages. Please review:
> - `reactflow` — interactive node-based graph visualization (n8n-like)
> - `@xterm/xterm` + `@xterm/addon-fit` — terminal emulator
> - `react-diff-viewer-continued` — git-style diff viewer
> - `react-markdown` + `remark-gfm` — markdown rendering for docs/PRDs
> - `react-syntax-highlighter` — code syntax highlighting for project viewer
> - `lucide-react` — icon library (lightweight, tree-shakeable)
>
> All are well-maintained, production-grade packages. No backend changes required — this phase is frontend-only with mock data.

> [!WARNING]
> **Backend WebSocket Integration**: This plan builds the complete UI with **mock data and simulated streaming**. Real WebSocket integration with the FastAPI backend (via Redis Pub/Sub as described in [complete_pipeline_flow.md](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/complete_pipeline_flow.md)) will be a separate follow-up phase. The hooks and stores are designed to be swapped to real WebSocket connections without UI changes.

## Open Questions

> [!IMPORTANT]
> **Chat Approval UX**: When the Planner or PM agent requests approval via `interrupt()`, should the approval UI be:
> - (A) Inline buttons in the chat message (Approve / Reject + feedback textarea) — like a Slack approval
> - (B) A modal overlay that blocks interaction until resolved
> - (C) Both — inline buttons that expand into a modal for detailed feedback
>
> The current plan implements **(C)** — inline approval cards that expand.

> [!IMPORTANT]
> **Graph Visualization Scope**: The architecture has a parent orchestrator graph AND individual subgraphs per agent (Planning, PM Phase A, Architect, etc.). Should:
> - (A) The main view show the parent graph, and clicking a node drills into its subgraph
> - (B) Both parent graph and active subgraph display simultaneously in a split view
> - (C) Auto-switch: show parent graph overview, but when an agent is active, animate into its subgraph
>
> The current plan implements **(B)** — split view with parent graph on top and active subgraph below.

---

## Proposed Changes

### Component 1: Design System & Global Styles

The entire app gets a premium black/charcoal/gray theme with subtle accent colors for agent states.

#### [MODIFY] [globals.css](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/frontend/src/app/globals.css)
- Complete rewrite of the CSS design system
- Custom properties for the charcoal palette: `--bg-primary: #0a0a0c`, `--bg-secondary: #111114`, `--bg-tertiary: #18181b`, `--bg-elevated: #1e1e22`, `--border: #27272a`, `--text-primary: #fafafa`, `--text-secondary: #a1a1aa`, `--text-muted: #71717a`
- Agent state accent colors: thinking (amber pulse), drafting (blue glow), waiting (gray), completed (emerald), error (rose)
- Custom scrollbar styles, glassmorphism utilities, streaming text animation keyframes
- Panel layout utilities for the split-view architecture

#### [MODIFY] [layout.tsx](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/frontend/src/app/layout.tsx)
- Update metadata title/description for SEO
- Add Inter + JetBrains Mono from Google Fonts
- Apply dark theme class to html element

---

### Component 2: Type System

Extend the existing types to support chat messages, agent states, graph nodes, file trees, and terminal sessions.

#### [MODIFY] [agent.ts](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/frontend/src/types/agent.ts)
- Add agent states: `'thinking' | 'drafting' | 'reviewing' | 'waiting_approval' | 'executing' | 'idle' | 'completed' | 'error'`
- Add agent phase tracking (which subgraph node is active)

#### [MODIFY] [workflow.ts](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/frontend/src/types/workflow.ts)
- Add subgraph node types with positions for ReactFlow
- Add edge animation states (active, completed, pending)

#### [NEW] chat.ts — `src/types/chat.ts`
- `ChatMessage` interface: role (user/agent/system), content, agentName, agentState, timestamp, streaming flag, approval payload
- `ApprovalRequest` interface: type (prd/design/deployment), content preview, approve/reject handlers
- `StreamingChunk` interface for real-time token streaming

#### [NEW] project.ts additions — Extend `src/types/project.ts`
- `FileNode` interface: path, name, type (file/dir), language, content, children
- `FileDiff` interface: oldContent, newContent, path, additions, deletions
- `Document` interface: title, content (markdown), type (prd/design/plan), status

#### [NEW] terminal.ts — `src/types/terminal.ts`
- `TerminalLine` interface: content, type (stdout/stderr/command), timestamp
- `TerminalSession` interface: id, agentName, lines, active flag

---

### Component 3: State Management (Zustand Stores)

#### [MODIFY] [workflowStore.ts](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/frontend/src/store/workflowStore.ts)
- Add active node tracking, subgraph state, animation state
- Add methods: `setActiveNode`, `completeNode`, `setActiveSubgraph`

#### [NEW] chatStore.ts — `src/store/chatStore.ts`
- Messages array with streaming support
- Active agent state (thinking/drafting/etc.)
- Pending approval state
- Methods: `addMessage`, `updateStreamingMessage`, `setAgentState`, `submitApproval`

#### [NEW] projectViewStore.ts — `src/store/projectViewStore.ts`
- File tree state, selected file, diff mode toggle
- Open tabs array (like VS Code)
- Methods: `selectFile`, `openTab`, `closeTab`, `toggleDiffView`

#### [NEW] terminalStore.ts — `src/store/terminalStore.ts`
- Terminal sessions per agent
- Active terminal ID
- Methods: `addLine`, `createSession`, `switchSession`

#### [NEW] layoutStore.ts — `src/store/layoutStore.ts`
- Panel visibility toggles (chat, graph, project, terminal)
- Panel sizes for resizable layouts
- Active view mode: `'chat-graph' | 'project' | 'terminal'`

---

### Component 4: Chat Interface Components

The centerpiece of the UI — an interactive chat where agents communicate, show their thinking state, stream responses, and request approvals.

#### [NEW] ChatPanel.tsx — `src/components/chat/ChatPanel.tsx`
- Main chat container with message list + input area
- Auto-scroll behavior, message grouping by agent
- Keyboard shortcuts (Enter to send, Shift+Enter for newline)

#### [NEW] ChatMessage.tsx — `src/components/chat/ChatMessage.tsx`
- Individual message bubble with agent avatar, name, role badge
- Streaming text animation (tokens appearing progressively)
- Markdown rendering for PRD/design doc content
- Expandable sections for long content

#### [NEW] AgentStateIndicator.tsx — `src/components/chat/AgentStateIndicator.tsx`
- Animated state chips: "🧠 Thinking...", "📝 Drafting PRD...", "🔍 Reviewing...", "⏳ Waiting for approval..."
- Pulsing/breathing animations matching the agent's current activity
- Shows which subgraph node the agent is currently in

#### [NEW] ApprovalCard.tsx — `src/components/chat/ApprovalCard.tsx`
- Inline approval UI that appears in the chat flow
- Shows document preview (PRD, Design Doc, etc.)
- Approve button (emerald) / Request Changes button (amber)
- Expandable feedback textarea when "Request Changes" is clicked
- Renders the approval payload from LangGraph's `interrupt()` 

#### [NEW] ChatInput.tsx — `src/components/chat/ChatInput.tsx`
- Multi-line textarea with auto-resize
- Send button with loading state
- Disabled state when no approval is pending (chat is agent-driven)

---

### Component 5: Graph Visualization Components

Interactive, n8n-style graph visualization using ReactFlow, showing both the parent orchestrator and active subgraphs.

#### [NEW] GraphPanel.tsx — `src/components/graph/GraphPanel.tsx`
- Split view: parent orchestrator graph (top) + active subgraph (bottom)
- Collapsible with smooth animation
- Minimap for large graphs
- Zoom/pan controls

#### [NEW] ParentGraph.tsx — `src/components/graph/ParentGraph.tsx`
- ReactFlow canvas rendering the parent orchestrator nodes from [architecture_overview.md](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/architecture_overview.md)
- Nodes: Planning → PM Phase A → Architect → Task Breakdown → PM Phase B → Dispatcher → [Agent stages] → END
- Active node highlighted with glow effect + animation
- Completed nodes get emerald checkmark, pending nodes are dim gray
- Edges animate with flowing dots when data is being passed

#### [NEW] SubgraphView.tsx — `src/components/graph/SubgraphView.tsx`
- Renders the active agent's internal subgraph (e.g., Planning subgraph: Clarification → Generate Draft → Critique → User Approval → Finalize)
- Automatically switches when a different agent becomes active
- Same visual language as parent graph but with agent-specific accent color

#### [NEW] GraphNode.tsx — `src/components/graph/GraphNode.tsx`
- Custom ReactFlow node component
- States: pending (dim), running (animated glow), completed (emerald), failed (rose), interrupt (amber)
- Agent icon/emoji, node label, mini status text
- Click handler to jump to that agent's chat messages

#### [NEW] GraphEdge.tsx — `src/components/graph/GraphEdge.tsx`
- Custom animated edge with flowing particles for active connections
- Dotted line for pending, solid for completed, pulsing for active

#### [NEW] graphData.ts — `src/lib/graphData.ts`
- Static graph definitions mapping the parent orchestrator and all subgraphs to ReactFlow node/edge format
- Node positions, edge routing, subgraph definitions for all 11 agents
- Based exactly on the mermaid diagrams in [architecture_overview.md](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/architecture_overview.md)

---

### Component 6: Project Viewer Components

VS Code-like file explorer with syntax highlighting and git diff view.

#### [NEW] ProjectPanel.tsx — `src/components/project/ProjectPanel.tsx`
- Three-pane layout: file tree (left) + code viewer (center) + diff view (toggle)
- Tab bar for open files (like VS Code tabs)
- Language detection for syntax highlighting

#### [NEW] FileTree.tsx — `src/components/project/FileTree.tsx`
- Recursive collapsible tree with file/folder icons
- File type icons (`.ts`, `.py`, `.md`, `.json`, etc.)
- Modified files highlighted with a dot indicator
- Search/filter input at top

#### [NEW] CodeViewer.tsx — `src/components/project/CodeViewer.tsx`
- Syntax-highlighted code display using react-syntax-highlighter
- Line numbers, copy button
- Charcoal theme matching the overall design
- Scrollable with position memory per file

#### [NEW] DiffViewer.tsx — `src/components/project/DiffViewer.tsx`
- Side-by-side or unified diff view using react-diff-viewer-continued
- Shows additions (emerald), deletions (rose), modifications (amber)
- File path header with change summary (+N / -N)
- Toggle between "Changes" and "Full File" views

#### [NEW] DocumentViewer.tsx — `src/components/project/DocumentViewer.tsx`
- Markdown renderer for PRDs, implementation plans, design docs
- Styled like Antigravity's artifact viewer
- Table of contents sidebar for long documents
- Syntax highlighting for embedded code blocks

---

### Component 7: Terminal Component

Embedded terminal view showing agent command execution.

#### [NEW] TerminalPanel.tsx — `src/components/terminal/TerminalPanel.tsx`
- Xterm.js terminal emulator with charcoal theme
- Tab bar for multiple terminal sessions (one per active agent)
- Shows real-time command execution output
- Agent name badge on each terminal tab
- Resizable height

---

### Component 8: Layout & Navigation

Restructure the main layout for the multi-panel workspace.

#### [MODIFY] [MainLayout.tsx](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/frontend/src/components/layout/MainLayout.tsx)
- Remove old simple layout
- New workspace layout with resizable panels
- Panel arrangement: Left (Chat) | Right (Graph + Terminal, stacked)
- View mode switcher: "Chat & Graph" | "Project" | "Docs"

#### [MODIFY] [Sidebar.tsx](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/frontend/src/components/layout/Sidebar.tsx)
- Slim icon-only sidebar (collapsed by default) matching charcoal theme
- Icons for: Chat, Graph, Project Files, Documents, Terminal, Settings
- Active indicator with accent glow
- Tooltip on hover showing label

#### [MODIFY] [Header.tsx](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/frontend/src/components/layout/Header.tsx)
- Project name + active agent indicator
- Pipeline progress bar (Phase 1/6, 2/6, etc.)
- System status indicator (connected/disconnected)

#### [NEW] PanelResizer.tsx — `src/components/layout/PanelResizer.tsx`
- Draggable divider between panels
- Double-click to reset to default size
- Minimum/maximum size constraints

#### [NEW] ViewSwitcher.tsx — `src/components/layout/ViewSwitcher.tsx`
- Tab bar to switch between workspace views
- Smooth crossfade transitions between views

---

### Component 9: Hooks

#### [NEW] useWebSocket.ts — `src/hooks/useWebSocket.ts`
- WebSocket connection manager (mock for now, real implementation later)
- Auto-reconnect with exponential backoff
- Message parsing and routing to appropriate stores

#### [NEW] useStreamingText.ts — `src/hooks/useStreamingText.ts`
- Simulates token-by-token text streaming for the chat
- Configurable speed, supports markdown content
- Returns current visible text + completion state

#### [NEW] usePanelResize.ts — `src/hooks/usePanelResize.ts`
- Mouse drag handler for panel resizing
- Persists sizes to localStorage
- Respects min/max constraints

---

### Component 10: Mock Data & Simulation

#### [NEW] mockData.ts — `src/lib/mockData.ts`
- Realistic mock chat conversation simulating the full SDLC flow
- Planning agent asking clarifying questions → PM drafting PRD → Approval flow
- Mock file tree with generated code files
- Mock terminal output for agent commands
- Mock diff data showing code changes

#### [NEW] simulateWorkflow.ts — `src/lib/simulateWorkflow.ts`
- Timed simulation that drives all the stores
- Progressively activates graph nodes, sends chat messages, updates agent states
- Demonstrates the full UX with realistic timing

---

### Component 11: Main Workspace Page

#### [MODIFY] [page.tsx (dashboard)](file:///c:/Users/Orax%20Technologies/Desktop/hamza_sdlc/frontend/src/app/dashboard/page.tsx)
- Replace static dashboard with the interactive workspace
- Renders the multi-panel layout with all components
- Initializes the workflow simulation on mount

---

## Verification Plan

### Build Verification
- `npm run build` must complete without errors
- `npm run lint` must pass

### Manual Verification
- Run `npm run dev` and verify:
  - [ ] Chat messages appear with streaming animation
  - [ ] Agent states (thinking, drafting) show animated indicators
  - [ ] Approval cards render with approve/reject buttons
  - [ ] Parent graph renders with all orchestrator nodes
  - [ ] Active subgraph renders when an agent is active
  - [ ] Graph nodes animate through pending → running → completed states
  - [ ] File tree is navigable and code viewer shows syntax highlighting
  - [ ] Diff viewer shows additions/deletions with color coding
  - [ ] Document viewer renders markdown PRDs correctly
  - [ ] Terminal displays simulated command output
  - [ ] Panel resizing works smoothly
  - [ ] All panels use the black/charcoal/gray theme consistently
  - [ ] Micro-animations and hover effects feel premium

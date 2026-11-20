const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ''}`);
  }
  return res.json();
}

export async function getLatestProject(): Promise<{ id: number; name: string; description: string } | null> {
  try {
    return await apiFetch('/projects/latest');
  } catch {
    return null;
  }
}

export async function createProject(name: string, user_req: string) {
  const data = await apiFetch<{ id: number; name: string; description: string }>('/projects', {
    method: 'POST',
    body: JSON.stringify({ name, user_req }),
  });
  if (typeof window !== 'undefined' && data?.id) {
    localStorage.setItem('activeProjectId', String(data.id));
  }
  return data;
}

export async function resumeProject(projectId: string) {
  return apiFetch(`/projects/${projectId}/resume`, { method: 'POST' });
}

export async function stopProject(projectId: string) {
  return apiFetch<{ status: string; project_id: number; task_cancelled: boolean }>(`/projects/${projectId}/stop`, {
    method: 'POST',
  });
}

export async function getProjectApprovals(projectId: string) {
  return apiFetch<any[]>(`/approvals/project/${projectId}`);
}

export async function respondToApproval(approvalId: string, feedback: string = '') {
  return apiFetch(`/approvals/${approvalId}/respond`, {
    method: 'POST',
    body: JSON.stringify({
      status: feedback.trim() ? 'FEEDBACK_SUBMITTED' : 'APPROVED',
      feedback,
      feed_back: feedback,
    }),
  });
}

export async function getFileContent(path: string, projectId?: string): Promise<{ path: string; content: string }> {
  const pid = projectId || (typeof window !== 'undefined' ? localStorage.getItem('activeProjectId') || '' : '');
  const q = pid && pid !== 'live-sdlc-project' && pid !== 'new-project' ? `&project_id=${encodeURIComponent(pid)}` : '';
  return apiFetch(`/files/content?path=${encodeURIComponent(path)}${q}`);
}

export async function getFileTree(projectId?: string) {
  const pid = projectId || (typeof window !== 'undefined' ? localStorage.getItem('activeProjectId') || '' : '');
  const q = pid && pid !== 'live-sdlc-project' && pid !== 'new-project' ? `?project_id=${encodeURIComponent(pid)}` : '';
  return apiFetch<any[]>(`/files/tree${q}`);
}

export async function getProjectWorkflow(projectId: string) {
  return apiFetch<any>(`/workflows/project/${projectId}`);
}

export async function listProjects(): Promise<Array<{ id: number; title?: string; name?: string; description?: string; current_status?: string }>> {
  try {
    return await apiFetch('/projects');
  } catch {
    return [];
  }
}

export async function getProject(projectId: string): Promise<{ id: number; title?: string; description?: string; current_status?: string } | null> {
  try {
    return await apiFetch(`/projects/${projectId}`);
  } catch {
    return null;
  }
}

export async function getProjectLogs(projectId: string): Promise<any[]> {
  try {
    return await apiFetch(`/logs/project/${projectId}`);
  } catch {
    return [];
  }
}

export async function getProjectTerminalLogs(projectId: string): Promise<any[]> {
  try {
    return await apiFetch(`/terminal/project/${projectId}`);
  } catch {
    return [];
  }
}

export async function getProjectDocuments(projectId: string): Promise<any[]> {
  try {
    return await apiFetch(`/documents/project/${projectId}`);
  } catch {
    return [];
  }
}

export async function getProjectGitDiff(projectId: string): Promise<{ diff: string }> {
  try {
    return await apiFetch(`/files/git-diff?project_id=${encodeURIComponent(projectId)}`);
  } catch {
    return { diff: '' };
  }
}

export async function getProjectFileRecords(projectId: string): Promise<any[]> {
  try {
    return await apiFetch(`/files/records/project/${projectId}`);
  } catch {
    return [];
  }
}

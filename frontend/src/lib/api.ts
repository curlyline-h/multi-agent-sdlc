const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function getLatestProject() {
  try {
    const res = await fetch(`${API_BASE}/projects/latest`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.warn('Could not fetch latest project:', err);
    return null;
  }
}

export async function createProject(name: string, prompt: string) {
  const res = await fetch(`${API_BASE}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, user_req: prompt }),
  });
  if (!res.ok) {
    const errorDetail = await res.text();
    throw new Error(`Failed to create project (${res.status}): ${errorDetail}`);
  }
  const data = await res.json();
  if (typeof window !== 'undefined' && data?.id) {
    localStorage.setItem('activeProjectId', String(data.id));
  }
  return data;
}

export async function resumeProject(projectId: string | number, feedback?: string) {
  const res = await fetch(`${API_BASE}/projects/${projectId}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback: feedback || '' }),
  });
  if (!res.ok) {
    const errorDetail = await res.text();
    throw new Error(`Resume error (${res.status}): ${errorDetail}`);
  }
  return await res.json();
}

export async function getProjectApprovals(projectId: string | number) {
  const res = await fetch(`${API_BASE}/approvals/project/${projectId}`);
  if (!res.ok) return [];
  return await res.json();
}

export async function respondToApproval(approvalId: string | number, feedback: string) {
  const res = await fetch(`${API_BASE}/approvals/${approvalId}/respond`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      approved: true,
      feedback: feedback || '',
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to submit approval: ${res.statusText}`);
  }
  return await res.json();
}

export async function getFileContent(filePath: string) {
  const activeProjectId = typeof window !== 'undefined' ? localStorage.getItem('activeProjectId') : null;
  const url = activeProjectId
    ? `${API_BASE}/files/content?project_id=${activeProjectId}&path=${encodeURIComponent(filePath)}`
    : `${API_BASE}/files/content?path=${encodeURIComponent(filePath)}`;
  const res = await fetch(url);
  if (!res.ok) return { content: '' };
  return await res.json();
}

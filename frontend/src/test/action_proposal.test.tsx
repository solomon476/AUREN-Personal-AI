/**
 * Unit & Integration Tests for AI Action Proposals (MessageContent & ActionProposalCard).
 * Verifies the proposed -> awaiting confirmation -> executing -> completed / failed lifecycle,
 * localStorage execution persistence, duplicate prevention, and retry handling.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MessageContent } from '../components/chat/MessageContent';
import * as productivityApi from '../api/productivity';
import * as settingsApi from '../api/settings';
import * as memoriesApi from '../api/memories';

vi.mock('../api/settings', async () => {
  const actual = await vi.importActual<any>('../api/settings');
  return {
    ...actual,
    updateUserProfile: vi.fn(),
  };
});

vi.mock('../api/memories', async () => {
  const actual = await vi.importActual<any>('../api/memories');
  return {
    ...actual,
    createMemory: vi.fn(),
    listMemories: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  };
});

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<any>();
  const user = { id: 'usr-test-123', email: 'test@auren.ai', role: 'authenticated' };
  return {
    ...actual,
    AuthContext: React.createContext({
      user,
      isAuthenticated: true,
    }),
    useAuth: () => ({
      user,
      isAuthenticated: true,
    }),
  };
});

vi.mock('../api/productivity', async () => {
  const actual = await vi.importActual<any>('../api/productivity');
  return {
    ...actual,
    createTask: vi.fn(),
    createProject: vi.fn(),
    createGoal: vi.fn(),
    getTasks: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    getProjects: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    getGoals: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  };
});

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

describe('Action Proposals & Lifecycle Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders action proposal card from auren-action fenced code block', () => {
    const qc = createTestQueryClient();
    const markdown = `
Here is a suggested task for your review:

\`\`\`auren-action
{
  "type": "create_task",
  "title": "Review Q4 Security Audit",
  "priority": "high",
  "due_date": "2026-11-30"
}
\`\`\`
`;
    render(
      <QueryClientProvider client={qc}>
        <MessageContent content={markdown} role="assistant" />
      </QueryClientProvider>
    );

    expect(screen.getByText('Task Proposal')).toBeInTheDocument();
    expect(screen.getByText('Review Q4 Security Audit')).toBeInTheDocument();
    expect(screen.getByText('Priority: high')).toBeInTheDocument();
    expect(screen.getByText('Due: 2026-11-30')).toBeInTheDocument();
    expect(screen.getByText('Requires confirmation')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add to tasks/i })).toBeInTheDocument();
  });

  it('executes task creation on confirm and transitions to completed state', async () => {
    const qc = createTestQueryClient();
    vi.mocked(productivityApi.createTask).mockResolvedValueOnce({
      id: 'task-new-1',
      user_id: 'usr-test-123',
      title: 'Review Q4 Security Audit',
      priority: 'high',
      status: 'todo',
      tags: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    const markdown = `
\`\`\`auren-action
{
  "type": "create_task",
  "title": "Review Q4 Security Audit",
  "priority": "high"
}
\`\`\`
`;
    render(
      <QueryClientProvider client={qc}>
        <MessageContent content={markdown} role="assistant" />
      </QueryClientProvider>
    );

    const button = screen.getByRole('button', { name: /add to tasks/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(productivityApi.createTask).toHaveBeenCalledTimes(1);
      expect(screen.getByText('Added to Life Management')).toBeInTheDocument();
    });

    // Verify state was saved to localStorage
    const savedKeys = Object.keys(localStorage);
    expect(savedKeys.some((k) => k.startsWith('auren_action_'))).toBe(true);
  });

  it('prevents duplicate creation by restoring completed state from localStorage on page reload', async () => {
    const qc = createTestQueryClient();
    const actionKey = 'auren_action_usr-test-123_create_task_Review Q4 Security Audit__high';
    localStorage.setItem(
      actionKey,
      JSON.stringify({
        status: 'completed',
        entityId: 'task-existing-99',
        updatedAt: new Date().toISOString(),
      })
    );

    const markdown = `
\`\`\`auren-action
{
  "type": "create_task",
  "title": "Review Q4 Security Audit",
  "priority": "high"
}
\`\`\`
`;
    render(
      <QueryClientProvider client={qc}>
        <MessageContent content={markdown} role="assistant" />
      </QueryClientProvider>
    );

    // Should immediately show executed badge without "Add to Tasks" button!
    expect(screen.getByText('Added to Life Management')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add to tasks/i })).not.toBeInTheDocument();
    expect(productivityApi.createTask).not.toHaveBeenCalled();
  });

  it('handles execution failure, displays error message, and allows safe retry', async () => {
    const qc = createTestQueryClient();
    vi.mocked(productivityApi.createProject).mockRejectedValueOnce(
      new Error('Database unique constraint failed')
    );

    const markdown = `
\`\`\`auren-action
{
  "type": "create_project",
  "name": "Core Hardening",
  "description": "Hardening the system"
}
\`\`\`
`;
    render(
      <QueryClientProvider client={qc}>
        <MessageContent content={markdown} role="assistant" />
      </QueryClientProvider>
    );

    const button = screen.getByRole('button', { name: /create project/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText('Database unique constraint failed')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /retry create project/i })).toBeInTheDocument();
    });

    // Retry should be possible
    vi.mocked(productivityApi.createProject).mockResolvedValueOnce({
      id: 'proj-1',
      user_id: 'usr-test-123',
      name: 'Core Hardening',
      description: 'Hardening the system',
      color: '#4f46e5',
      status: 'active',
      task_count: 0,
      completed_task_count: 0,
      progress_percentage: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    const retryButton = screen.getByRole('button', { name: /retry create project/i });
    await userEvent.click(retryButton);

    await waitFor(() => {
      expect(screen.getByText('Added to Life Management')).toBeInTheDocument();
    });
  });

  it('supports an array of multiple action proposals within a single block', () => {
    const qc = createTestQueryClient();
    const markdown = `
\`\`\`auren-action
[
  {
    "type": "create_task",
    "title": "Action Item 1"
  },
  {
    "type": "create_goal",
    "title": "Quarterly Milestone"
  }
]
\`\`\`
`;
    render(
      <QueryClientProvider client={qc}>
        <MessageContent content={markdown} role="assistant" />
      </QueryClientProvider>
    );

    expect(screen.getByText('Action Item 1')).toBeInTheDocument();
    expect(screen.getByText('Quarterly Milestone')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add to tasks/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /set goal/i })).toBeInTheDocument();
  });

  it('associates action execution state with conversationId', async () => {
    const qc = createTestQueryClient();
    vi.mocked(productivityApi.createTask).mockResolvedValueOnce({
      id: 'task-conv-1',
      user_id: 'usr-test-123',
      title: 'Scoped to Conversation',
      priority: 'low',
      status: 'todo',
      tags: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    const markdown = `
\`\`\`auren-action
{
  "type": "create_task",
  "title": "Scoped to Conversation",
  "priority": "low"
}
\`\`\`
`;
    render(
      <QueryClientProvider client={qc}>
        <MessageContent content={markdown} role="assistant" conversationId="conv-456" />
      </QueryClientProvider>
    );

    const button = screen.getByRole('button', { name: /add to tasks/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText('Added to Life Management')).toBeInTheDocument();
    });

    // Verify localStorage key contains conversationId
    const storedKeys = Object.keys(localStorage);
    expect(storedKeys.some((k) => k.includes('conv-456'))).toBe(true);
  });

  it('recovers safely on retry if entity was already created on the server without creating duplicates', async () => {
    const qc = createTestQueryClient();
    // Simulate initial failure / timeout
    vi.mocked(productivityApi.createTask).mockRejectedValueOnce(new Error('Gateway timeout'));

    const markdown = `
\`\`\`auren-action
{
  "type": "create_task",
  "title": "Idempotent Safe Task"
}
\`\`\`
`;
    render(
      <QueryClientProvider client={qc}>
        <MessageContent content={markdown} role="assistant" />
      </QueryClientProvider>
    );

    const button = screen.getByRole('button', { name: /add to tasks/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText(/retry add to tasks/i)).toBeInTheDocument();
    });

    // Before retry, backend actually has the task (it succeeded despite client timeout)
    vi.mocked(productivityApi.getTasks).mockResolvedValueOnce({
      items: [
        {
          id: 'task-already-created',
          user_id: 'usr-test-123',
          title: 'Idempotent Safe Task',
          priority: 'medium',
          status: 'todo',
          tags: [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
    });

    const retryButton = screen.getByRole('button', { name: /retry add to tasks/i });
    await userEvent.click(retryButton);

    await waitFor(() => {
      expect(screen.getByText('Added to Life Management')).toBeInTheDocument();
    });

    // createTask must NOT have been called a second time (prevented duplicate!)
    expect(productivityApi.createTask).toHaveBeenCalledTimes(1);
  });

  it('respects server-executed app actions without duplicating writes and supports delete, settings, memory & navigation cards', async () => {
    const qc = createTestQueryClient();
    const onNavigate = vi.fn();

    // 1. Server pre-executed action skips client re-creation
    const executedMd = `
\`\`\`auren-action
{
  "type": "create_task",
  "title": "Server Executed Task"
}
\`\`\`
`;
    const { unmount } = render(
      <QueryClientProvider client={qc}>
        <MessageContent
          content={executedMd}
          role="assistant"
          executedActions={[
            {
              action_type: 'create_task',
              status: 'executed',
              domain: 'tasks',
              summary: "Created task 'Server Executed Task'",
            },
          ]}
        />
      </QueryClientProvider>
    );
    expect(screen.getByText('Added to Life Management')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add to tasks/i })).not.toBeInTheDocument();
    expect(productivityApi.createTask).not.toHaveBeenCalled();
    unmount();

    // 2. Interactive Settings, Memory, Confirm Delete Task, and Navigation command cards
    vi.mocked(settingsApi.updateUserProfile).mockResolvedValueOnce({} as any);
    vi.mocked(memoriesApi.createMemory).mockResolvedValueOnce({ id: 'mem-1', content: 'Prefer morning study' } as any);

    const commandsMd = `
\`\`\`auren-action
[
  { "type": "update_settings", "theme": "dark", "quiet_hours_enabled": true },
  { "type": "create_memory", "content": "Prefer morning study", "memory_type": "preference" },
  { "type": "delete_task", "task_id": "task-del-1", "title": "Old Draft" },
  { "type": "navigate", "path": "/tasks" }
]
\`\`\`
`;
    render(
      <QueryClientProvider client={qc}>
        <MessageContent content={commandsMd} role="assistant" onNavigate={onNavigate} />
      </QueryClientProvider>
    );

    await userEvent.click(screen.getByRole('button', { name: /Apply Preferences/i }));
    await waitFor(() => {
      expect(settingsApi.updateUserProfile).toHaveBeenCalledWith(
        expect.objectContaining({
          preferences: expect.objectContaining({ theme: 'dark', quiet_hours_enabled: true }),
        })
      );
    });

    await userEvent.click(screen.getByRole('button', { name: /Save Memory Update/i }));
    await waitFor(() => {
      expect(memoriesApi.createMemory).toHaveBeenCalledWith(
        expect.objectContaining({ content: 'Prefer morning study', memory_type: 'preference' })
      );
    });

    const deleteSpy = vi.spyOn(productivityApi, 'deleteTask').mockResolvedValueOnce(undefined);
    await userEvent.click(screen.getByRole('button', { name: /Confirm Delete/i }));
    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('task-del-1');
    });

    await userEvent.click(screen.getByRole('button', { name: /Open \/tasks/i }));
    expect(onNavigate).toHaveBeenCalledWith('/tasks');
  });
});

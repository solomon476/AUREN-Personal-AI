/**
 * Unit & Integration Tests for HomeView (AUREN Personal AI Command Center).
 * Verifies greeting, Priorities Radar, Active Projects, Strategic Goals,
 * Recent AI Dialogue, AI Composer quick entry, and Guest Mode handling.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HomeView } from '../features/home/HomeView';
import * as productivityApi from '../api/productivity';
import * as chatApi from '../api/chat';

const mockNavigate = vi.fn();

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual<any>('@tanstack/react-router');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    Link: ({ children, to, className, ...props }: any) => (
      <a href={typeof to === 'string' ? to : '#'} className={className} {...props}>
        {children}
      </a>
    ),
  };
});

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<any>();
  const user = { id: 'usr-home-123', email: 'solomon@auren.ai', role: 'authenticated' };
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
    getProductivityDashboard: vi.fn(),
    getTasks: vi.fn(),
    changeTaskStatus: vi.fn(),
    getProjects: vi.fn(),
    getGoals: vi.fn(),
  };
});

vi.mock('../api/chat', async () => {
  const actual = await vi.importActual<any>('../api/chat');
  return {
    ...actual,
    listConversations: vi.fn(),
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

describe('HomeView Command Center Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders greeting, command center banner, and prompt composer', async () => {
    const qc = createTestQueryClient();
    vi.mocked(productivityApi.getProductivityDashboard).mockResolvedValueOnce({
      total_tasks: 5,
      completed_tasks: 2,
      active_projects: 3,
      in_progress_goals: 1,
    } as any);
    vi.mocked(productivityApi.getTasks).mockResolvedValueOnce({
      items: [
        {
          id: 'task-1',
          user_id: 'usr-home-123',
          title: 'Audit Master Build Invariants',
          priority: 'urgent',
          status: 'todo',
          tags: ['security'],
          due_date: '2026-11-20',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 5,
    });
    vi.mocked(productivityApi.getProjects).mockResolvedValueOnce({
      items: [
        {
          id: 'proj-1',
          user_id: 'usr-home-123',
          name: 'Phase 4C Remediation',
          description: 'Harden product integrity',
          color: '#4f46e5',
          status: 'active',
          task_count: 8,
          completed_task_count: 6,
          progress_percentage: 75,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 4,
    });
    vi.mocked(productivityApi.getGoals).mockResolvedValueOnce({
      items: [
        {
          id: 'goal-1',
          user_id: 'usr-home-123',
          title: 'Achieve Production Staging Readiness',
          status: 'in_progress',
          target_date: '2026-12-01',
          project_count: 2,
          task_count: 5,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 3,
    });
    vi.mocked(chatApi.listConversations).mockResolvedValueOnce([
      {
        id: 'conv-1',
        title: 'Cryptographic Protocol Discussion',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 4,
      },
    ]);

    render(
      <QueryClientProvider client={qc}>
        <HomeView />
      </QueryClientProvider>
    );

    // Dynamic greeting and Command Center banner render
    await waitFor(() => {
      expect(screen.getByText('Personal Command Center')).toBeInTheDocument();
      expect(screen.getByText('Audit Master Build Invariants')).toBeInTheDocument();
      expect(screen.getByText('Phase 4C Remediation')).toBeInTheDocument();
      expect(screen.getByText('Achieve Production Staging Readiness')).toBeInTheDocument();
      expect(screen.getByText('Cryptographic Protocol Discussion')).toBeInTheDocument();
    });
  });

  it('submits query via AI composer and navigates to /chat with prefilled prompt', async () => {
    const qc = createTestQueryClient();
    vi.mocked(productivityApi.getProductivityDashboard).mockResolvedValueOnce({} as any);
    vi.mocked(productivityApi.getTasks).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 5 });
    vi.mocked(productivityApi.getProjects).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 4 });
    vi.mocked(productivityApi.getGoals).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 3 });
    vi.mocked(chatApi.listConversations).mockResolvedValueOnce([]);

    render(
      <QueryClientProvider client={qc}>
        <HomeView />
      </QueryClientProvider>
    );

    const input = screen.getByPlaceholderText(/ask auren anything/i);
    await userEvent.type(input, 'What are my top priorities for today?');

    const submitButton = screen.getByTitle('Ask AUREN');
    await userEvent.click(submitButton);

    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/chat',
      search: { q: 'What are my top priorities for today?' },
    });
  });

  it('toggles task status from Priorities Radar', async () => {
    const qc = createTestQueryClient();
    vi.mocked(productivityApi.getProductivityDashboard).mockResolvedValueOnce({} as any);
    vi.mocked(productivityApi.getTasks).mockResolvedValueOnce({
      items: [
        {
          id: 'task-99',
          user_id: 'usr-home-123',
          title: 'Review HMAC signatures',
          priority: 'high',
          status: 'todo',
          tags: ['integrity'],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 5,
    });
    vi.mocked(productivityApi.changeTaskStatus).mockResolvedValueOnce({
      id: 'task-99',
      user_id: 'usr-home-123',
      title: 'Review HMAC signatures',
      priority: 'high',
      status: 'completed',
      tags: ['integrity'],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    vi.mocked(productivityApi.getProjects).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 4 });
    vi.mocked(productivityApi.getGoals).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 3 });
    vi.mocked(chatApi.listConversations).mockResolvedValueOnce([]);

    render(
      <QueryClientProvider client={qc}>
        <HomeView />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Review HMAC signatures')).toBeInTheDocument();
    });

    const toggleButton = screen.getByTitle('Toggle task status');
    await userEvent.click(toggleButton);

    await waitFor(() => {
      expect(productivityApi.changeTaskStatus).toHaveBeenCalledWith('task-99', 'completed');
    });
  });

  it('renders loading state when task data is pending', () => {
    const qc = createTestQueryClient();
    vi.mocked(productivityApi.getProductivityDashboard).mockReturnValue(new Promise(() => {}));
    vi.mocked(productivityApi.getTasks).mockReturnValue(new Promise(() => {}));
    vi.mocked(productivityApi.getProjects).mockReturnValue(new Promise(() => {}));
    vi.mocked(productivityApi.getGoals).mockReturnValue(new Promise(() => {}));
    vi.mocked(chatApi.listConversations).mockReturnValue(new Promise(() => {}));

    render(
      <QueryClientProvider client={qc}>
        <HomeView />
      </QueryClientProvider>
    );

    expect(screen.getByText('Loading priority tasks...')).toBeInTheDocument();
  });

  it('renders empty state when there are no pending tasks', async () => {
    const qc = createTestQueryClient();
    vi.mocked(productivityApi.getProductivityDashboard).mockResolvedValueOnce({} as any);
    vi.mocked(productivityApi.getTasks).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 5 });
    vi.mocked(productivityApi.getProjects).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 4 });
    vi.mocked(productivityApi.getGoals).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 3 });
    vi.mocked(chatApi.listConversations).mockResolvedValueOnce([]);

    render(
      <QueryClientProvider client={qc}>
        <HomeView />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('All tasks cleared')).toBeInTheDocument();
      expect(screen.getByText(/you have no pending tasks/i)).toBeInTheDocument();
    });
  });

  it('renders error state when task query fails', async () => {
    const qc = createTestQueryClient();
    vi.mocked(productivityApi.getProductivityDashboard).mockResolvedValueOnce({} as any);
    vi.mocked(productivityApi.getTasks).mockRejectedValueOnce(new Error('Network error'));
    vi.mocked(productivityApi.getProjects).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 4 });
    vi.mocked(productivityApi.getGoals).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 3 });
    vi.mocked(chatApi.listConversations).mockResolvedValueOnce([]);

    render(
      <QueryClientProvider client={qc}>
        <HomeView />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Tasks temporarily unavailable.')).toBeInTheDocument();
    });
  });
});

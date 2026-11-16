/**
 * Unit & Integration Tests for AUREN Phase 3C.4 Productivity Core:
 * TasksView, ProjectsView, GoalsView, and ProductivityDashboardView.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TasksView } from '../features/tasks/TasksView';
import { ProjectsView } from '../features/projects/ProjectsView';
import { GoalsView } from '../features/goals/GoalsView';
import { ProductivityDashboardView } from '../features/productivity/ProductivityDashboardView';
import * as productivityApi from '../api/productivity';

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual<any>('@tanstack/react-router');
  return {
    ...actual,
    Link: ({ children, to, className, ...props }: any) => (
      <a href={typeof to === 'string' ? to : '#'} className={className} {...props}>
        {children}
      </a>
    ),
  };
});

// Mock API module
vi.mock('../api/productivity', async () => {
  const actual = await vi.importActual('../api/productivity');
  return {
    ...actual,
    getTasks: vi.fn(),
    createTask: vi.fn(),
    updateTask: vi.fn(),
    changeTaskStatus: vi.fn(),
    deleteTask: vi.fn(),
    getProjects: vi.fn(),
    getProject: vi.fn(),
    createProject: vi.fn(),
    updateProject: vi.fn(),
    deleteProject: vi.fn(),
    getGoals: vi.fn(),
    getGoal: vi.fn(),
    createGoal: vi.fn(),
    updateGoal: vi.fn(),
    deleteGoal: vi.fn(),
    getProductivityDashboard: vi.fn(),
  };
});

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
}

const mockTasksResponse: productivityApi.TaskListResponse = {
  items: [
    {
      id: 'task-1',
      user_id: 'user-1',
      title: 'Review pull request #42',
      description: 'Check security and test coverage',
      status: 'todo',
      priority: 'high',
      project_id: 'proj-1',
      project_name: 'Core Security',
      due_date: new Date(Date.now() + 86400000).toISOString(),
      tags: ['security', 'review'],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      subtask_count: 0,
    },
    {
      id: 'task-2',
      user_id: 'user-1',
      title: 'Implement OAuth refresh token',
      description: null,
      status: 'completed',
      priority: 'urgent',
      project_id: 'proj-1',
      project_name: 'Core Security',
      completed_at: new Date().toISOString(),
      tags: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      subtask_count: 0,
    },
  ],
  total: 2,
  page: 1,
  page_size: 25,
};

const mockProjectsResponse: productivityApi.ProjectListResponse = {
  items: [
    {
      id: 'proj-1',
      user_id: 'user-1',
      name: 'Core Security Overhaul',
      description: 'Harden authentication, RLS, and session encryption',
      color: '#4872bd',
      status: 'active',
      start_date: '2026-11-01',
      target_date: '2026-12-01',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      task_count: 4,
      completed_task_count: 2,
      progress_percentage: 50.0,
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
};

const mockGoalsResponse: productivityApi.GoalListResponse = {
  items: [
    {
      id: 'goal-1',
      user_id: 'user-1',
      title: 'Achieve 99.9% Pipeline Reliability',
      description: 'Zero memory leaks and strict error recovery',
      status: 'in_progress',
      target_date: '2026-12-31',
      target_value: 100.0,
      current_value: 75.0,
      unit: '%',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      progress_percentage: 75.0,
      project_count: 2,
      task_count: 8,
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
};

const mockDashboardResponse: productivityApi.ProductivityDashboard = {
  active_tasks_count: 3,
  overdue_tasks_count: 1,
  completed_tasks_count: 5,
  active_projects_count: 2,
  active_goals_count: 1,
  overdue_tasks: [
    {
      id: 'task-overdue',
      user_id: 'user-1',
      title: 'Fix SSL Certificate Rotation',
      status: 'todo',
      priority: 'urgent',
      due_date: new Date(Date.now() - 86400000).toISOString(),
      project_name: 'Infrastructure',
      tags: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ],
  upcoming_tasks: [
    {
      id: 'task-upcoming',
      user_id: 'user-1',
      title: 'Prepare Phase 3C.4 Release Notes',
      status: 'in_progress',
      priority: 'high',
      due_date: new Date(Date.now() + 86400000).toISOString(),
      project_name: 'Core Security',
      tags: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ],
  active_projects: mockProjectsResponse.items,
  active_goals: mockGoalsResponse.items,
  recently_completed_tasks: [mockTasksResponse.items[1]],
};

describe('Productivity Core: Tasks View', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(productivityApi.getTasks).mockResolvedValue(mockTasksResponse);
    vi.mocked(productivityApi.getProjects).mockResolvedValue(mockProjectsResponse);
    vi.mocked(productivityApi.getGoals).mockResolvedValue(mockGoalsResponse);
  });

  it('renders task list with titles, status badges, and project pills', async () => {
    const qc = createTestQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <TasksView />
      </QueryClientProvider>
    );

    expect(screen.getByRole('heading', { name: 'Tasks & Timetable' })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Review pull request #42')).toBeInTheDocument();
      expect(screen.getByText('Implement OAuth refresh token')).toBeInTheDocument();
      expect(screen.getAllByText('Core Security')[0]).toBeInTheDocument();
    });
  });

  it('opens task creation modal on New Task button click', async () => {
    const user = userEvent.setup();
    const qc = createTestQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <TasksView />
      </QueryClientProvider>
    );

    const newBtn = screen.getByRole('button', { name: /new task/i });
    await user.click(newBtn);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Create New Task' })).toBeInTheDocument();
    });
  });

  it('toggles task completion status', async () => {
    const user = userEvent.setup();
    vi.mocked(productivityApi.changeTaskStatus).mockResolvedValue({
      ...mockTasksResponse.items[0],
      status: 'completed',
    });

    const qc = createTestQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <TasksView />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Review pull request #42')).toBeInTheDocument();
    });

    const completeBtn = screen.getByRole('button', { name: 'Mark completed' });
    await user.click(completeBtn);

    expect(productivityApi.changeTaskStatus).toHaveBeenCalledWith('task-1', 'completed');
  });
});

describe('Productivity Core: Projects View', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(productivityApi.getProjects).mockResolvedValue(mockProjectsResponse);
    vi.mocked(productivityApi.getGoals).mockResolvedValue(mockGoalsResponse);
  });

  it('renders project cards with derived progress percentage', async () => {
    const qc = createTestQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <ProjectsView />
      </QueryClientProvider>
    );

    expect(screen.getByRole('heading', { name: 'Project Workspaces' })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Core Security Overhaul')).toBeInTheDocument();
      expect(screen.getByText('50%')).toBeInTheDocument();
      expect(screen.getByText(/2 \/ 4 tasks completed/i)).toBeInTheDocument();
    });
  });

  it('opens project creation modal on New Project button click', async () => {
    const user = userEvent.setup();
    const qc = createTestQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <ProjectsView />
      </QueryClientProvider>
    );

    const newBtn = screen.getByRole('button', { name: /new project/i });
    await user.click(newBtn);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Create New Project' })).toBeInTheDocument();
    });
  });
});

describe('Productivity Core: Goals View', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(productivityApi.getGoals).mockResolvedValue(mockGoalsResponse);
  });

  it('renders strategic goals with target metrics and progress', async () => {
    const qc = createTestQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <GoalsView />
      </QueryClientProvider>
    );

    expect(screen.getByRole('heading', { name: 'Strategic Goals' })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Achieve 99.9% Pipeline Reliability')).toBeInTheDocument();
      expect(screen.getByText('75%')).toBeInTheDocument();
      expect(screen.getByText(/75 \/ 100 %/i)).toBeInTheDocument();
    });
  });
});

describe('Productivity Core: Overview Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(productivityApi.getProductivityDashboard).mockResolvedValue(mockDashboardResponse);
  });

  it('renders KPI summary cards and overdue commitment alerts', async () => {
    const qc = createTestQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <ProductivityDashboardView />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Productivity Overview' })).toBeInTheDocument();
      expect(screen.getByText('Fix SSL Certificate Rotation')).toBeInTheDocument();
      expect(screen.getByText('Prepare Phase 3C.4 Release Notes')).toBeInTheDocument();
      expect(screen.getByText('Core Security Overhaul')).toBeInTheDocument();
    });
  });
});

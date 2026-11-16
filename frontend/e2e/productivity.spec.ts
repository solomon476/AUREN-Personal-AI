import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession } from './helpers';

test.describe('Productivity Core E2E: Tasks, Projects, Goals & Dashboard', () => {
  let mockTasks: any[] = [];
  let mockProjects: any[] = [];
  let mockGoals: any[] = [];

  test.beforeEach(async ({ page }) => {
    mockProjects = [
      {
        id: 'proj-001',
        name: 'Core Infrastructure Overhaul',
        description: 'Upgrade PostgreSQL migrations, asyncpg pooling, and domain services.',
        status: 'active',
        color: '#6366f1',
        start_date: '2026-11-01',
        target_date: '2026-11-30',
        goal_id: 'goal-001',
        progress_percentage: 50.0,
        task_count: 2,
        completed_task_count: 1,
        created_at: '2026-11-01T10:00:00Z',
        updated_at: '2026-11-16T12:00:00Z',
      },
    ];

    mockTasks = [
      {
        id: 'task-001',
        title: 'Implement Forward-Only Schema Migration',
        description: 'Create migration 019 for productivity schema alignment.',
        status: 'completed',
        priority: 'high',
        due_date: '2026-11-16',
        start_date: '2026-11-15',
        completed_at: '2026-11-16T10:00:00Z',
        project_id: 'proj-001',
        project_name: 'Core Infrastructure Overhaul',
        goal_id: 'goal-001',
        tags: ['database', 'migration'],
        created_at: '2026-11-15T09:00:00Z',
        updated_at: '2026-11-16T10:00:00Z',
      },
      {
        id: 'task-002',
        title: 'Verify RLS Tenant Isolation',
        description: 'Test that users cannot link records across accounts.',
        status: 'in_progress',
        priority: 'urgent',
        due_date: '2026-11-17',
        start_date: '2026-11-16',
        completed_at: null,
        project_id: 'proj-001',
        project_name: 'Core Infrastructure Overhaul',
        goal_id: 'goal-001',
        tags: ['security', 'rls'],
        created_at: '2026-11-16T09:00:00Z',
        updated_at: '2026-11-16T09:00:00Z',
      },
    ];

    mockGoals = [
      {
        id: 'goal-001',
        title: 'Deliver Production-Grade Productivity Core',
        description: 'Complete Phase 3C.4 with comprehensive verification.',
        status: 'in_progress',
        target_date: '2026-11-30',
        completed_at: null,
        target_value: 100,
        current_value: 80,
        unit: '%',
        progress_percentage: 80.0,
        projects_count: 1,
        tasks_count: 2,
        completed_tasks_count: 1,
        created_at: '2026-11-01T08:00:00Z',
        updated_at: '2026-11-16T14:00:00Z',
      },
    ];

    await setupAuthenticatedSession(page);

    // Mock Tasks API
    await page.route('**/api/v1/tasks*', async (route) => {
      const request = route.request();
      const method = request.method();
      const url = new URL(request.url());

      if (method === 'GET' && url.pathname.endsWith('/tasks')) {
        const statusParam = url.searchParams.get('status');
        let filtered = [...mockTasks];
        if (statusParam) {
          filtered = filtered.filter((t) => t.status === statusParam);
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: filtered,
            total: filtered.length,
            page: 1,
            page_size: 50,
            has_more: false,
          }),
        });
      } else if (method === 'POST' && url.pathname.endsWith('/tasks')) {
        const payload = JSON.parse(request.postData() || '{}');
        const newTask = {
          id: `task-${Date.now()}`,
          title: payload.title,
          description: payload.description || null,
          status: payload.status || 'todo',
          priority: payload.priority || 'medium',
          due_date: payload.due_date || null,
          start_date: payload.start_date || null,
          completed_at: null,
          project_id: payload.project_id || null,
          project_name: payload.project_id ? 'Core Infrastructure Overhaul' : null,
          goal_id: payload.goal_id || null,
          parent_task_id: null,
          tags: payload.tags || [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        mockTasks.unshift(newTask);
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(newTask),
        });
      } else if (method === 'PATCH' && url.pathname.includes('/status')) {
        const match = url.pathname.match(/\/tasks\/([^/]+)\/status/);
        const taskId = match ? match[1] : '';
        const payload = JSON.parse(request.postData() || '{}');
        const task = mockTasks.find((t) => t.id === taskId);
        if (task) {
          task.status = payload.status;
          task.updated_at = new Date().toISOString();
          if (payload.status === 'completed') {
            task.completed_at = new Date().toISOString();
          } else {
            task.completed_at = null;
          }
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(task || {}),
        });
      } else {
        await route.continue();
      }
    });

    // Mock Projects API
    await page.route('**/api/v1/projects*', async (route) => {
      const request = route.request();
      const method = request.method();
      const url = new URL(request.url());

      if (method === 'GET' && url.pathname.endsWith('/projects')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: mockProjects,
            total: mockProjects.length,
            page: 1,
            page_size: 50,
            has_more: false,
          }),
        });
      } else if (method === 'POST' && url.pathname.endsWith('/projects')) {
        const payload = JSON.parse(request.postData() || '{}');
        const newProj = {
          id: `proj-${Date.now()}`,
          name: payload.name,
          description: payload.description || null,
          status: payload.status || 'planning',
          color: payload.color || '#6366f1',
          start_date: payload.start_date || null,
          target_date: payload.target_date || null,
          goal_id: payload.goal_id || null,
          progress_percentage: 0.0,
          task_count: 0,
          completed_task_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        mockProjects.unshift(newProj);
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(newProj),
        });
      } else {
        await route.continue();
      }
    });

    // Mock Goals API
    await page.route('**/api/v1/goals*', async (route) => {
      const request = route.request();
      const method = request.method();
      const url = new URL(request.url());

      if (method === 'GET' && url.pathname.endsWith('/goals')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: mockGoals,
            total: mockGoals.length,
            page: 1,
            page_size: 50,
            has_more: false,
          }),
        });
      } else if (method === 'POST' && url.pathname.endsWith('/goals')) {
        const payload = JSON.parse(request.postData() || '{}');
        const newGoal = {
          id: `goal-${Date.now()}`,
          title: payload.title,
          description: payload.description || null,
          status: payload.status || 'in_progress',
          target_date: payload.target_date || null,
          completed_at: null,
          target_value: payload.target_value ?? null,
          current_value: payload.current_value ?? 0,
          unit: payload.unit || null,
          progress_percentage: payload.target_value ? (payload.current_value / payload.target_value) * 100 : 0.0,
          projects_count: 0,
          tasks_count: 0,
          completed_tasks_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        mockGoals.unshift(newGoal);
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(newGoal),
        });
      } else {
        await route.continue();
      }
    });

    // Mock Productivity Dashboard API
    await page.route('**/api/v1/productivity/dashboard*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active_tasks_count: 1,
          overdue_tasks_count: 1,
          completed_tasks_count: 1,
          active_projects_count: 1,
          active_goals_count: 1,
          upcoming_tasks: [
            {
              id: 'task-002',
              title: 'Verify RLS Tenant Isolation',
              status: 'in_progress',
              priority: 'urgent',
              due_date: '2026-11-17',
              project_name: 'Core Infrastructure Overhaul',
              tags: ['security', 'rls'],
              created_at: '2026-11-16T09:00:00Z',
              updated_at: '2026-11-16T09:00:00Z',
            },
          ],
          overdue_tasks: [
            {
              id: 'task-overdue-1',
              title: 'Fix SSL Certificate Rotation',
              status: 'in_progress',
              priority: 'urgent',
              due_date: '2026-11-10',
              project_name: 'Core Infrastructure Overhaul',
              tags: ['security'],
              created_at: '2026-11-01T09:00:00Z',
              updated_at: '2026-11-10T09:00:00Z',
            },
          ],
          active_projects: mockProjects,
          active_goals: mockGoals,
          recently_completed_tasks: [mockTasks[0]],
        }),
      });
    });
  });

  test('navigates to Tasks view and renders persisted tasks with filtering', async ({ page }) => {
    await page.goto('/chat');
    const tasksLink = page.getByRole('link', { name: /tasks & timetable/i });
    await expect(tasksLink).toBeVisible();
    await tasksLink.click();

    await expect(page).toHaveURL(/\/tasks/);
    await expect(page.getByRole('heading', { name: 'Tasks & Timetable' })).toBeVisible();
    await expect(page.getByText('Implement Forward-Only Schema Migration')).toBeVisible();
    await expect(page.getByText('Verify RLS Tenant Isolation')).toBeVisible();

    // Filter by completed
    const completedTab = page.getByRole('button', { name: 'Completed', exact: true });
    await completedTab.click();
    await expect(page.getByText('Implement Forward-Only Schema Migration')).toBeVisible();
    await expect(page.getByText('Verify RLS Tenant Isolation')).not.toBeVisible();
  });

  test('creates a new task via modal and verifies persistence in list', async ({ page }) => {
    await page.goto('/tasks');
    await expect(page.getByRole('heading', { name: 'Tasks & Timetable' })).toBeVisible();

    // Click New Task button
    const newTaskBtn = page.getByRole('button', { name: /new task/i });
    await expect(newTaskBtn).toBeVisible();
    await newTaskBtn.click();

    // Fill form in modal
    await expect(page.getByText('Create New Task')).toBeVisible();
    await page.getByPlaceholder('What needs to be done?').fill('Write Playwright E2E Tests');
    await page.getByPlaceholder('Add details, notes, or acceptance criteria...').fill('Comprehensive browser tests for productivity core');

    // Submit form
    const createBtn = page.getByRole('button', { name: /create task/i });
    await createBtn.click();

    // Verify task appears in list
    await expect(page.getByText('Write Playwright E2E Tests')).toBeVisible();
  });

  test('navigates to Projects workspace and displays derived progress', async ({ page }) => {
    await page.goto('/chat');
    const projectsLink = page.getByRole('link', { name: /projects/i });
    await expect(projectsLink).toBeVisible();
    await projectsLink.click();

    await expect(page).toHaveURL(/\/projects/);
    await expect(page.getByRole('heading', { name: 'Project Workspaces' })).toBeVisible();
    await expect(page.getByText('Core Infrastructure Overhaul')).toBeVisible();
    await expect(page.getByText('50%')).toBeVisible();
    await expect(page.getByText(/1 \/ 2 tasks completed/i)).toBeVisible();

    // Open project modal
    const newProjBtn = page.getByRole('button', { name: /new project/i });
    await newProjBtn.click();
    await expect(page.getByText('Create Project')).toBeVisible();
    await page.getByPlaceholder('e.g. AUREN Engine 2.0').fill('Next-Gen UI Experience');
    await page.getByRole('button', { name: /create project/i }).click();

    await expect(page.getByText('Next-Gen UI Experience')).toBeVisible();
  });

  test('navigates to Strategic Goals and displays progress metrics', async ({ page }) => {
    await page.goto('/chat');
    const goalsLink = page.getByRole('link', { name: /goals & milestones/i });
    await expect(goalsLink).toBeVisible();
    await goalsLink.click();

    await expect(page).toHaveURL(/\/goals/);
    await expect(page.getByRole('heading', { name: 'Strategic Goals' })).toBeVisible();
    await expect(page.getByText('Deliver Production-Grade Productivity Core')).toBeVisible();
    await expect(page.getByText('80%')).toBeVisible();
    await expect(page.getByText(/80 \/ 100 %/i)).toBeVisible();

    // Open goal modal
    const newGoalBtn = page.getByRole('button', { name: /new goal/i });
    await newGoalBtn.click();
    await expect(page.getByText('Create Strategic Goal')).toBeVisible();
    await page.getByPlaceholder('e.g. Master High-Performance Go & Rust').fill('Publish Documentation Suite');
    await page.getByRole('button', { name: /create goal/i }).click();

    await expect(page.getByText('Publish Documentation Suite')).toBeVisible();
  });

  test('navigates to Productivity Dashboard and renders live aggregated KPIs', async ({ page }) => {
    await page.goto('/productivity');
    await expect(page.getByRole('heading', { name: 'Productivity Overview' })).toBeVisible();

    // Verify KPI summary cards
    await expect(page.locator('span', { hasText: 'Active Tasks' })).toBeVisible();
    await expect(page.locator('span', { hasText: 'Active Projects' })).toBeVisible();
    await expect(page.locator('span', { hasText: 'Active Goals' })).toBeVisible();
    await expect(page.locator('span', { hasText: 'Overdue Tasks' })).toBeVisible();

    // Verify overdue & upcoming tasks
    await expect(page.getByText('Fix SSL Certificate Rotation')).toBeVisible();
    await expect(page.getByText('Verify RLS Tenant Isolation')).toBeVisible();
  });
});

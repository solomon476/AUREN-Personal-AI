/**
 * Application Routing Architecture using TanStack Router.
 * Establishes typed routes, layout nesting, bookmarkable URLs,
 * and unified command center integration across all six product areas.
 */

import {
  createRouter,
  createRoute,
  createRootRoute,
  redirect,
} from '@tanstack/react-router';
import { AppLayout } from './components/layout/AppLayout';
import { HomeView } from './features/home/HomeView';
import { ChatView } from './features/chat/ChatView';
import { MemoryView } from './features/memory/MemoryView';
import { TasksView } from './features/tasks/TasksView';
import { ProjectsView } from './features/projects/ProjectsView';
import { GoalsView } from './features/goals/GoalsView';
import { ProductivityDashboardView } from './features/productivity/ProductivityDashboardView';
import { OmnisearchView } from './features/search/OmnisearchView';
import { ReflectionView } from './features/reflection/ReflectionView';
import { JournalView } from './features/journal/JournalView';
import { SettingsView } from './features/settings/SettingsView';
import { OperationsView } from './features/operations/OperationsView';
import { NotFound } from './components/common/NotFound';

// Root Application Route with Shared Shell Layout
export const rootRoute = createRootRoute({
  component: AppLayout,
  notFoundComponent: NotFound,
});

// Index Route: Redirects to /home (Personal AI Command Center)
export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    throw redirect({ to: '/home' });
  },
});

// Area 1: Home — Personal Command Center (/home)
export const homeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/home',
  component: HomeView,
});

// Area 2: Assistant — Central AI Intelligence (/chat and /chat/$conversationId)
export const chatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/chat',
  validateSearch: (search: Record<string, unknown>): { q?: string; prompt?: string } => ({
    q: typeof search.q === 'string' ? search.q : undefined,
    prompt: typeof search.prompt === 'string' ? search.prompt : undefined,
  }),
  component: ChatView,
});

export const conversationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/chat/$conversationId',
  component: ChatView,
});

// Area 3: Memory — Personal Knowledge and Context (/memories)
export const memoriesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/memories',
  component: MemoryView,
});

// Area 4: Life Management — Tasks, Projects, and Goals
export const tasksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/tasks',
  validateSearch: (search: Record<string, unknown>): { project_id?: string; goal_id?: string } => ({
    project_id: typeof search.project_id === 'string' ? search.project_id : undefined,
    goal_id: typeof search.goal_id === 'string' ? search.goal_id : undefined,
  }),
  component: TasksView,
});

export const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/projects',
  validateSearch: (search: Record<string, unknown>): { project_id?: string } => ({
    project_id: typeof search.project_id === 'string' ? search.project_id : undefined,
  }),
  component: ProjectsView,
});

export const goalsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/goals',
  component: GoalsView,
});

export const productivityRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/productivity',
  component: ProductivityDashboardView,
});

// Area 5: Reflection & Journal — Private Journal and Reflective Intelligence
export const journalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/journal',
  component: JournalView,
});

export const reflectionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/reflection',
  component: ReflectionView,
});

// Area 6: Settings — Privacy, Preferences and Control (/settings)
export const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/settings',
  component: SettingsView,
});

// Search Route
export const searchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/search',
  component: OmnisearchView,
});

// Legacy /system redirected to /settings
export const systemRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system',
  beforeLoad: () => {
    throw redirect({ to: '/settings' });
  },
  component: () => null,
});

// Area 7: Operations & GPS Hub (/operations)
export const operationsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/operations',
  component: OperationsView,
});

// Route Tree Definition
export const routeTree = rootRoute.addChildren([
  indexRoute,
  homeRoute,
  chatRoute,
  conversationRoute,
  memoriesRoute,
  tasksRoute,
  projectsRoute,
  goalsRoute,
  productivityRoute,
  journalRoute,
  reflectionRoute,
  settingsRoute,
  searchRoute,
  systemRoute,
  operationsRoute,
]);

export function createAppRouter() {
  return createRouter({
    routeTree,
    defaultPreload: 'intent',
  });
}

export const router = createAppRouter();

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

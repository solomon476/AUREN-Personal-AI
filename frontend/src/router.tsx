/**
 * Application Routing Architecture using TanStack Router.
 * Establishes typed routes, layout nesting, bookmarkable conversation URLs, and roadmap destinations.
 */

import {
  createRouter,
  createRoute,
  createRootRoute,
  redirect,
} from '@tanstack/react-router';
import {
  BookOpen,
  Settings,
} from 'lucide-react';
import { AppLayout } from './components/layout/AppLayout';
import { ChatView } from './features/chat/ChatView';
import { SystemView } from './features/system/SystemView';
import { MemoryView } from './features/memory/MemoryView';
import { TasksView } from './features/tasks/TasksView';
import { ProjectsView } from './features/projects/ProjectsView';
import { GoalsView } from './features/goals/GoalsView';
import { ProductivityDashboardView } from './features/productivity/ProductivityDashboardView';
import { OmnisearchView } from './features/search/OmnisearchView';
import { ReflectionView } from './features/reflection/ReflectionView';
import { SectionPlaceholder } from './components/placeholders/SectionPlaceholder';
import { NotFound } from './components/common/NotFound';

// Root Application Route with Shared Shell Layout
export const rootRoute = createRootRoute({
  component: AppLayout,
  notFoundComponent: NotFound,
});

// Index Route: Redirects to /chat
export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    throw redirect({ to: '/chat' });
  },
});

// Active Chat View (New Dialogue or Default)
export const chatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/chat',
  component: ChatView,
});

// Specific Conversation Route (/chat/$conversationId)
export const conversationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/chat/$conversationId',
  component: ChatView,
});

// System & Database Health Route
export const systemRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/system',
  component: SystemView,
});

// Long-term Memory Explorer & Epistemic Verification (Phase 3C.3)
export const memoriesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/memories',
  component: MemoryView,
});

// Tasks & Timetable Management (Phase 3C.4)
export const tasksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/tasks',
  component: TasksView,
});

// Projects Workspace Management (Phase 3C.4)
export const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/projects',
  component: ProjectsView,
});

// Strategic Goals & Milestones Management (Phase 3C.4)
export const goalsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/goals',
  component: GoalsView,
});

// Productivity Overview Dashboard (Phase 3C.4)
export const productivityRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/productivity',
  component: ProductivityDashboardView,
});

// Omnisearch — Phase 3C.5
export const searchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/search',
  component: OmnisearchView,
});

// Reflective Intelligence — Phase 3C.5
export const reflectionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/reflection',
  component: ReflectionView,
});

// Private Journaling Placeholder (Phase 3C.5)
export const journalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/journal',
  component: () => (
    <SectionPlaceholder
      title="Private Journaling & Moods"
      icon={BookOpen}
      badge="Consent Protected"
      phase="Phase 3C.5"
      description="Private daily reflections with mood analysis and cryptographic consent guarantees."
      backendStatus="Active: PostgreSQL journal_entries table with RFC 8785 canonical JSON and HMAC signing"
      plannedFeatures={[
        'Distraction-free Markdown Reflection Editor',
        'Mood & Sentiment Trend Tracking',
        'Private Epistemic Reflections',
      ]}
    />
  ),
});

// Settings Placeholder
export const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/settings',
  component: () => (
    <SectionPlaceholder
      title="Settings & Preferences"
      icon={Settings}
      badge="Configuration"
      phase="Phase 3C.2 / 3C.3"
      description="Manage AI persona, model preferences, Supabase credentials, and data privacy settings."
      backendStatus="Active: profiles table with user metadata and preferences"
      plannedFeatures={[
        'LLM Provider & Model Selection',
        'Memory Retention & Privacy Policies',
        'Data Export & Account Management',
      ]}
    />
  ),
});

// Route Tree Definition
export const routeTree = rootRoute.addChildren([
  indexRoute,
  chatRoute,
  conversationRoute,
  systemRoute,
  memoriesRoute,
  tasksRoute,
  projectsRoute,
  goalsRoute,
  productivityRoute,
  searchRoute,
  reflectionRoute,
  journalRoute,
  settingsRoute,
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

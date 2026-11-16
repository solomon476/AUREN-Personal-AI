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
  CheckSquare,
  FolderKanban,
  Target,
  BookOpen,
  Settings,
} from 'lucide-react';
import { AppLayout } from './components/layout/AppLayout';
import { ChatView } from './features/chat/ChatView';
import { SystemView } from './features/system/SystemView';
import { MemoryView } from './features/memory/MemoryView';
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

// Tasks & Timetable Placeholder (Phase 3C.4)
export const tasksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/tasks',
  component: () => (
    <SectionPlaceholder
      title="Tasks & Timetable"
      icon={CheckSquare}
      badge="Schema Ready"
      phase="Phase 3C.4"
      description="Personal task management with timetable scheduling, priority tiers, and due date tracking."
      backendStatus="Active: PostgreSQL tasks table with user-isolated RLS"
      plannedFeatures={[
        'Task Board (Pending, In Progress, Completed)',
        'Priority Filtering (Low, Medium, High, Urgent)',
        'Due Date Reminders & Timetable',
        'AI-Assisted Task Breakdown from Dialogues',
      ]}
    />
  ),
});

// Projects Workspace Placeholder (Phase 3C.4)
export const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/projects',
  component: () => (
    <SectionPlaceholder
      title="Project Workspaces"
      icon={FolderKanban}
      badge="Schema Ready"
      phase="Phase 3C.4"
      description="Focused project spaces to group conversations, memories, and tasks into coherent workstreams."
      backendStatus="Active: PostgreSQL projects table with user-isolated RLS"
      plannedFeatures={[
        'Custom Project Workspaces with Color & Icon tagging',
        'Project-bound Conversations & Task association',
        'Cross-project Intelligence & Status Summaries',
      ]}
    />
  ),
});

// Goals & Milestones Placeholder (Phase 3C.4)
export const goalsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/goals',
  component: () => (
    <SectionPlaceholder
      title="Personal Goals & Milestones"
      icon={Target}
      badge="Schema Ready"
      phase="Phase 3C.4"
      description="Long-range personal and professional goals with measurable milestone tracking."
      backendStatus="Active: PostgreSQL goals and milestones tables with RLS"
      plannedFeatures={[
        'Strategic Goal Roadmaps',
        'Measurable Milestone Checklists',
        'AI Progress Reflection & Review',
      ]}
    />
  ),
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

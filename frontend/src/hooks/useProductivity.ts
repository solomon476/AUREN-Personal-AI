/**
 * TanStack Query hooks for Tasks, Projects, Goals, and Dashboard state management.
 * Enforces user-scoped query keys to ensure tenant isolation and cache integrity.
 */

import { useContext } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AuthContext } from '../context/AuthContext';
import {
  changeGoalStatus,
  changeProjectStatus,
  changeTaskStatus,
  createGoal,
  createProject,
  createTask,
  deleteGoal,
  deleteProject,
  deleteTask,
  getGoal,
  getGoals,
  getProductivityDashboard,
  getProject,
  getProjects,
  getTask,
  getTasks,
  updateGoal,
  updateProject,
  updateTask,
  GoalCreateInput,
  GoalStatus,
  GoalUpdateInput,
  ProjectCreateInput,
  ProjectStatus,
  ProjectUpdateInput,
  TaskCreateInput,
  TaskStatus,
  TaskUpdateInput,
} from '../api/productivity';

/**
 * Safely resolves the current authenticated user ID without throwing outside AuthProvider.
 */
export function useCurrentUserId(explicitUserId?: string): string {
  const auth = useContext(AuthContext);
  return explicitUserId ?? auth?.user?.id ?? 'anonymous';
}

export const PRODUCTIVITY_KEYS = {
  all: ['productivity'] as const,
  tasks: (userId?: string) => ['productivity', 'tasks', userId ?? 'anonymous'] as const,
  task: (id: string, userId?: string) => ['productivity', 'tasks', userId ?? 'anonymous', id] as const,
  projects: (userId?: string) => ['productivity', 'projects', userId ?? 'anonymous'] as const,
  project: (id: string, userId?: string) => ['productivity', 'projects', userId ?? 'anonymous', id] as const,
  goals: (userId?: string) => ['productivity', 'goals', userId ?? 'anonymous'] as const,
  goal: (id: string, userId?: string) => ['productivity', 'goals', userId ?? 'anonymous', id] as const,
  dashboard: (userId?: string) => ['productivity', 'dashboard', userId ?? 'anonymous'] as const,
};

// ============================================================================
// Task Hooks
// ============================================================================

export function useTasks(
  params?: {
    project_id?: string;
    goal_id?: string;
    status?: string;
    priority?: string;
    query?: string;
    parent_task_id?: string;
    page?: number;
    page_size?: number;
  },
  userId?: string
) {
  const currentUserId = useCurrentUserId(userId);
  return useQuery({
    queryKey: [...PRODUCTIVITY_KEYS.tasks(currentUserId), params],
    queryFn: () => getTasks(params),
    staleTime: 1000 * 30,
  });
}

export function useTask(taskId?: string, userId?: string) {
  const currentUserId = useCurrentUserId(userId);
  return useQuery({
    queryKey: PRODUCTIVITY_KEYS.task(taskId || '', currentUserId),
    queryFn: () => getTask(taskId!),
    enabled: Boolean(taskId),
  });
}

export function useCreateTask(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: (input: TaskCreateInput) => createTask(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

export function useUpdateTask(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: ({ taskId, input }: { taskId: string; input: TaskUpdateInput }) =>
      updateTask(taskId, input),
    onSuccess: (_, { taskId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.task(taskId, currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

export function useChangeTaskStatus(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: ({ taskId, newStatus }: { taskId: string; newStatus: TaskStatus }) =>
      changeTaskStatus(taskId, newStatus),
    onSuccess: (_, { taskId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.task(taskId, currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

export function useDeleteTask(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: (taskId: string) => deleteTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

// ============================================================================
// Project Hooks
// ============================================================================

export function useProjects(
  params?: {
    status?: string;
    goal_id?: string;
    query?: string;
    page?: number;
    page_size?: number;
  },
  userId?: string
) {
  const currentUserId = useCurrentUserId(userId);
  return useQuery({
    queryKey: [...PRODUCTIVITY_KEYS.projects(currentUserId), params],
    queryFn: () => getProjects(params),
    staleTime: 1000 * 30,
  });
}

export function useProject(projectId?: string, userId?: string) {
  const currentUserId = useCurrentUserId(userId);
  return useQuery({
    queryKey: PRODUCTIVITY_KEYS.project(projectId || '', currentUserId),
    queryFn: () => getProject(projectId!),
    enabled: Boolean(projectId),
  });
}

export function useCreateProject(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: (input: ProjectCreateInput) => createProject(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

export function useUpdateProject(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: ({ projectId, input }: { projectId: string; input: ProjectUpdateInput }) =>
      updateProject(projectId, input),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.project(projectId, currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

export function useChangeProjectStatus(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: ({ projectId, newStatus }: { projectId: string; newStatus: ProjectStatus }) =>
      changeProjectStatus(projectId, newStatus),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.project(projectId, currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

export function useDeleteProject(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: ({ projectId, deleteTasks }: { projectId: string; deleteTasks?: boolean }) =>
      deleteProject(projectId, deleteTasks),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

// ============================================================================
// Goal Hooks
// ============================================================================

export function useGoals(
  params?: {
    status?: string;
    query?: string;
    page?: number;
    page_size?: number;
  },
  userId?: string
) {
  const currentUserId = useCurrentUserId(userId);
  return useQuery({
    queryKey: [...PRODUCTIVITY_KEYS.goals(currentUserId), params],
    queryFn: () => getGoals(params),
    staleTime: 1000 * 30,
  });
}

export function useGoal(goalId?: string, userId?: string) {
  const currentUserId = useCurrentUserId(userId);
  return useQuery({
    queryKey: PRODUCTIVITY_KEYS.goal(goalId || '', currentUserId),
    queryFn: () => getGoal(goalId!),
    enabled: Boolean(goalId),
  });
}

export function useCreateGoal(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: (input: GoalCreateInput) => createGoal(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goals(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

export function useUpdateGoal(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: ({ goalId, input }: { goalId: string; input: GoalUpdateInput }) =>
      updateGoal(goalId, input),
    onSuccess: (_, { goalId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goals(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goal(goalId, currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

export function useChangeGoalStatus(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: ({ goalId, newStatus }: { goalId: string; newStatus: GoalStatus }) =>
      changeGoalStatus(goalId, newStatus),
    onSuccess: (_, { goalId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goals(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goal(goalId, currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

export function useDeleteGoal(userId?: string) {
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId(userId);
  return useMutation({
    mutationFn: (goalId: string) => deleteGoal(goalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goals(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks(currentUserId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId) });
    },
  });
}

// ============================================================================
// Dashboard Hook
// ============================================================================

export function useProductivityDashboard(userId?: string) {
  const currentUserId = useCurrentUserId(userId);
  return useQuery({
    queryKey: PRODUCTIVITY_KEYS.dashboard(currentUserId),
    queryFn: getProductivityDashboard,
    staleTime: 1000 * 20,
  });
}

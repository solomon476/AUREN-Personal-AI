/**
 * TanStack Query hooks for Tasks, Projects, Goals, and Dashboard state management.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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

export const PRODUCTIVITY_KEYS = {
  tasks: ['tasks'] as const,
  task: (id: string) => ['tasks', id] as const,
  projects: ['projects'] as const,
  project: (id: string) => ['projects', id] as const,
  goals: ['goals'] as const,
  goal: (id: string) => ['goals', id] as const,
  dashboard: ['productivity-dashboard'] as const,
};

// ============================================================================
// Task Hooks
// ============================================================================

export function useTasks(params?: {
  project_id?: string;
  goal_id?: string;
  status?: string;
  priority?: string;
  query?: string;
  parent_task_id?: string;
  page?: number;
  page_size?: number;
}) {
  return useQuery({
    queryKey: [...PRODUCTIVITY_KEYS.tasks, params],
    queryFn: () => getTasks(params),
    staleTime: 1000 * 30,
  });
}

export function useTask(taskId?: string) {
  return useQuery({
    queryKey: PRODUCTIVITY_KEYS.task(taskId || ''),
    queryFn: () => getTask(taskId!),
    enabled: Boolean(taskId),
  });
}

export function useCreateTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: TaskCreateInput) => createTask(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

export function useUpdateTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, input }: { taskId: string; input: TaskUpdateInput }) =>
      updateTask(taskId, input),
    onSuccess: (_, { taskId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.task(taskId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

export function useChangeTaskStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, newStatus }: { taskId: string; newStatus: TaskStatus }) =>
      changeTaskStatus(taskId, newStatus),
    onSuccess: (_, { taskId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.task(taskId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

export function useDeleteTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => deleteTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

// ============================================================================
// Project Hooks
// ============================================================================

export function useProjects(params?: {
  status?: string;
  goal_id?: string;
  query?: string;
  page?: number;
  page_size?: number;
}) {
  return useQuery({
    queryKey: [...PRODUCTIVITY_KEYS.projects, params],
    queryFn: () => getProjects(params),
    staleTime: 1000 * 30,
  });
}

export function useProject(projectId?: string) {
  return useQuery({
    queryKey: PRODUCTIVITY_KEYS.project(projectId || ''),
    queryFn: () => getProject(projectId!),
    enabled: Boolean(projectId),
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ProjectCreateInput) => createProject(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

export function useUpdateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, input }: { projectId: string; input: ProjectUpdateInput }) =>
      updateProject(projectId, input),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.project(projectId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

export function useChangeProjectStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, newStatus }: { projectId: string; newStatus: ProjectStatus }) =>
      changeProjectStatus(projectId, newStatus),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.project(projectId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, deleteTasks }: { projectId: string; deleteTasks?: boolean }) =>
      deleteProject(projectId, deleteTasks),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

// ============================================================================
// Goal Hooks
// ============================================================================

export function useGoals(params?: {
  status?: string;
  query?: string;
  page?: number;
  page_size?: number;
}) {
  return useQuery({
    queryKey: [...PRODUCTIVITY_KEYS.goals, params],
    queryFn: () => getGoals(params),
    staleTime: 1000 * 30,
  });
}

export function useGoal(goalId?: string) {
  return useQuery({
    queryKey: PRODUCTIVITY_KEYS.goal(goalId || ''),
    queryFn: () => getGoal(goalId!),
    enabled: Boolean(goalId),
  });
}

export function useCreateGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: GoalCreateInput) => createGoal(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goals });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

export function useUpdateGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ goalId, input }: { goalId: string; input: GoalUpdateInput }) =>
      updateGoal(goalId, input),
    onSuccess: (_, { goalId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goals });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goal(goalId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

export function useChangeGoalStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ goalId, newStatus }: { goalId: string; newStatus: GoalStatus }) =>
      changeGoalStatus(goalId, newStatus),
    onSuccess: (_, { goalId }) => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goals });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goal(goalId) });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

export function useDeleteGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (goalId: string) => deleteGoal(goalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.goals });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.projects });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.tasks });
      queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard });
    },
  });
}

// ============================================================================
// Dashboard Hook
// ============================================================================

export function useProductivityDashboard() {
  return useQuery({
    queryKey: PRODUCTIVITY_KEYS.dashboard,
    queryFn: getProductivityDashboard,
    staleTime: 1000 * 20,
  });
}


/**
 * Productivity Core API client for Tasks, Projects, Goals, and Dashboard.
 */

import { apiClient } from './client';

export type TaskStatus = 'todo' | 'in_progress' | 'blocked' | 'completed' | 'cancelled';
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent';

export type ProjectStatus = 'planning' | 'active' | 'on_hold' | 'completed' | 'cancelled' | 'archived';

export type GoalStatus = 'not_started' | 'in_progress' | 'achieved' | 'paused' | 'abandoned' | 'completed';

export interface Task {
  id: string;
  user_id: string;
  title: string;
  description?: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  project_id?: string | null;
  goal_id?: string | null;
  parent_task_id?: string | null;
  due_date?: string | null;
  start_date?: string | null;
  completed_at?: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
  project_name?: string | null;
  goal_title?: string | null;
  subtask_count?: number;
}

export interface TaskListResponse {
  items: Task[];
  total: number;
  page: number;
  page_size: number;
}

export interface TaskCreateInput {
  title: string;
  description?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  project_id?: string | null;
  goal_id?: string | null;
  parent_task_id?: string | null;
  due_date?: string | null;
  start_date?: string | null;
  tags?: string[];
}

export interface TaskUpdateInput {
  title?: string;
  description?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  project_id?: string | null;
  goal_id?: string | null;
  parent_task_id?: string | null;
  due_date?: string | null;
  start_date?: string | null;
  tags?: string[];
}

export interface Project {
  id: string;
  user_id: string;
  name: string;
  description?: string | null;
  color?: string | null;
  status: ProjectStatus;
  start_date?: string | null;
  target_date?: string | null;
  completed_at?: string | null;
  goal_id?: string | null;
  created_at: string;
  updated_at: string;
  goal_title?: string | null;
  task_count: number;
  completed_task_count: number;
  progress_percentage: number;
}

export interface ProjectDetail extends Project {
  tasks: Task[];
}

export interface ProjectListResponse {
  items: Project[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProjectCreateInput {
  name: string;
  description?: string | null;
  color?: string | null;
  status?: ProjectStatus;
  start_date?: string | null;
  target_date?: string | null;
  goal_id?: string | null;
}

export interface ProjectUpdateInput {
  name?: string;
  description?: string | null;
  color?: string | null;
  status?: ProjectStatus;
  start_date?: string | null;
  target_date?: string | null;
  goal_id?: string | null;
}

export interface Goal {
  id: string;
  user_id: string;
  title: string;
  description?: string | null;
  status: GoalStatus;
  target_date?: string | null;
  target_value?: number | null;
  current_value?: number | null;
  unit?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  progress_percentage?: number | null;
  project_count: number;
  task_count: number;
}

export interface GoalDetail extends Goal {
  projects: Project[];
  tasks: Task[];
}

export interface GoalListResponse {
  items: Goal[];
  total: number;
  page: number;
  page_size: number;
}

export interface GoalCreateInput {
  title: string;
  description?: string | null;
  status?: GoalStatus;
  target_date?: string | null;
  target_value?: number | null;
  current_value?: number | null;
  unit?: string | null;
}

export interface GoalUpdateInput {
  title?: string;
  description?: string | null;
  status?: GoalStatus;
  target_date?: string | null;
  target_value?: number | null;
  current_value?: number | null;
  unit?: string | null;
}

export interface ProductivityDashboard {
  active_tasks_count: number;
  overdue_tasks_count: number;
  completed_tasks_count: number;
  active_projects_count: number;
  active_goals_count: number;
  upcoming_tasks: Task[];
  overdue_tasks: Task[];
  active_projects: Project[];
  active_goals: Goal[];
  recently_completed_tasks: Task[];
}

// ---------------------------------------------------------------------------
// Task API Calls
// ---------------------------------------------------------------------------

export async function getTasks(params?: {
  project_id?: string;
  goal_id?: string;
  status?: string;
  priority?: string;
  query?: string;
  parent_task_id?: string;
  page?: number;
  page_size?: number;
}): Promise<TaskListResponse> {
  const query = new URLSearchParams();
  if (params?.project_id) query.set('project_id', params.project_id);
  if (params?.goal_id) query.set('goal_id', params.goal_id);
  if (params?.status) query.set('status', params.status);
  if (params?.priority) query.set('priority', params.priority);
  if (params?.query) query.set('query', params.query);
  if (params?.parent_task_id) query.set('parent_task_id', params.parent_task_id);
  if (params?.page) query.set('page', String(params.page));
  if (params?.page_size) query.set('page_size', String(params.page_size));

  const qs = query.toString();
  return apiClient.get<TaskListResponse>(`/tasks${qs ? `?${qs}` : ''}`);
}

export async function getTask(taskId: string): Promise<Task> {
  return apiClient.get<Task>(`/tasks/${taskId}`);
}

export async function createTask(input: TaskCreateInput): Promise<Task> {
  return apiClient.post<Task>('/tasks', input);
}

export async function updateTask(taskId: string, input: TaskUpdateInput): Promise<Task> {
  return apiClient.patch<Task>(`/tasks/${taskId}`, input);
}

export async function changeTaskStatus(taskId: string, newStatus: TaskStatus): Promise<Task> {
  return apiClient.post<Task>(`/tasks/${taskId}/status?new_status=${newStatus}`);
}

export async function deleteTask(taskId: string): Promise<void> {
  return apiClient.delete<void>(`/tasks/${taskId}`);
}

// ---------------------------------------------------------------------------
// Project API Calls
// ---------------------------------------------------------------------------

export async function getProjects(params?: {
  status?: string;
  goal_id?: string;
  query?: string;
  page?: number;
  page_size?: number;
}): Promise<ProjectListResponse> {
  const query = new URLSearchParams();
  if (params?.status) query.set('status', params.status);
  if (params?.goal_id) query.set('goal_id', params.goal_id);
  if (params?.query) query.set('query', params.query);
  if (params?.page) query.set('page', String(params.page));
  if (params?.page_size) query.set('page_size', String(params.page_size));

  const qs = query.toString();
  return apiClient.get<ProjectListResponse>(`/projects${qs ? `?${qs}` : ''}`);
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  return apiClient.get<ProjectDetail>(`/projects/${projectId}`);
}

export async function createProject(input: ProjectCreateInput): Promise<Project> {
  return apiClient.post<Project>('/projects', input);
}

export async function updateProject(projectId: string, input: ProjectUpdateInput): Promise<Project> {
  return apiClient.patch<Project>(`/projects/${projectId}`, input);
}

export async function changeProjectStatus(projectId: string, newStatus: ProjectStatus): Promise<Project> {
  return apiClient.post<Project>(`/projects/${projectId}/status?new_status=${newStatus}`);
}

export async function deleteProject(projectId: string, deleteTasks: boolean = false): Promise<void> {
  return apiClient.delete<void>(`/projects/${projectId}?delete_tasks=${deleteTasks}`);
}

// ---------------------------------------------------------------------------
// Goal API Calls
// ---------------------------------------------------------------------------

export async function getGoals(params?: {
  status?: string;
  query?: string;
  page?: number;
  page_size?: number;
}): Promise<GoalListResponse> {
  const query = new URLSearchParams();
  if (params?.status) query.set('status', params.status);
  if (params?.query) query.set('query', params.query);
  if (params?.page) query.set('page', String(params.page));
  if (params?.page_size) query.set('page_size', String(params.page_size));

  const qs = query.toString();
  return apiClient.get<GoalListResponse>(`/goals${qs ? `?${qs}` : ''}`);
}

export async function getGoal(goalId: string): Promise<GoalDetail> {
  return apiClient.get<GoalDetail>(`/goals/${goalId}`);
}

export async function createGoal(input: GoalCreateInput): Promise<Goal> {
  return apiClient.post<Goal>('/goals', input);
}

export async function updateGoal(goalId: string, input: GoalUpdateInput): Promise<Goal> {
  return apiClient.patch<Goal>(`/goals/${goalId}`, input);
}

export async function changeGoalStatus(goalId: string, newStatus: GoalStatus): Promise<Goal> {
  return apiClient.post<Goal>(`/goals/${goalId}/status?new_status=${newStatus}`);
}

export async function deleteGoal(goalId: string): Promise<void> {
  return apiClient.delete<void>(`/goals/${goalId}`);
}

// ---------------------------------------------------------------------------
// Dashboard API Call
// ---------------------------------------------------------------------------

export async function getProductivityDashboard(): Promise<ProductivityDashboard> {
  return apiClient.get<ProductivityDashboard>('/productivity/dashboard');
}

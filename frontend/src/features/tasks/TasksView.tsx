/**
 * Tasks Management View for AUREN Phase 3C.4 Productivity Core.
 * Provides interactive task organization, status transitions, priority filtering, and project association.
 */

import React, { useState } from 'react';
import {
  CheckSquare,
  Plus,
  Search,
  Calendar,
  AlertCircle,
  Clock,
  CheckCircle2,
  Circle,
  Tag,
  FolderKanban,
  Edit2,
  Trash2,
} from 'lucide-react';
import { Task, TaskCreateInput, TaskPriority, TaskStatus, TaskUpdateInput } from '../../api/productivity';
import {
  useChangeTaskStatus,
  useCreateTask,
  useDeleteTask,
  useProjects,
  useTasks,
  useUpdateTask,
} from '../../hooks/useProductivity';
import { TaskModal } from '../../components/productivity/TaskModal';
import { useAuth } from '../../context/AuthContext';

const PRIORITY_BADGES: Record<TaskPriority, { label: string; color: string }> = {
  low: { label: 'Low', color: 'bg-slate-800 text-slate-300 border-slate-700' },
  medium: { label: 'Medium', color: 'bg-blue-950/80 text-blue-300 border-blue-800/40' },
  high: { label: 'High', color: 'bg-amber-950/80 text-amber-300 border-amber-800/40' },
  urgent: { label: 'Urgent', color: 'bg-rose-950/80 text-rose-300 border-rose-800/40' },
};

export const TasksView: React.FC = () => {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<string>('all');
  const [selectedPriority, setSelectedPriority] = useState<string>('');
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [page, setPage] = useState<number>(1);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);

  const { data: projectsData } = useProjects({ page_size: 100 }, user?.id);
  const { data: tasksData, isLoading, error } = useTasks({
    status: activeTab === 'all' ? undefined : activeTab,
    priority: selectedPriority || undefined,
    project_id: selectedProjectId || undefined,
    query: searchQuery || undefined,
    page,
    page_size: 25,
  }, user?.id);

  const createTaskMutation = useCreateTask(user?.id);
  const updateTaskMutation = useUpdateTask(user?.id);
  const changeStatusMutation = useChangeTaskStatus(user?.id);
  const deleteTaskMutation = useDeleteTask(user?.id);

  const handleOpenCreate = () => {
    setEditingTask(null);
    setIsModalOpen(true);
  };

  const handleOpenEdit = (task: Task) => {
    setEditingTask(task);
    setIsModalOpen(true);
  };

  const handleModalSubmit = async (data: TaskCreateInput | TaskUpdateInput) => {
    if (editingTask) {
      await updateTaskMutation.mutateAsync({ taskId: editingTask.id, input: data });
    } else {
      await createTaskMutation.mutateAsync(data as TaskCreateInput);
    }
  };

  const handleToggleComplete = async (task: Task) => {
    const nextStatus: TaskStatus = task.status === 'completed' ? 'todo' : 'completed';
    await changeStatusMutation.mutateAsync({ taskId: task.id, newStatus: nextStatus });
  };

  const handleDelete = async (task: Task) => {
    const message =
      task.subtask_count && task.subtask_count > 0
        ? `Are you sure you want to delete "${task.title}"? Its ${task.subtask_count} subtask(s) will be kept as independent tasks.`
        : `Are you sure you want to delete this task?`;
    if (window.confirm(message)) {
      await deleteTaskMutation.mutateAsync(task.id);
    }
  };

  const isOverdue = (task: Task) => {
    if (!task.due_date || task.status === 'completed' || task.status === 'cancelled') return false;
    return new Date(task.due_date) < new Date();
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden text-slate-100">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between p-6 border-b border-slate-800 bg-slate-900/40 gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <CheckSquare className="w-5 h-5" />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-100">Tasks & Timetable</h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Personal task tracking with priority tiers, project binding, and deadline awareness.
          </p>
        </div>

        <button
          onClick={handleOpenCreate}
          className="flex items-center justify-center space-x-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors shadow-lg shadow-indigo-600/20 self-start md:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>New Task</span>
        </button>
      </div>

      {/* Filter and Tab Bar */}
      <div className="p-6 pb-2 space-y-4">
        {/* Status Tabs */}
        <div className="flex items-center space-x-2 border-b border-slate-800 pb-2 overflow-x-auto">
          {[
            { id: 'all', label: 'All Tasks' },
            { id: 'todo', label: 'To Do' },
            { id: 'in_progress', label: 'In Progress' },
            { id: 'blocked', label: 'Blocked' },
            { id: 'completed', label: 'Completed' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                setPage(1);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Filter Controls */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(1);
              }}
              placeholder="Search tasks..."
              className="w-full pl-9 pr-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div className="flex items-center space-x-2">
            <select
              value={selectedPriority}
              onChange={(e) => {
                setSelectedPriority(e.target.value);
                setPage(1);
              }}
              className="w-full px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
            >
              <option value="">All Priorities</option>
              <option value="urgent">Urgent</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div className="flex items-center space-x-2">
            <select
              value={selectedProjectId}
              onChange={(e) => {
                setSelectedProjectId(e.target.value);
                setPage(1);
              }}
              className="w-full px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
            >
              <option value="">All Projects</option>
              {projectsData?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Task List */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {isLoading ? (
          <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
            <Clock className="w-5 h-5 animate-spin mr-2" />
            Loading tasks...
          </div>
        ) : error ? (
          <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl text-center space-y-2">
            <AlertCircle className="w-5 h-5 text-indigo-400 mx-auto" />
            <div className="text-sm font-semibold text-slate-200">
              {!user ? 'Sign In to Access Tasks' : 'Failed to load tasks'}
            </div>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              {!user
                ? 'Sign in or register to manage your personal tasks, due dates, and priorities.'
                : 'Could not connect to the tasks service. Please verify network connectivity and try again.'}
            </p>
          </div>
        ) : tasksData?.items.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 border border-dashed border-slate-800 rounded-xl p-8 text-center bg-slate-900/20">
            <CheckSquare className="w-12 h-12 text-slate-600 mb-3" />
            <h3 className="text-sm font-semibold text-slate-300">No tasks found</h3>
            <p className="text-xs text-slate-500 max-w-sm mt-1 mb-4">
              {searchQuery || selectedPriority || selectedProjectId || activeTab !== 'all'
                ? 'Try clearing your search or filters to see more tasks.'
                : 'Create your first task to start organizing your work and commitments.'}
            </p>
            <button
              onClick={handleOpenCreate}
              className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg transition-colors border border-slate-700"
            >
              Create Task
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {tasksData?.items.map((task) => {
              const priorityInfo = PRIORITY_BADGES[task.priority] || PRIORITY_BADGES.medium;
              const overdue = isOverdue(task);

              return (
                <div
                  key={task.id}
                  className={`group flex items-start justify-between p-3.5 rounded-xl border transition-all ${
                    task.status === 'completed'
                      ? 'bg-slate-900/30 border-slate-800/60 opacity-75'
                      : overdue
                      ? 'bg-rose-950/10 border-rose-900/40 hover:border-rose-800/80'
                      : 'bg-slate-900/60 border-slate-800/80 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-start space-x-3 flex-1 min-w-0">
                    <button
                      onClick={() => handleToggleComplete(task)}
                      className="mt-0.5 text-slate-500 hover:text-indigo-400 transition-colors"
                      aria-label={task.status === 'completed' ? 'Mark incomplete' : 'Mark completed'}
                    >
                      {task.status === 'completed' ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                      ) : (
                        <Circle className="w-5 h-5" />
                      )}
                    </button>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center space-x-2 flex-wrap">
                        <span
                          className={`text-sm font-medium ${
                            task.status === 'completed' ? 'line-through text-slate-400' : 'text-slate-100'
                          }`}
                        >
                          {task.title}
                        </span>

                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${priorityInfo.color}`}
                        >
                          {priorityInfo.label}
                        </span>

                        {task.status === 'in_progress' && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-950 text-indigo-300 border border-indigo-800/50">
                            In Progress
                          </span>
                        )}

                        {task.status === 'blocked' && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-950 text-amber-300 border border-amber-800/50">
                            Blocked
                          </span>
                        )}
                      </div>

                      {task.description && (
                        <p className="text-xs text-slate-400 mt-1 line-clamp-2">{task.description}</p>
                      )}

                      {/* Metadata Badges */}
                      <div className="flex items-center space-x-3 mt-2 text-[11px] text-slate-400 flex-wrap gap-y-1">
                        {task.project_name && (
                          <span className="flex items-center text-slate-300 bg-slate-800/60 px-2 py-0.5 rounded border border-slate-700/50">
                            <FolderKanban className="w-3 h-3 mr-1 text-indigo-400" />
                            {task.project_name}
                          </span>
                        )}

                        {task.due_date && (
                          <span
                            className={`flex items-center ${
                              overdue ? 'text-rose-400 font-medium' : 'text-slate-400'
                            }`}
                          >
                            <Calendar className="w-3 h-3 mr-1" />
                            {overdue ? 'Overdue: ' : 'Due: '}
                            {new Date(task.due_date).toLocaleDateString()}
                          </span>
                        )}

                        {task.tags && task.tags.length > 0 && (
                          <div className="flex items-center space-x-1">
                            <Tag className="w-3 h-3 text-slate-500" />
                            {task.tags.map((tag) => (
                              <span key={tag} className="text-slate-400">
                                #{tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition-opacity ml-3">
                    <button
                      onClick={() => handleOpenEdit(task)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                      title="Edit task"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(task)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition-colors"
                      title="Delete task"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <TaskModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleModalSubmit}
        initialTask={editingTask}
      />
    </div>
  );
};


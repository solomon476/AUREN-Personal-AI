/**
 * Tasks & Timetable Management View for AUREN Phase 3C.4 Productivity Core.
 * Provides interactive task organization, status transitions, priority filtering,
 * project association, full-fidelity synchronization, and an academic student Timetable / Schedule view.
 * Elevated with AUREN Obsidian & Emerald Executive Design System.
 */

import React, { useState, useEffect, useMemo } from 'react';
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
  RotateCw,
  ChevronLeft,
  ChevronRight,
  Sun,
  Sunset,
  Moon,
  Sparkles,
  CalendarDays,
  ListFilter,
  BellPlus,
} from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useSafeSearch } from '../../hooks/useSafeSearch';
import { Task, TaskCreateInput, TaskPriority, TaskStatus, TaskUpdateInput } from '../../api/productivity';
import { ReminderCreateInput } from '../../api/reminders';
import {
  PRODUCTIVITY_KEYS,
  useChangeTaskStatus,
  useCreateTask,
  useDeleteTask,
  useProjects,
  useTasks,
  useUpdateTask,
} from '../../hooks/useProductivity';
import { REMINDER_KEYS, useCreateReminder } from '../../hooks/useReminders';
import { TaskModal } from '../../components/productivity/TaskModal';
import { ReminderModal } from '../reminders/ReminderModal';
import { useAuth } from '../../context/AuthContext';

const PRIORITY_BADGES: Record<TaskPriority, { label: string; color: string }> = {
  low: { label: 'Low', color: 'bg-slate-100 text-slate-700 border-slate-200' },
  medium: { label: 'Medium', color: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
  high: { label: 'High', color: 'bg-amber-50 text-amber-800 border-amber-200' },
  urgent: { label: 'Urgent', color: 'bg-rose-50 text-rose-700 border-rose-200' },
};

type ViewMode = 'list' | 'timetable';

export const TasksView: React.FC = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const searchParams = useSafeSearch<{ project_id?: string; goal_id?: string; view?: string }>();

  const [viewMode, setViewMode] = useState<ViewMode>(
    searchParams?.view === 'timetable' ? 'timetable' : 'list'
  );
  const [activeTab, setActiveTab] = useState<string>('all');
  const [selectedPriority, setSelectedPriority] = useState<string>('');
  const [selectedProjectId, setSelectedProjectId] = useState<string>(searchParams?.project_id || '');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const pageSize = 100; // Load all tasks up to 100 so all 31+ tasks sync immediately without truncation

  // Timetable State: Day selector
  const [selectedDate, setSelectedDate] = useState<Date>(() => new Date());
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [syncFeedback, setSyncFeedback] = useState<string | null>(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [modalInitialDueDate, setModalInitialDueDate] = useState<string | null>(null);
  const [reminderTaskTarget, setReminderTaskTarget] = useState<Task | null>(null);
  const createReminderMutation = useCreateReminder(user?.id);

  useEffect(() => {
    if (searchParams?.project_id && searchParams.project_id !== selectedProjectId) {
      setSelectedProjectId(searchParams.project_id);
    }
  }, [searchParams?.project_id]);

  const { data: projectsData } = useProjects({ page_size: 100 }, user?.id);
  const {
    data: tasksData,
    isLoading,
    error,
    refetch,
  } = useTasks(
    {
      status: activeTab === 'all' ? undefined : activeTab,
      priority: selectedPriority || undefined,
      project_id: selectedProjectId || undefined,
      query: searchQuery || undefined,
      page,
      page_size: pageSize,
    },
    user?.id
  );

  const createTaskMutation = useCreateTask(user?.id);
  const updateTaskMutation = useUpdateTask(user?.id);
  const changeStatusMutation = useChangeTaskStatus(user?.id);
  const deleteTaskMutation = useDeleteTask(user?.id);

  // Force sync / refresh across all productivity caches
  const handleSync = async () => {
    setIsSyncing(true);
    setSyncFeedback('Syncing tasks...');
    try {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.all }),
        refetch(),
      ]);
      setSyncFeedback('Tasks in sync');
      setTimeout(() => setSyncFeedback(null), 2500);
    } catch {
      setSyncFeedback('Sync failed');
      setTimeout(() => setSyncFeedback(null), 2500);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleOpenCreate = (prefilledDueDate?: string) => {
    setEditingTask(null);
    setModalInitialDueDate(prefilledDueDate || null);
    setIsModalOpen(true);
  };

  const handleOpenEdit = (task: Task) => {
    setEditingTask(task);
    setModalInitialDueDate(null);
    setIsModalOpen(true);
  };

  const handleModalSubmit = async (data: TaskCreateInput | TaskUpdateInput) => {
    if (editingTask) {
      await updateTaskMutation.mutateAsync({ taskId: editingTask.id, input: data });
    } else {
      await createTaskMutation.mutateAsync(data as TaskCreateInput);
    }
    // Invalidate dashboard, tasks, and reminders to ensure full sync
    await queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(user?.id) });
    await queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.all });
  };

  const handleToggleComplete = async (task: Task) => {
    const nextStatus: TaskStatus = task.status === 'completed' ? 'todo' : 'completed';
    await changeStatusMutation.mutateAsync({ taskId: task.id, newStatus: nextStatus });
    await queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(user?.id) });
    await queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.all });
  };

  const handleDelete = async (task: Task) => {
    const message =
      task.subtask_count && task.subtask_count > 0
        ? `Are you sure you want to delete "${task.title}"? Its ${task.subtask_count} subtask(s) will be kept as independent tasks.`
        : `Are you sure you want to delete this task?`;
    if (window.confirm(message)) {
      await deleteTaskMutation.mutateAsync(task.id);
      await queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.dashboard(user?.id) });
      await queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.all });
    }
  };

  const isOverdue = (task: Task) => {
    if (!task.due_date || task.status === 'completed' || task.status === 'cancelled') return false;
    return new Date(task.due_date) < new Date();
  };

  // -------------------------------------------------------------------------
  // Timetable Date Helpers & Time Blocks
  // -------------------------------------------------------------------------
  const weekDays = useMemo(() => {
    const start = new Date(selectedDate);
    const dayOfWeek = start.getDay(); // 0 is Sunday, 1 is Monday
    // Start week on Monday
    const diff = (dayOfWeek + 6) % 7;
    const monday = new Date(start);
    monday.setDate(start.getDate() - diff);

    const days = [];
    const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    for (let i = 0; i < 7; i++) {
      const d = new Date(monday);
      d.setDate(monday.getDate() + i);
      const isSelected = d.toDateString() === selectedDate.toDateString();
      const isToday = d.toDateString() === new Date().toDateString();

      // Count tasks due on this day
      const dateStr = d.toISOString().split('T')[0];
      const count =
        tasksData?.items.filter((t) => t.due_date && t.due_date.startsWith(dateStr)).length || 0;

      days.push({
        name: dayNames[i],
        dayNum: String(d.getDate()).padStart(2, '0'),
        dateObj: d,
        dateStr,
        isSelected,
        isToday,
        taskCount: count,
      });
    }
    return days;
  }, [selectedDate, tasksData?.items]);

  // Tasks grouped for the currently selected day
  const selectedDateStr = selectedDate.toISOString().split('T')[0];
  const dayTasks = useMemo(() => {
    if (!tasksData?.items) return [];
    return tasksData.items.filter((t) => t.due_date && t.due_date.startsWith(selectedDateStr));
  }, [tasksData?.items, selectedDateStr]);

  // Tasks with no due date (unscheduled)
  const unscheduledTasks = useMemo(() => {
    if (!tasksData?.items) return [];
    return tasksData.items.filter((t) => !t.due_date && t.status !== 'completed' && t.status !== 'cancelled');
  }, [tasksData?.items]);

  // Categorize dayTasks into timetable slots
  const morningTasks = useMemo(() => {
    return dayTasks.filter((t) => {
      if (!t.due_date) return false;
      const hour = new Date(t.due_date).getHours();
      return hour >= 6 && hour < 12;
    });
  }, [dayTasks]);

  const afternoonTasks = useMemo(() => {
    return dayTasks.filter((t) => {
      if (!t.due_date) return false;
      const hour = new Date(t.due_date).getHours();
      return hour >= 12 && hour < 17;
    });
  }, [dayTasks]);

  const eveningTasks = useMemo(() => {
    return dayTasks.filter((t) => {
      if (!t.due_date) return false;
      const hour = new Date(t.due_date).getHours();
      return hour >= 17 && hour < 23;
    });
  }, [dayTasks]);

  const allDayFlexibleTasks = useMemo(() => {
    return dayTasks.filter((t) => {
      if (!t.due_date) return false;
      const d = new Date(t.due_date);
      const hour = d.getHours();
      // If hour is 0:00 or 23:59 (typical for date-only deadline) or outside regular blocks
      return hour < 6 || hour === 23;
    });
  }, [dayTasks]);

  const totalTasksCount = tasksData?.total ?? tasksData?.items.length ?? 0;

  return (
    <div className="flex-1 flex flex-col h-full bg-white overflow-hidden text-slate-900">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between p-4 sm:p-6 border-b border-slate-200 bg-white gap-3 sm:gap-4 flex-shrink-0">
        <div>
          <div className="flex items-center space-x-3.5">
            <div className="p-2.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-600 shadow-sm flex-shrink-0">
              <CheckSquare className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-xl font-bold tracking-tight text-slate-900">Tasks &amp; Timetable</h1>
                <span className="inline-flex items-center text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5 animate-pulse" />
                  {totalTasksCount} Synced
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Academic &amp; personal tracking with priority tiers, project binding, and student timetable.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* View Mode Toggle: List vs Timetable */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200">
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                viewMode === 'list'
                  ? 'bg-white text-slate-900 shadow-sm border border-slate-200'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <ListFilter className="w-3.5 h-3.5" />
              <span>List View</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode('timetable')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                viewMode === 'timetable'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <CalendarDays className="w-3.5 h-3.5" />
              <span>Timetable</span>
            </button>
          </div>

          {/* Sync Button */}
          <button
            type="button"
            onClick={handleSync}
            disabled={isSyncing}
            className="flex items-center space-x-1.5 px-3 py-2 bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 text-xs font-medium rounded-xl transition cursor-pointer disabled:opacity-50"
            title="Sync tasks with Home and AI Engine"
          >
            <RotateCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin text-emerald-600' : ''}`} />
            <span className="hidden sm:inline">{syncFeedback || 'Sync'}</span>
          </button>

          {/* New Task Button */}
          <button
            onClick={() => handleOpenCreate()}
            className="flex items-center justify-center space-x-2 px-4 py-2 min-h-[40px] bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-xl transition-all shadow-sm hover:shadow-emerald-600/25 touch-target cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>New Task</span>
          </button>
        </div>
      </div>

      {/* TIMETABLE VIEW */}
      {viewMode === 'timetable' ? (
        <div className="flex-1 flex flex-col overflow-y-auto p-4 sm:p-6 space-y-5 scrollbar-thin bg-slate-50/50">
          {/* Weekly Date Strip Navigator */}
          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Calendar className="w-4 h-4 text-emerald-600" />
                <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                  Academic &amp; Daily Schedule
                </span>
                <span className="text-xs text-slate-500">
                  • {selectedDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
                </span>
              </div>
              <div className="flex items-center space-x-1.5">
                <button
                  type="button"
                  onClick={() => {
                    const prev = new Date(selectedDate);
                    prev.setDate(prev.getDate() - 7);
                    setSelectedDate(prev);
                  }}
                  className="p-1.5 rounded-lg hover:bg-slate-100 border border-slate-200 text-slate-600 cursor-pointer"
                  title="Previous Week"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedDate(new Date())}
                  className="px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 cursor-pointer"
                >
                  Today
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const next = new Date(selectedDate);
                    next.setDate(next.getDate() + 7);
                    setSelectedDate(next);
                  }}
                  className="p-1.5 rounded-lg hover:bg-slate-100 border border-slate-200 text-slate-600 cursor-pointer"
                  title="Next Week"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* 7-Day Day Selector Buttons */}
            <div className="grid grid-cols-7 gap-1.5 sm:gap-2">
              {weekDays.map((day) => (
                <button
                  key={day.dateStr}
                  type="button"
                  onClick={() => setSelectedDate(day.dateObj)}
                  className={`flex flex-col items-center justify-center p-2 rounded-xl border transition-all text-center cursor-pointer ${
                    day.isSelected
                      ? 'bg-emerald-600 border-emerald-600 text-white shadow-md shadow-emerald-600/20'
                      : day.isToday
                      ? 'bg-emerald-50 border-emerald-300 text-emerald-900 hover:bg-emerald-100'
                      : 'bg-white border-slate-200 text-slate-800 hover:border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  <span
                    className={`text-[10px] uppercase font-bold tracking-wider ${
                      day.isSelected ? 'text-emerald-100' : day.isToday ? 'text-emerald-700' : 'text-slate-500'
                    }`}
                  >
                    {day.name}
                  </span>
                  <span className="text-sm sm:text-base font-extrabold font-mono mt-0.5 leading-none">
                    {day.dayNum}
                  </span>
                  {day.taskCount > 0 && (
                    <span
                      className={`mt-1 text-[9px] font-mono px-1.5 py-0.2 rounded-full font-bold ${
                        day.isSelected
                          ? 'bg-white text-emerald-700'
                          : 'bg-emerald-100 text-emerald-800'
                      }`}
                    >
                      {day.taskCount}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Time Slots Grid for Selected Day */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Morning Slot */}
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
              <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                <div className="flex items-center space-x-2">
                  <div className="p-1.5 rounded-lg bg-amber-50 text-amber-600 border border-amber-200">
                    <Sun className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-slate-900 uppercase tracking-tight">Morning</h3>
                    <span className="text-[10px] text-slate-500">08:00 — 12:00</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleOpenCreate(`${selectedDateStr}T09:00`)}
                  className="text-[11px] text-emerald-600 hover:text-emerald-700 font-semibold flex items-center space-x-1 cursor-pointer"
                >
                  <Plus className="w-3 h-3" />
                  <span>Add</span>
                </button>
              </div>

              {morningTasks.length === 0 ? (
                <div className="py-6 text-center text-xs text-slate-400">
                  <p>No morning sessions</p>
                  <button
                    type="button"
                    onClick={() => handleOpenCreate(`${selectedDateStr}T09:00`)}
                    className="mt-1 text-emerald-600 text-[11px] font-medium hover:underline cursor-pointer"
                  >
                    + Schedule morning task
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  {morningTasks.map((task) => (
                    <TimetableTaskCard
                      key={task.id}
                      task={task}
                      onToggle={handleToggleComplete}
                      onEdit={handleOpenEdit}
                      onDelete={handleDelete}
                      onSetReminder={setReminderTaskTarget}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Afternoon Slot */}
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
              <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                <div className="flex items-center space-x-2">
                  <div className="p-1.5 rounded-lg bg-orange-50 text-orange-600 border border-orange-200">
                    <Sunset className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-slate-900 uppercase tracking-tight">Afternoon</h3>
                    <span className="text-[10px] text-slate-500">12:00 — 17:00</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleOpenCreate(`${selectedDateStr}T14:00`)}
                  className="text-[11px] text-emerald-600 hover:text-emerald-700 font-semibold flex items-center space-x-1 cursor-pointer"
                >
                  <Plus className="w-3 h-3" />
                  <span>Add</span>
                </button>
              </div>

              {afternoonTasks.length === 0 ? (
                <div className="py-6 text-center text-xs text-slate-400">
                  <p>No afternoon sessions</p>
                  <button
                    type="button"
                    onClick={() => handleOpenCreate(`${selectedDateStr}T14:00`)}
                    className="mt-1 text-emerald-600 text-[11px] font-medium hover:underline cursor-pointer"
                  >
                    + Schedule afternoon task
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  {afternoonTasks.map((task) => (
                    <TimetableTaskCard
                      key={task.id}
                      task={task}
                      onToggle={handleToggleComplete}
                      onEdit={handleOpenEdit}
                      onDelete={handleDelete}
                      onSetReminder={setReminderTaskTarget}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Evening Slot */}
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
              <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                <div className="flex items-center space-x-2">
                  <div className="p-1.5 rounded-lg bg-indigo-50 text-indigo-600 border border-indigo-200">
                    <Moon className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-slate-900 uppercase tracking-tight">Evening &amp; Night</h3>
                    <span className="text-[10px] text-slate-500">17:00 — 22:00</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleOpenCreate(`${selectedDateStr}T19:00`)}
                  className="text-[11px] text-emerald-600 hover:text-emerald-700 font-semibold flex items-center space-x-1 cursor-pointer"
                >
                  <Plus className="w-3 h-3" />
                  <span>Add</span>
                </button>
              </div>

              {eveningTasks.length === 0 ? (
                <div className="py-6 text-center text-xs text-slate-400">
                  <p>No evening study blocks</p>
                  <button
                    type="button"
                    onClick={() => handleOpenCreate(`${selectedDateStr}T19:00`)}
                    className="mt-1 text-emerald-600 text-[11px] font-medium hover:underline cursor-pointer"
                  >
                    + Schedule evening task
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  {eveningTasks.map((task) => (
                    <TimetableTaskCard
                      key={task.id}
                      task={task}
                      onToggle={handleToggleComplete}
                      onEdit={handleOpenEdit}
                      onDelete={handleDelete}
                      onSetReminder={setReminderTaskTarget}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* All-Day or Flexible Deadlines */}
          {allDayFlexibleTasks.length > 0 && (
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
              <div className="flex items-center space-x-2">
                <Clock className="w-4 h-4 text-emerald-600" />
                <h3 className="text-xs font-bold text-slate-900 uppercase tracking-tight">
                  All-Day &amp; Flexible Deadlines for {selectedDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
                </h3>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
                {allDayFlexibleTasks.map((task) => (
                  <TimetableTaskCard
                    key={task.id}
                    task={task}
                    onToggle={handleToggleComplete}
                    onEdit={handleOpenEdit}
                    onDelete={handleDelete}
                    onSetReminder={setReminderTaskTarget}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Unscheduled Tasks Drawer: Allows instant scheduling into the timetable */}
          {unscheduledTasks.length > 0 && (
            <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Sparkles className="w-4 h-4 text-amber-500" />
                  <h3 className="text-xs font-bold text-slate-900 uppercase tracking-tight">
                    Unscheduled Tasks ({unscheduledTasks.length})
                  </h3>
                  <span className="text-[11px] text-slate-500">
                    — Assign to your timetable with a deadline
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 max-h-60 overflow-y-auto scrollbar-thin pr-1">
                {unscheduledTasks.map((task) => (
                  <div
                    key={task.id}
                    className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between gap-2 hover:border-emerald-300 transition"
                  >
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-slate-900 truncate">{task.title}</p>
                      <span className="text-[10px] text-slate-500 block">No deadline set</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setEditingTask(task);
                        setModalInitialDueDate(`${selectedDateStr}T09:00`);
                        setIsModalOpen(true);
                      }}
                      className="px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 whitespace-nowrap cursor-pointer"
                    >
                      + Schedule
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        /* STANDARD LIST VIEW */
        <>
          {/* Filter and Tab Bar */}
          <div className="p-4 sm:p-6 pb-2 space-y-3 sm:space-y-4 border-b border-slate-200 bg-slate-50/60 flex-shrink-0">
            {/* Status Tabs */}
            <div className="flex items-center space-x-2 pb-2 overflow-x-auto scrollbar-none">
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
                  className={`px-3.5 py-2 min-h-[38px] rounded-xl text-xs font-medium transition-all duration-150 whitespace-nowrap flex items-center cursor-pointer ${
                    activeTab === tab.id
                      ? 'bg-emerald-600 text-white shadow-sm font-semibold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 border border-transparent'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Filter Controls */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 sm:gap-3">
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setPage(1);
                  }}
                  placeholder="Search tasks..."
                  className="w-full pl-10 pr-3.5 py-2.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition min-h-[42px]"
                />
              </div>

              <div className="flex items-center space-x-2">
                <select
                  value={selectedPriority}
                  onChange={(e) => {
                    setSelectedPriority(e.target.value);
                    setPage(1);
                  }}
                  className="w-full px-3.5 py-2.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-700 focus:outline-none focus:border-emerald-500 transition min-h-[42px]"
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
                  className="w-full px-3.5 py-2.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-700 focus:outline-none focus:border-emerald-500 transition min-h-[42px]"
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
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 scrollbar-thin">
            {isLoading ? (
              <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
                <Clock className="w-5 h-5 animate-spin mr-2 text-emerald-600" />
                Loading tasks...
              </div>
            ) : error ? (
              <div className="p-5 bg-white border border-slate-200 rounded-2xl text-center space-y-2 shadow-sm">
                <AlertCircle className="w-5 h-5 text-amber-500 mx-auto" />
                <div className="text-sm font-semibold text-slate-800">
                  {!user ? 'Sign In to Access Tasks' : 'Failed to load tasks'}
                </div>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  {!user
                    ? 'Sign in or register to manage your personal tasks, due dates, and priorities.'
                    : 'Could not connect to the tasks service. Please verify network connectivity and try again.'}
                </p>
              </div>
            ) : tasksData?.items.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-64 border border-dashed border-slate-300 rounded-2xl p-8 text-center bg-slate-50/50">
                <CheckSquare className="w-12 h-12 text-slate-400 mb-3" />
                <h3 className="text-sm font-semibold text-slate-700">No tasks found</h3>
                <p className="text-xs text-slate-500 max-w-sm mt-1 mb-4">
                  {searchQuery || selectedPriority || selectedProjectId || activeTab !== 'all'
                    ? 'Try clearing your search or filters to see more tasks.'
                    : 'Create your first task to start organizing your work and commitments.'}
                </p>
                <button
                  onClick={() => handleOpenCreate()}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-xl transition shadow-sm cursor-pointer"
                >
                  Create Task
                </button>
              </div>
            ) : (
              <div className="space-y-2.5">
                {tasksData?.items.map((task) => {
                  const priorityInfo = PRIORITY_BADGES[task.priority] || PRIORITY_BADGES.medium;
                  const overdue = isOverdue(task);

                  return (
                    <div
                      key={task.id}
                      className={`group flex items-start justify-between p-4 rounded-2xl border transition-all duration-200 shadow-sm ${
                        task.status === 'completed'
                          ? 'bg-slate-50/70 border-slate-200 opacity-70'
                          : overdue
                          ? 'bg-rose-50/40 border-rose-200 hover:border-rose-300'
                          : 'bg-white border-slate-200 hover:border-emerald-300 hover:shadow-md'
                      }`}
                    >
                      <div className="flex items-start space-x-3.5 flex-1 min-w-0">
                        <button
                          onClick={() => handleToggleComplete(task)}
                          className="p-2 -m-1.5 touch-target flex items-center justify-center text-slate-400 hover:text-emerald-600 transition-colors flex-shrink-0 cursor-pointer"
                          aria-label={task.status === 'completed' ? 'Mark incomplete' : 'Mark completed'}
                        >
                          {task.status === 'completed' ? (
                            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                          ) : (
                            <Circle className="w-5 h-5 text-slate-400 hover:text-emerald-600" />
                          )}
                        </button>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center space-x-2.5 flex-wrap gap-y-1">
                            <span
                              className={`text-xs sm:text-sm font-medium ${
                                task.status === 'completed' ? 'line-through text-slate-400' : 'text-slate-900'
                              }`}
                            >
                              {task.title}
                            </span>

                            <span
                              className={`px-2 py-0.5 rounded-md text-[10px] font-semibold border ${priorityInfo.color}`}
                            >
                              {priorityInfo.label}
                            </span>

                            {task.status === 'in_progress' && (
                              <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                                In Progress
                              </span>
                            )}

                            {task.status === 'blocked' && (
                              <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                                Blocked
                              </span>
                            )}
                          </div>

                          {task.description && (
                            <p className="text-xs text-slate-500 mt-1 line-clamp-2 leading-relaxed">
                              {task.description}
                            </p>
                          )}

                          {/* Metadata Badges */}
                          <div className="flex items-center space-x-3 mt-2 text-[11px] text-slate-500 flex-wrap gap-y-1">
                            {task.project_name && (
                              <span className="flex items-center text-slate-700 bg-slate-100 px-2 py-0.5 rounded-md border border-slate-200 font-medium">
                                <FolderKanban className="w-3 h-3 mr-1 text-emerald-600" />
                                {task.project_name}
                              </span>
                            )}

                            {task.due_date && (
                              <span
                                className={`flex items-center ${
                                  overdue ? 'text-rose-600 font-medium' : 'text-slate-500'
                                }`}
                              >
                                <Calendar className="w-3 h-3 mr-1" />
                                {overdue ? 'Overdue: ' : 'Due: '}
                                {new Date(task.due_date).toLocaleDateString()}
                              </span>
                            )}

                            {task.tags && task.tags.length > 0 && (
                              <div className="flex items-center space-x-1">
                                <Tag className="w-3 h-3 text-slate-400" />
                                {task.tags.map((tag) => (
                                  <span
                                    key={tag}
                                    className="text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200 font-mono text-[10px]"
                                  >
                                    #{tag}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center space-x-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity ml-2 sm:ml-3 flex-shrink-0">
                        <button
                          type="button"
                          onClick={() => setReminderTaskTarget(task)}
                          className="p-2 sm:p-1.5 rounded-lg text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 transition-colors touch-target flex items-center justify-center cursor-pointer"
                          title="Set reminder"
                          aria-label="Set reminder"
                        >
                          <BellPlus className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleOpenEdit(task)}
                          className="p-2 sm:p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors touch-target flex items-center justify-center cursor-pointer"
                          title="Edit task"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(task)}
                          className="p-2 sm:p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors touch-target flex items-center justify-center cursor-pointer"
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
        </>
      )}

      {/* Task Creation / Edit Modal */}
      <TaskModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleModalSubmit}
        initialTask={editingTask}
        initialDueDate={modalInitialDueDate}
      />

      {/* Quick Reminder Creation Modal for a Task */}
      <ReminderModal
        isOpen={Boolean(reminderTaskTarget)}
        onClose={() => setReminderTaskTarget(null)}
        defaultTaskId={reminderTaskTarget?.id ?? null}
        onSubmit={async (data) => {
          await createReminderMutation.mutateAsync(data as ReminderCreateInput);
          await queryClient.invalidateQueries({ queryKey: REMINDER_KEYS.all });
          await queryClient.invalidateQueries({ queryKey: PRODUCTIVITY_KEYS.all });
        }}
      />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Timetable Slot Card Component
// ---------------------------------------------------------------------------
interface TimetableTaskCardProps {
  task: Task;
  onToggle: (task: Task) => Promise<void>;
  onEdit: (task: Task) => void;
  onDelete: (task: Task) => Promise<void>;
  onSetReminder?: (task: Task) => void;
}

const TimetableTaskCard: React.FC<TimetableTaskCardProps> = ({
  task,
  onToggle,
  onEdit,
  onDelete,
  onSetReminder,
}) => {
  const isCompleted = task.status === 'completed';
  const priorityInfo = PRIORITY_BADGES[task.priority] || PRIORITY_BADGES.medium;

  const timeStr = useMemo(() => {
    if (!task.due_date) return null;
    const d = new Date(task.due_date);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }, [task.due_date]);

  return (
    <div
      className={`p-3 rounded-xl border transition-all text-xs space-y-2 group ${
        isCompleted
          ? 'bg-slate-50 border-slate-200 opacity-60'
          : 'bg-white border-slate-200 hover:border-emerald-300 hover:shadow-sm'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start space-x-2 min-w-0">
          <button
            type="button"
            onClick={() => onToggle(task)}
            className="p-1 -m-1 text-slate-400 hover:text-emerald-600 cursor-pointer flex-shrink-0"
            aria-label={isCompleted ? 'Mark incomplete' : 'Mark completed'}
          >
            {isCompleted ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            ) : (
              <Circle className="w-4 h-4 text-slate-400 hover:text-emerald-600" />
            )}
          </button>
          <div className="min-w-0">
            <p
              className={`font-semibold leading-snug truncate ${
                isCompleted ? 'line-through text-slate-400' : 'text-slate-900'
              }`}
            >
              {task.title}
            </p>
            {task.description && (
              <p className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">{task.description}</p>
            )}
          </div>
        </div>

        <div className="flex items-center space-x-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity flex-shrink-0">
          {onSetReminder && (
            <button
              type="button"
              onClick={() => onSetReminder(task)}
              className="p-1 text-slate-400 hover:text-emerald-600 rounded hover:bg-emerald-50 cursor-pointer"
              title="Set reminder"
              aria-label="Set reminder"
            >
              <BellPlus className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            type="button"
            onClick={() => onEdit(task)}
            className="p-1 text-slate-400 hover:text-slate-700 rounded hover:bg-slate-100 cursor-pointer"
            title="Edit task"
          >
            <Edit2 className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => onDelete(task)}
            className="p-1 text-slate-400 hover:text-rose-600 rounded hover:bg-rose-50 cursor-pointer"
            title="Delete task"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="flex items-center space-x-2 text-[10px] flex-wrap gap-y-1">
        {timeStr && (
          <span className="flex items-center font-mono font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
            <Clock className="w-2.5 h-2.5 mr-1 text-emerald-600" />
            {timeStr}
          </span>
        )}

        <span className={`px-1.5 py-0.5 rounded font-semibold border ${priorityInfo.color}`}>
          {priorityInfo.label}
        </span>

        {task.project_name && (
          <span className="flex items-center text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
            <FolderKanban className="w-2.5 h-2.5 mr-1 text-emerald-600" />
            {task.project_name}
          </span>
        )}
      </div>
    </div>
  );
};

/**
 * Home — AUREN Personal AI Command Center.
 * Unified operating environment integrating daily planning, high-priority tasks,
 * active projects, strategic goals, recent conversations, and central AI entry point.
 * Elevated with High-Contrast Executive White, Obsidian, Emerald, and Gold Design System.
 */

import React, { useState } from 'react';
import {
  CheckSquare,
  FolderKanban,
  Target,
  ArrowRight,
  Plus,
  Send,
  Clock,
  CheckCircle2,
  BookOpen,
  Search,
  MessageSquare,
  Bot,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Command,
  MapPin,
} from 'lucide-react';
import { Link, useNavigate } from '@tanstack/react-router';
import { useAuth } from '../../context/AuthContext';
import {
  useChangeTaskStatus,
  useGoals,
  useProductivityDashboard,
  useProjects,
  useTasks,
} from '../../hooks/useProductivity';
import { useConversations } from '../../hooks/useConversations';
import { Task, TaskStatus } from '../../api/productivity';

export const HomeView: React.FC = () => {
  const { user, profile, isLoading: isAuthLoading } = useAuth();
  const navigate = useNavigate();

  const [promptInput, setPromptInput] = useState('');
  const [stripCenterOffsetDays, setStripCenterOffsetDays] = useState(0);
  const toLocalDateKey = (date: Date) =>
    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  const [selectedDateKey, setSelectedDateKey] = useState<string>(() => toLocalDateKey(new Date()));

  // Real data hooks
  const { data: dashboard } = useProductivityDashboard(user?.id);
  const { data: tasksData, isLoading: isLoadingTasks, error: tasksError } = useTasks(
    { status: 'todo', page: 1, page_size: 5 },
    user?.id
  );
  const { data: projectsData, isLoading: isLoadingProjects, error: projectsError } = useProjects(
    { status: 'active', page: 1, page_size: 4 },
    user?.id
  );
  const { data: goalsData, isLoading: isLoadingGoals, error: goalsError } = useGoals(
    { status: 'in_progress', page: 1, page_size: 3 },
    user?.id
  );
  const { data: conversations = [], isLoading: isLoadingConversations, error: conversationsError } = useConversations(user?.id);

  const changeTaskStatusMutation = useChangeTaskStatus(user?.id);

  const handleToggleTask = async (task: Task) => {
    const nextStatus: TaskStatus = task.status === 'completed' ? 'todo' : 'completed';
    try {
      await changeTaskStatusMutation.mutateAsync({
        taskId: task.id,
        newStatus: nextStatus,
      });
    } catch (e) {
      console.error('Failed to toggle task status:', e);
    }
  };

  const handleQuickAsk = (e: React.FormEvent) => {
    e.preventDefault();
    const query = promptInput.trim();
    if (!query) {
      navigate({ to: '/chat' });
      return;
    }
    // Navigate to chat and pass prompt via search param
    navigate({ to: '/chat', search: { q: query } });
  };

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  const getDisplayName = (): string => {
    if (profile?.full_name?.trim()) {
      return profile.full_name.trim();
    }
    const metaFullName = (user?.user_metadata?.full_name || user?.user_metadata?.name || '') as string;
    if (metaFullName?.trim()) {
      return metaFullName.trim();
    }
    return '';
  };

  const displayName = getDisplayName();

  const todayFormatted = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  });

  // Centered sliding 7-day window so Today is always front-and-center and never clipped off an edge
  const { weekDays, rangeLabel, todayKey } = React.useMemo(() => {
    const now = new Date();
    const todayStr = toLocalDateKey(now);
    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const anchor = new Date(now);
    anchor.setDate(now.getDate() + stripCenterOffsetDays);

    const days = [];
    for (let offset = -3; offset <= 3; offset++) {
      const d = new Date(anchor);
      d.setDate(anchor.getDate() + offset);
      const dateKey = toLocalDateKey(d);
      days.push({
        date: d,
        dateKey,
        name: dayNames[d.getDay()],
        dayNum: String(d.getDate()).padStart(2, '0'),
        monthShort: d.toLocaleDateString('en-US', { month: 'short' }),
        fullLabel: d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }),
        isToday: dateKey === todayStr,
      });
    }
    const first = days[0];
    const last = days[days.length - 1];
    const range =
      first.monthShort === last.monthShort
        ? `${first.monthShort} ${first.dayNum} – ${last.dayNum}`
        : `${first.monthShort} ${first.dayNum} – ${last.monthShort} ${last.dayNum}`;
    return { weekDays: days, rangeLabel: range, todayKey: todayStr };
  }, [stripCenterOffsetDays]);

  const dueCountByDate = React.useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of tasksData?.items ?? []) {
      if (t.due_date) {
        const key = String(t.due_date).slice(0, 10);
        counts[key] = (counts[key] || 0) + 1;
      }
    }
    return counts;
  }, [tasksData?.items]);

  const selectedDayMeta = weekDays.find((d) => d.dateKey === selectedDateKey);

  return (
    <div className="flex-1 flex flex-col h-full bg-white overflow-y-auto text-slate-900 p-3.5 sm:p-7 space-y-5 sm:space-y-7 max-w-7xl mx-auto scrollbar-thin">
      {/* Top Briefing Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-5 sm:pb-6 border-b border-slate-200 gap-4 sm:gap-6 relative">
        <div className="space-y-1">
          <div className="flex items-center space-x-2 text-xs font-semibold text-emerald-600 mb-1">
            <Calendar className="w-3.5 h-3.5 text-emerald-600" />
            <span className="tracking-tight text-emerald-700">{todayFormatted}</span>
            <span className="text-slate-300">•</span>
            <span className="text-slate-500 font-normal">Personal Command Center</span>
          </div>
          <h1 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-slate-900">
            {getGreeting()}{displayName ? `, ${displayName}` : ''}
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 max-w-xl leading-relaxed">
            Overview of your daily commitments, strategic milestones, and intelligence streams.
          </p>
        </div>

        {/* Quick KPI Snapshot - Crisp White & Emerald Design */}
        {dashboard && (
          <div className="flex items-center gap-2 sm:gap-3 overflow-x-auto w-full md:w-auto scrollbar-none py-1">
            <div className="flex-1 md:flex-none px-3.5 py-2 sm:px-4 sm:py-2.5 rounded-2xl bg-white border border-slate-200 shadow-sm text-center min-w-[76px] hover:border-emerald-500/40 transition-all group">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider block font-semibold">Tasks</span>
              <span className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight font-mono inline-block">
                {dashboard.active_tasks_count ?? 0}
              </span>
            </div>
            <div className="flex-1 md:flex-none px-3.5 py-2 sm:px-4 sm:py-2.5 rounded-2xl bg-white border border-slate-200 shadow-sm text-center min-w-[76px] hover:border-emerald-500/40 transition-all group">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider block font-semibold">Projects</span>
              <span className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight font-mono inline-block">
                {dashboard.active_projects_count ?? 0}
              </span>
            </div>
            <div className="flex-1 md:flex-none px-3.5 py-2 sm:px-4 sm:py-2.5 rounded-2xl bg-white border border-slate-200 shadow-sm text-center min-w-[76px] hover:border-emerald-500/40 transition-all group">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider block font-semibold">Goals</span>
              <span className="text-lg sm:text-xl font-bold text-emerald-600 tracking-tight font-mono inline-block">
                {dashboard.active_goals_count ?? 0}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Centered 7-Day Planner Strip — All 7 days fit viewport cleanly with Today highlighted & easy navigation */}
      <div className="w-full flex-shrink-0 space-y-2.5">
        <div className="flex items-center justify-between gap-2 px-0.5">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-xs font-bold text-slate-800 tracking-tight truncate">{rangeLabel}</span>
            {selectedDayMeta && (
              <Link
                to="/tasks"
                className="text-[11px] font-medium text-emerald-700 hover:text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200/80 truncate"
              >
                {selectedDayMeta.isToday ? 'Today' : selectedDayMeta.fullLabel}
                {dueCountByDate[selectedDayMeta.dateKey]
                  ? ` · ${dueCountByDate[selectedDayMeta.dateKey]} due`
                  : ' · Timetable →'}
              </Link>
            )}
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            <button
              type="button"
              onClick={() => setStripCenterOffsetDays((prev) => prev - 7)}
              aria-label="Previous 7 days"
              className="w-7 h-7 rounded-full border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 flex items-center justify-center transition cursor-pointer"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => {
                setStripCenterOffsetDays(0);
                setSelectedDateKey(todayKey);
              }}
              aria-label="Jump to Today"
              className={`px-2.5 h-7 rounded-full text-[11px] font-semibold border transition cursor-pointer ${
                stripCenterOffsetDays === 0 && selectedDateKey === todayKey
                  ? 'bg-emerald-50 border-emerald-300 text-emerald-700'
                  : 'bg-emerald-600 border-emerald-600 text-white hover:bg-emerald-500'
              }`}
            >
              Today
            </button>
            <button
              type="button"
              onClick={() => setStripCenterOffsetDays((prev) => prev + 7)}
              aria-label="Next 7 days"
              className="w-7 h-7 rounded-full border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 flex items-center justify-center transition cursor-pointer"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-7 gap-1 sm:gap-2.5 w-full">
          {weekDays.map((d) => {
            const isSelected = d.dateKey === selectedDateKey;
            const hasDueTasks = (dueCountByDate[d.dateKey] || 0) > 0;
            return (
              <button
                key={d.dateKey}
                type="button"
                onClick={() => setSelectedDateKey(d.dateKey)}
                className={`h-[70px] sm:h-[78px] rounded-xl sm:rounded-2xl flex flex-col items-center justify-center p-1 sm:p-2 border transition-all select-none shadow-sm cursor-pointer ${
                  d.isToday
                    ? 'bg-emerald-50 border-2 border-emerald-500 text-emerald-950 shadow-emerald-500/15'
                    : isSelected
                    ? 'bg-slate-900 border-slate-900 text-white'
                    : 'bg-white border-slate-200 text-slate-800 hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <span
                  className={`text-[9px] sm:text-[10px] uppercase tracking-wider font-bold leading-none ${
                    d.isToday
                      ? 'text-emerald-700'
                      : isSelected
                      ? 'text-slate-300'
                      : 'text-slate-500'
                  }`}
                >
                  {d.name}
                </span>
                <span
                  className={`text-sm sm:text-lg font-bold font-mono mt-1 leading-none ${
                    d.isToday
                      ? 'text-emerald-950'
                      : isSelected
                      ? 'text-white'
                      : 'text-slate-900'
                  }`}
                >
                  {d.dayNum}
                </span>
                {d.isToday ? (
                  <span className="text-[8px] sm:text-[9px] font-bold uppercase tracking-wider text-emerald-700 mt-1 leading-none">
                    Today
                  </span>
                ) : hasDueTasks ? (
                  <span
                    className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${
                      isSelected ? 'bg-emerald-400' : 'bg-emerald-500'
                    }`}
                  />
                ) : (
                  <span className="h-2.5 mt-1" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Guest Mode Banner */}
      {!isAuthLoading && !user && (
        <div className="rounded-2xl bg-slate-50 border border-slate-200 p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm">
          <div className="flex items-center space-x-3.5">
            <div className="p-2.5 rounded-xl bg-emerald-50 text-emerald-600 flex-shrink-0 border border-emerald-200">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-xs font-semibold text-slate-900 tracking-tight">Guest Preview Mode</h2>
              <p className="text-[11px] sm:text-xs text-slate-600 mt-0.5 leading-relaxed">
                You are exploring AUREN without an active session. Sign in to sync your tasks, projects, strategic goals, reflections, and persistent knowledge.
              </p>
            </div>
          </div>
          <Link
            to="/chat"
            className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-xs font-semibold transition whitespace-nowrap text-center shadow-md shadow-emerald-500/20"
          >
            Open Assistant
          </Link>
        </div>
      )}

      {/* Central AI Assistant Entry Point (Raycast/Linear Style Command Bar) */}
      <div className="relative rounded-2xl bg-white border border-slate-200 p-5 sm:p-6 shadow-sm space-y-4">
        {/* Subtle Ambient Ray */}
        <div className="absolute top-0 right-1/4 w-72 h-32 bg-emerald-500/5 blur-3xl pointer-events-none rounded-full" />

        <div className="flex items-center justify-between relative z-10">
          <div className="flex items-center space-x-2 text-xs font-semibold text-amber-600">
            <Sparkles className="w-4 h-4 text-amber-500 animate-pulse" />
            <span className="tracking-tight text-slate-900 font-bold">AUREN Intelligence Composer</span>
          </div>
          <Link
            to="/chat"
            className="text-[11px] text-slate-500 hover:text-emerald-600 font-medium flex items-center space-x-1 transition-colors"
          >
            <span>Open Dedicated Assistant</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <form onSubmit={handleQuickAsk} className="flex items-center gap-2 p-1.5 sm:p-2 bg-slate-50 border border-slate-200 rounded-2xl focus-within:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-500/20 transition-all shadow-inner relative z-10">
          <div className="pl-3 text-slate-400 pointer-events-none flex-shrink-0">
            <Command className="w-4 h-4" />
          </div>
          <input
            type="text"
            value={promptInput}
            onChange={(e) => setPromptInput(e.target.value)}
            placeholder="Ask AUREN anything, plan today's priorities, or break down a project..."
            className="flex-1 bg-transparent border-0 outline-none px-2 py-2 text-xs sm:text-sm text-slate-900 placeholder-slate-400 focus:ring-0"
          />
          <button
            type="submit"
            className={`h-8 w-8 sm:h-9 sm:w-9 rounded-full flex items-center justify-center flex-shrink-0 transition-all cursor-pointer ${
              promptInput.trim()
                ? 'bg-emerald-500 hover:bg-emerald-400 active:scale-95 text-white shadow-md shadow-emerald-500/25'
                : 'bg-slate-200 text-slate-400 hover:bg-slate-300 border border-slate-200'
            }`}
            title="Ask AUREN"
            aria-label="Ask AUREN"
          >
            <Send className="w-3.5 h-3.5 ml-0.5" />
          </button>
        </form>

        {/* Suggestion Chips */}
        <div className="flex items-center gap-2 overflow-x-auto pt-1 text-[11px] scrollbar-none text-slate-500 relative z-10">
          <span className="text-slate-500 text-[10px] uppercase tracking-wider font-semibold">Suggested:</span>
          <button
            type="button"
            onClick={() => {
              setPromptInput('What are my highest priority tasks and commitments today?');
            }}
            className="px-3 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 hover:text-slate-900 transition whitespace-nowrap shadow-sm text-xs"
          >
            Today's priorities
          </button>
          <button
            type="button"
            onClick={() => {
              setPromptInput('Break down my active goals into concrete next steps.');
            }}
            className="px-3 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 hover:text-slate-900 transition whitespace-nowrap shadow-sm text-xs"
          >
            Break down goals
          </button>
          <button
            type="button"
            onClick={() => {
              setPromptInput('Help me review my active projects and identify next actions.');
            }}
            className="px-3 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-700 hover:text-slate-900 transition whitespace-nowrap shadow-sm text-xs"
          >
            Review active projects
          </button>
        </div>
      </div>

      {/* Quick Actions Bar */}
      <div className="flex flex-wrap items-center gap-2 sm:gap-2.5">
        <Link
          to="/tasks"
          className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 text-xs font-semibold text-emerald-800 transition shadow-sm"
        >
          <Plus className="w-3.5 h-3.5 text-emerald-600" />
          <span>New Task</span>
        </Link>
        <Link
          to="/projects"
          className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-xs font-semibold text-slate-800 transition shadow-sm"
        >
          <Plus className="w-3.5 h-3.5 text-slate-700" />
          <span>New Project</span>
        </Link>
        <Link
          to="/goals"
          className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-amber-50 hover:bg-amber-100 border border-amber-200 text-xs font-semibold text-amber-800 transition shadow-sm"
        >
          <Plus className="w-3.5 h-3.5 text-amber-600" />
          <span>New Goal</span>
        </Link>
        <Link
          to="/journal"
          className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-rose-50 hover:bg-rose-100 border border-rose-200 text-xs font-semibold text-rose-800 transition shadow-sm"
        >
          <BookOpen className="w-3.5 h-3.5 text-rose-600" />
          <span>Write Reflection</span>
        </Link>
        <Link
          to="/operations"
          className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 text-xs font-semibold text-emerald-800 transition shadow-sm"
        >
          <MapPin className="w-3.5 h-3.5 text-emerald-600" />
          <span>Operations & GPS</span>
        </Link>
        <Link
          to="/search"
          className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-xs font-semibold text-slate-700 transition shadow-sm"
        >
          <Search className="w-3.5 h-3.5 text-slate-500" />
          <span>Search Everything</span>
        </Link>
      </div>

      {/* Main 2-Column Life Management Radar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2 spans): Tasks and Active Projects */}
        <div className="lg:col-span-2 space-y-6">
          {/* Priority Tasks Radar */}
          <div className="rounded-2xl bg-white border border-slate-200 p-5 space-y-4 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <CheckSquare className="w-4 h-4 text-emerald-600" />
                <h2 className="text-sm font-bold text-slate-900 tracking-tight">Priority Next Actions</h2>
              </div>
              <Link
                to="/tasks"
                className="text-[11px] text-slate-500 hover:text-emerald-600 flex items-center space-x-1 transition font-medium"
              >
                <span>View All Tasks</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isAuthLoading || isLoadingTasks ? (
              <div className="p-6 text-center text-xs text-slate-500">Loading priority tasks...</div>
            ) : !user ? (
              <div className="p-6 text-center rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                <CheckSquare className="w-6 h-6 text-emerald-600 mx-auto opacity-80" />
                <p className="text-xs text-slate-900 font-semibold">Guest Mode</p>
                <p className="text-[11px] text-slate-500 max-w-sm mx-auto leading-relaxed">
                  Sign in to view, prioritize, and check off your personal tasks.
                </p>
              </div>
            ) : tasksError ? (
              <div className="p-5 text-center rounded-2xl bg-slate-50 border border-slate-200 text-xs text-slate-600">
                Tasks temporarily unavailable.
              </div>
            ) : !tasksData?.items.length ? (
              <div className="p-7 text-center rounded-2xl bg-slate-50 border border-slate-200 space-y-2.5">
                <CheckCircle2 className="w-6 h-6 text-emerald-600 mx-auto" />
                <p className="text-xs text-slate-900 font-semibold">All tasks cleared</p>
                <p className="text-[11px] text-slate-500 max-w-sm mx-auto leading-relaxed">
                  You have no pending tasks. Click below to add an actionable item.
                </p>
                <Link
                  to="/tasks"
                  className="inline-block mt-2 px-3.5 py-1.5 rounded-xl bg-white hover:bg-slate-100 border border-slate-300 text-xs font-semibold text-slate-800 transition shadow-sm"
                >
                  Create Task
                </Link>
              </div>
            ) : (
              <div className="space-y-2">
                {tasksData.items.map((task) => (
                  <div
                    key={task.id}
                    className="flex items-center justify-between p-3.5 rounded-xl bg-slate-50 hover:bg-slate-100/80 border border-slate-200 transition-all shadow-sm"
                  >
                    <div className="flex items-center space-x-2.5 min-w-0">
                      <button
                        type="button"
                        onClick={() => handleToggleTask(task)}
                        title="Toggle task status"
                        aria-label="Toggle task status"
                        className="p-2 -m-1.5 touch-target flex items-center justify-center flex-shrink-0"
                      >
                        <span
                          className={`w-4 h-4 rounded border flex items-center justify-center transition ${
                            task.status === 'completed'
                              ? 'bg-emerald-600 border-emerald-500 text-white'
                              : 'border-slate-400 bg-white hover:border-slate-600'
                          }`}
                        >
                          {task.status === 'completed' && <CheckCircle2 className="w-3.5 h-3.5 text-white" />}
                        </span>
                      </button>
                      <div className="min-w-0">
                        <span
                          className={`text-xs block truncate font-medium ${
                            task.status === 'completed' ? 'line-through text-slate-400' : 'text-slate-900'
                          }`}
                        >
                          {task.title}
                        </span>
                        {task.due_date && (
                          <span className="text-[10px] text-slate-500 flex items-center space-x-1 mt-0.5 font-mono">
                            <Clock className="w-3 h-3 text-slate-400" />
                            <span>{task.due_date}</span>
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center space-x-2 pl-2 flex-shrink-0">
                      {task.priority && (
                        <span
                          className={`text-[9px] font-semibold uppercase px-2 py-0.5 rounded border tracking-wider ${
                            task.priority === 'urgent'
                              ? 'bg-rose-50 text-rose-700 border-rose-200'
                              : task.priority === 'high'
                              ? 'bg-amber-50 text-amber-700 border-amber-200'
                              : task.priority === 'medium'
                              ? 'bg-slate-100 text-slate-700 border-slate-200'
                              : 'bg-slate-100 text-slate-600 border-slate-200'
                          }`}
                        >
                          {task.priority}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Active Projects Radar */}
          <div className="rounded-2xl bg-white border border-slate-200 p-5 space-y-4 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <FolderKanban className="w-4 h-4 text-emerald-600" />
                <h2 className="text-sm font-bold text-slate-900 tracking-tight">Active Project Workspaces</h2>
              </div>
              <Link
                to="/projects"
                className="text-[11px] text-slate-500 hover:text-emerald-600 flex items-center space-x-1 transition font-medium"
              >
                <span>View All Projects</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isAuthLoading || isLoadingProjects ? (
              <div className="p-6 text-center text-xs text-slate-500">Loading projects...</div>
            ) : !user ? (
              <div className="p-6 text-center rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                <FolderKanban className="w-6 h-6 text-emerald-600 mx-auto opacity-80" />
                <p className="text-xs text-slate-900 font-semibold">Guest Mode</p>
                <p className="text-[11px] text-slate-500 max-w-sm mx-auto leading-relaxed">
                  Sign in to view your multi-step project workspaces and completion progress.
                </p>
              </div>
            ) : projectsError ? (
              <div className="p-5 text-center rounded-2xl bg-slate-50 border border-slate-200 text-xs text-slate-600">
                Projects temporarily unavailable.
              </div>
            ) : !projectsData?.items.length ? (
              <div className="p-7 text-center rounded-2xl bg-slate-50 border border-slate-200 space-y-2.5">
                <FolderKanban className="w-6 h-6 text-slate-400 mx-auto" />
                <p className="text-xs text-slate-900 font-semibold">No active projects</p>
                <p className="text-[11px] text-slate-500">Create a project workspace to coordinate complex goals.</p>
                <Link
                  to="/projects"
                  className="inline-block mt-2 px-3.5 py-1.5 rounded-xl bg-white hover:bg-slate-100 border border-slate-300 text-xs font-semibold text-slate-800 transition shadow-sm"
                >
                  Create Project
                </Link>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                {projectsData.items.map((project) => (
                  <Link
                    key={project.id}
                    to="/projects"
                    className="p-4 rounded-xl bg-slate-50 hover:bg-slate-100/80 border border-slate-200 transition-all space-y-3 block shadow-sm group"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-900 group-hover:text-emerald-700 truncate pr-2 tracking-tight">
                        {project.name}
                      </span>
                      <span className="text-[10px] font-mono text-emerald-600 font-bold">
                        {project.progress_percentage ?? 0}%
                      </span>
                    </div>
                    <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 rounded-full transition-all duration-300 shadow-sm"
                        style={{ width: `${project.progress_percentage ?? 0}%` }}
                      />
                    </div>
                    {project.description && (
                      <p className="text-[11px] text-slate-600 line-clamp-1 leading-relaxed">{project.description}</p>
                    )}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Strategic Goals & Recent Dialogue */}
        <div className="space-y-6">
          {/* Strategic Goals Radar */}
          <div className="rounded-2xl bg-white border border-slate-200 p-5 space-y-4 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Target className="w-4 h-4 text-emerald-600" />
                <h2 className="text-sm font-bold text-slate-900 tracking-tight">Strategic Goals</h2>
              </div>
              <Link
                to="/goals"
                className="text-[11px] text-slate-500 hover:text-emerald-600 flex items-center space-x-1 transition font-medium"
              >
                <span>View Goals</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isAuthLoading || isLoadingGoals ? (
              <div className="p-6 text-center text-xs text-slate-500">Loading goals...</div>
            ) : !user ? (
              <div className="p-6 text-center rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                <Target className="w-5 h-5 text-emerald-600 mx-auto opacity-80" />
                <p className="text-xs text-slate-900 font-semibold">Guest Mode</p>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Sign in to track strategic objectives, measurable milestones, and deadlines.
                </p>
              </div>
            ) : goalsError ? (
              <div className="p-5 text-center rounded-2xl bg-slate-50 border border-slate-200 text-xs text-slate-600">
                Goals temporarily unavailable.
              </div>
            ) : !goalsData?.items.length ? (
              <div className="p-6 text-center rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                <Target className="w-5 h-5 text-slate-400 mx-auto" />
                <p className="text-xs text-slate-900 font-semibold">No active goals</p>
                <p className="text-[11px] text-slate-500">Set strategic horizons to orient your day-to-day work.</p>
                <Link
                  to="/goals"
                  className="inline-block mt-2 px-3.5 py-1.5 rounded-xl bg-white hover:bg-slate-100 border border-slate-300 text-xs font-semibold text-slate-800 transition shadow-sm"
                >
                  Create Goal
                </Link>
              </div>
            ) : (
              <div className="space-y-3">
                {goalsData.items.map((goal) => (
                  <div key={goal.id} className="p-3.5 rounded-xl bg-slate-50 hover:bg-slate-100/80 border border-slate-200 space-y-2.5 shadow-sm transition-all">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-900 truncate pr-2 tracking-tight">{goal.title}</span>
                      <span className="font-mono text-emerald-600 text-[11px] font-bold flex-shrink-0">
                        {goal.progress_percentage ?? 0}%
                      </span>
                    </div>
                    <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                        style={{ width: `${goal.progress_percentage ?? 0}%` }}
                      />
                    </div>
                    {goal.target_date && (
                      <span className="text-[10px] text-slate-500 block font-mono">Target: {goal.target_date}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Conversations */}
          <div className="rounded-2xl bg-white border border-slate-200 p-5 space-y-4 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <MessageSquare className="w-4 h-4 text-emerald-600" />
                <h2 className="text-sm font-bold text-slate-900 tracking-tight">Recent Conversations</h2>
              </div>
              <Link
                to="/chat"
                className="text-[11px] text-slate-500 hover:text-emerald-600 flex items-center space-x-1 transition font-medium"
              >
                <span>New Dialogue</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isAuthLoading || isLoadingConversations ? (
              <div className="p-6 text-center text-xs text-slate-500">Loading dialogue...</div>
            ) : !user ? (
              <div className="p-6 text-center rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                <MessageSquare className="w-5 h-5 text-emerald-600 mx-auto opacity-80" />
                <p className="text-xs text-slate-900 font-semibold">Guest Mode</p>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Sign in to access your persistent conversations across devices.
                </p>
                <Link
                  to="/chat"
                  className="inline-block mt-2 px-3.5 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-xs font-semibold text-white transition shadow-sm"
                >
                  Start Dialogue
                </Link>
              </div>
            ) : conversationsError ? (
              <div className="p-5 text-center rounded-2xl bg-slate-50 border border-slate-200 text-xs text-slate-600">
                Dialogue history temporarily unavailable.
              </div>
            ) : !conversations.length ? (
              <div className="p-6 text-center rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                <MessageSquare className="w-5 h-5 text-slate-400 mx-auto" />
                <p className="text-xs text-slate-600">No active conversations</p>
                <Link
                  to="/chat"
                  className="inline-block mt-2 px-3.5 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-xs font-semibold text-white transition shadow-sm"
                >
                  Start Dialogue
                </Link>
              </div>
            ) : (
              <div className="space-y-1.5">
                {conversations.slice(0, 4).map((conv) => (
                  <Link
                    key={conv.id}
                    to="/chat/$conversationId"
                    params={{ conversationId: conv.id }}
                    className="p-3 rounded-xl hover:bg-slate-50 transition flex items-center justify-between group border border-transparent hover:border-slate-200"
                  >
                    <div className="min-w-0 pr-2">
                      <span className="text-xs text-slate-800 group-hover:text-emerald-700 block truncate font-medium tracking-tight">
                        {conv.title || 'Untitled Dialogue'}
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {new Date(conv.updated_at).toLocaleDateString()}
                      </span>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-emerald-600 flex-shrink-0 transition-transform group-hover:translate-x-0.5" />
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

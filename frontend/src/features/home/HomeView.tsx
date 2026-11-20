/**
 * Home — AUREN Personal AI Command Center.
 * Unified operating environment integrating daily planning, high-priority tasks,
 * active projects, strategic goals, recent conversations, and central AI entry point.
 * Elevated with AUREN Obsidian, Graphite & Champagne Design System.
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
  ChevronRight,
  Sparkles,
  Command,
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
  const { user, isLoading: isAuthLoading } = useAuth();
  const navigate = useNavigate();

  const [promptInput, setPromptInput] = useState('');

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

  const todayFormatted = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  });

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-y-auto text-slate-100 p-3.5 sm:p-7 space-y-5 sm:space-y-7 max-w-7xl mx-auto scrollbar-thin">
      {/* Top Briefing Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-5 sm:pb-6 border-b border-white/[0.08] gap-4 sm:gap-6 relative">
        <div className="space-y-1">
          <div className="flex items-center space-x-2 text-xs font-medium text-champagne-300 mb-1">
            <Calendar className="w-3.5 h-3.5 text-champagne-400" />
            <span className="tracking-tight">{todayFormatted}</span>
            <span className="text-slate-600">•</span>
            <span className="text-slate-400 font-normal">Personal Command Center</span>
          </div>
          <h1 className="text-2xl sm:text-4xl font-extrabold tracking-tight bg-gradient-to-r from-slate-100 via-slate-200 to-champagne-200 bg-clip-text text-transparent">
            {getGreeting()}{user?.email ? `, ${user.email.split('@')[0]}` : ''}
          </h1>
          <p className="text-xs sm:text-sm text-slate-400 max-w-xl leading-relaxed">
            Overview of your daily commitments, strategic milestones, and intelligence streams.
          </p>
        </div>

        {/* Quick KPI Snapshot */}
        {dashboard && (
          <div className="flex items-center gap-2.5 sm:gap-3.5 overflow-x-auto w-full md:w-auto scrollbar-none py-1">
            <div className="flex-1 md:flex-none px-4 py-2.5 sm:px-5 sm:py-3 rounded-2xl bg-white/[0.03] border border-white/[0.08] shadow-subtle-elevation text-center min-w-[80px] hover:border-white/[0.15] transition-all group">
              <span className="text-[10px] text-slate-400 uppercase tracking-widest block font-semibold">Tasks</span>
              <span className="text-xl sm:text-2xl font-bold text-indigo-400 tracking-tight group-hover:scale-105 transition-transform inline-block">
                {dashboard.active_tasks_count ?? 0}
              </span>
            </div>
            <div className="flex-1 md:flex-none px-4 py-2.5 sm:px-5 sm:py-3 rounded-2xl bg-white/[0.03] border border-white/[0.08] shadow-subtle-elevation text-center min-w-[80px] hover:border-white/[0.15] transition-all group">
              <span className="text-[10px] text-slate-400 uppercase tracking-widest block font-semibold">Projects</span>
              <span className="text-xl sm:text-2xl font-bold text-emerald-400 tracking-tight group-hover:scale-105 transition-transform inline-block">
                {dashboard.active_projects_count ?? 0}
              </span>
            </div>
            <div className="flex-1 md:flex-none px-4 py-2.5 sm:px-5 sm:py-3 rounded-2xl bg-white/[0.03] border border-white/[0.08] shadow-subtle-elevation text-center min-w-[80px] hover:border-white/[0.15] transition-all group">
              <span className="text-[10px] text-slate-400 uppercase tracking-widest block font-semibold">Goals</span>
              <span className="text-xl sm:text-2xl font-bold text-champagne-300 tracking-tight group-hover:scale-105 transition-transform inline-block">
                {dashboard.active_goals_count ?? 0}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Guest Mode Banner */}
      {!isAuthLoading && !user && (
        <div className="rounded-2xl bg-gradient-to-r from-indigo-950/40 via-slate-900/60 to-champagne-950/20 border border-indigo-800/40 p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-subtle-elevation backdrop-blur-md">
          <div className="flex items-center space-x-3.5">
            <div className="p-2.5 rounded-xl bg-indigo-600/20 text-indigo-400 flex-shrink-0 border border-indigo-500/30 shadow-glow-indigo">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-xs font-semibold text-slate-100 tracking-tight">Guest Preview Mode</h2>
              <p className="text-[11px] sm:text-xs text-slate-400 mt-0.5 leading-relaxed">
                You are exploring AUREN without an active session. Sign in to sync your tasks, projects, strategic goals, reflections, and persistent knowledge.
              </p>
            </div>
          </div>
          <Link
            to="/chat"
            className="px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white text-xs font-semibold transition whitespace-nowrap text-center shadow-md shadow-indigo-600/25 hover:shadow-indigo-600/40"
          >
            Open Assistant
          </Link>
        </div>
      )}

      {/* Central AI Assistant Entry Point (Raycast/Linear Style Command Bar) */}
      <div className="relative rounded-2xl bg-gradient-to-r from-indigo-950/30 via-slate-900/80 to-slate-950/90 border border-white/[0.09] p-5 sm:p-6 shadow-card-elevation space-y-4">
        {/* Subtle Ambient Ray */}
        <div className="absolute top-0 right-1/4 w-72 h-32 bg-indigo-500/10 blur-3xl pointer-events-none rounded-full" />

        <div className="flex items-center justify-between relative z-10">
          <div className="flex items-center space-x-2 text-xs font-semibold text-champagne-300">
            <Sparkles className="w-4 h-4 text-champagne-400 animate-pulse" />
            <span className="tracking-tight">AUREN Intelligence Composer</span>
          </div>
          <Link
            to="/chat"
            className="text-[11px] text-slate-400 hover:text-champagne-300 font-medium flex items-center space-x-1 transition-colors"
          >
            <span>Open Dedicated Assistant</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <form onSubmit={handleQuickAsk} className="relative flex items-center z-10">
          <div className="absolute left-4 text-slate-500 pointer-events-none">
            <Command className="w-4 h-4" />
          </div>
          <input
            type="text"
            value={promptInput}
            onChange={(e) => setPromptInput(e.target.value)}
            placeholder="Ask AUREN anything, plan today's priorities, or break down a project..."
            className="w-full bg-slate-950/90 border border-white/[0.1] rounded-xl pl-11 pr-12 py-3.5 text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-champagne-400/70 focus:ring-1 focus:ring-champagne-400/40 shadow-inner transition-all"
          />
          <button
            type="submit"
            className="absolute right-2.5 p-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition shadow-md shadow-indigo-600/30 hover:scale-105 active:scale-95"
            title="Ask AUREN"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>

        {/* Suggestion Chips */}
        <div className="flex items-center gap-2 overflow-x-auto pt-1 text-[11px] scrollbar-none text-slate-400 relative z-10">
          <span className="text-slate-500 text-[10px] uppercase tracking-wider font-semibold">Suggested:</span>
          <button
            type="button"
            onClick={() => {
              setPromptInput('What are my highest priority tasks and commitments today?');
            }}
            className="px-3 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.07] text-slate-300 hover:text-white transition whitespace-nowrap shadow-sm"
          >
            Today's priorities
          </button>
          <button
            type="button"
            onClick={() => {
              setPromptInput('Break down my active goals into concrete next steps.');
            }}
            className="px-3 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.07] text-slate-300 hover:text-white transition whitespace-nowrap shadow-sm"
          >
            Break down goals
          </button>
          <button
            type="button"
            onClick={() => {
              setPromptInput('Help me review my active projects and identify next actions.');
            }}
            className="px-3 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.07] text-slate-300 hover:text-white transition whitespace-nowrap shadow-sm"
          >
            Review active projects
          </button>
        </div>
      </div>

      {/* Quick Actions Bar */}
      <div className="flex flex-wrap items-center gap-2.5">
        <Link
          to="/tasks"
          className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] hover:border-white/[0.14] text-xs font-medium text-slate-300 hover:text-white transition shadow-sm"
        >
          <Plus className="w-3.5 h-3.5 text-indigo-400" />
          <span>New Task</span>
        </Link>
        <Link
          to="/projects"
          className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] hover:border-white/[0.14] text-xs font-medium text-slate-300 hover:text-white transition shadow-sm"
        >
          <Plus className="w-3.5 h-3.5 text-emerald-400" />
          <span>New Project</span>
        </Link>
        <Link
          to="/goals"
          className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] hover:border-white/[0.14] text-xs font-medium text-slate-300 hover:text-white transition shadow-sm"
        >
          <Plus className="w-3.5 h-3.5 text-champagne-300" />
          <span>New Goal</span>
        </Link>
        <Link
          to="/journal"
          className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] hover:border-white/[0.14] text-xs font-medium text-slate-300 hover:text-white transition shadow-sm"
        >
          <BookOpen className="w-3.5 h-3.5 text-sky-400" />
          <span>Write Reflection</span>
        </Link>
        <Link
          to="/search"
          className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] hover:border-white/[0.14] text-xs font-medium text-slate-300 hover:text-white transition shadow-sm"
        >
          <Search className="w-3.5 h-3.5 text-slate-400" />
          <span>Search Everything</span>
        </Link>
      </div>

      {/* Main 2-Column Life Management Radar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2 spans): Tasks and Active Projects */}
        <div className="lg:col-span-2 space-y-6">
          {/* Priority Tasks Radar */}
          <div className="rounded-2xl bg-white/[0.02] border border-white/[0.08] p-5 space-y-4 shadow-subtle-elevation">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <CheckSquare className="w-4 h-4 text-indigo-400" />
                <h2 className="text-sm font-semibold text-slate-100 tracking-tight">Priority Next Actions</h2>
              </div>
              <Link
                to="/tasks"
                className="text-[11px] text-slate-400 hover:text-champagne-300 flex items-center space-x-1 transition"
              >
                <span>View All Tasks</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isAuthLoading || isLoadingTasks ? (
              <div className="p-6 text-center text-xs text-slate-500">Loading priority tasks...</div>
            ) : !user ? (
              <div className="p-6 text-center rounded-2xl bg-slate-950/60 border border-white/[0.06] space-y-2">
                <CheckSquare className="w-6 h-6 text-indigo-400 mx-auto opacity-80" />
                <p className="text-xs text-slate-300 font-medium">Guest Mode</p>
                <p className="text-[11px] text-slate-500 max-w-sm mx-auto leading-relaxed">
                  Sign in to view, prioritize, and check off your personal tasks.
                </p>
              </div>
            ) : tasksError ? (
              <div className="p-5 text-center rounded-2xl bg-slate-900/40 border border-white/[0.06] text-xs text-slate-400">
                Tasks temporarily unavailable.
              </div>
            ) : !tasksData?.items.length ? (
              <div className="p-7 text-center rounded-2xl bg-slate-950/60 border border-white/[0.06] space-y-2.5">
                <CheckCircle2 className="w-6 h-6 text-emerald-500 mx-auto" />
                <p className="text-xs text-slate-300 font-medium">All tasks cleared</p>
                <p className="text-[11px] text-slate-500 max-w-sm mx-auto leading-relaxed">
                  You have no pending tasks. Click below to add an actionable item.
                </p>
                <Link
                  to="/tasks"
                  className="inline-block mt-2 px-3.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs text-slate-300 hover:text-white transition shadow-sm"
                >
                  Create Task
                </Link>
              </div>
            ) : (
              <div className="space-y-2">
                {tasksData.items.map((task) => (
                  <div
                    key={task.id}
                    className="flex items-center justify-between p-3.5 rounded-xl bg-white/[0.025] hover:bg-white/[0.055] border border-white/[0.06] hover:border-white/[0.1] transition-all shadow-sm"
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
                              : 'border-slate-600 hover:border-slate-400'
                          }`}
                        >
                          {task.status === 'completed' && <CheckCircle2 className="w-3.5 h-3.5" />}
                        </span>
                      </button>
                      <div className="min-w-0">
                        <span
                          className={`text-xs block truncate font-medium ${
                            task.status === 'completed' ? 'line-through text-slate-500' : 'text-slate-200'
                          }`}
                        >
                          {task.title}
                        </span>
                        {task.due_date && (
                          <span className="text-[10px] text-slate-500 flex items-center space-x-1 mt-0.5 font-mono">
                            <Clock className="w-3 h-3" />
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
                              ? 'bg-rose-950/60 text-rose-300 border-rose-800/50'
                              : task.priority === 'high'
                              ? 'bg-amber-950/60 text-amber-300 border-amber-800/50'
                              : task.priority === 'medium'
                              ? 'bg-indigo-950/60 text-indigo-300 border-indigo-800/50'
                              : 'bg-slate-800/80 text-slate-400 border-slate-700/80'
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
          <div className="rounded-2xl bg-white/[0.02] border border-white/[0.08] p-5 space-y-4 shadow-subtle-elevation">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <FolderKanban className="w-4 h-4 text-emerald-400" />
                <h2 className="text-sm font-semibold text-slate-100 tracking-tight">Active Project Workspaces</h2>
              </div>
              <Link
                to="/projects"
                className="text-[11px] text-slate-400 hover:text-champagne-300 flex items-center space-x-1 transition"
              >
                <span>View All Projects</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isAuthLoading || isLoadingProjects ? (
              <div className="p-6 text-center text-xs text-slate-500">Loading projects...</div>
            ) : !user ? (
              <div className="p-6 text-center rounded-2xl bg-slate-950/60 border border-white/[0.06] space-y-2">
                <FolderKanban className="w-6 h-6 text-emerald-400 mx-auto opacity-80" />
                <p className="text-xs text-slate-300 font-medium">Guest Mode</p>
                <p className="text-[11px] text-slate-500 max-w-sm mx-auto leading-relaxed">
                  Sign in to view your multi-step project workspaces and completion progress.
                </p>
              </div>
            ) : projectsError ? (
              <div className="p-5 text-center rounded-2xl bg-slate-900/40 border border-white/[0.06] text-xs text-slate-400">
                Projects temporarily unavailable.
              </div>
            ) : !projectsData?.items.length ? (
              <div className="p-7 text-center rounded-2xl bg-slate-950/60 border border-white/[0.06] space-y-2.5">
                <FolderKanban className="w-6 h-6 text-slate-600 mx-auto" />
                <p className="text-xs text-slate-300 font-medium">No active projects</p>
                <p className="text-[11px] text-slate-500">Create a project workspace to coordinate complex goals.</p>
                <Link
                  to="/projects"
                  className="inline-block mt-2 px-3.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs text-slate-300 hover:text-white transition shadow-sm"
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
                    className="p-4 rounded-xl bg-white/[0.025] hover:bg-white/[0.055] border border-white/[0.06] hover:border-white/[0.1] transition-all space-y-3 block shadow-sm group"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-200 group-hover:text-white truncate pr-2 tracking-tight">
                        {project.name}
                      </span>
                      <span className="text-[10px] font-mono text-emerald-400 font-semibold">
                        {project.progress_percentage ?? 0}%
                      </span>
                    </div>
                    <div className="w-full bg-slate-800/80 rounded-full h-1.5 overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 rounded-full transition-all duration-300 shadow-sm"
                        style={{ width: `${project.progress_percentage ?? 0}%` }}
                      />
                    </div>
                    {project.description && (
                      <p className="text-[11px] text-slate-400 line-clamp-1 leading-relaxed">{project.description}</p>
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
          <div className="rounded-2xl bg-white/[0.02] border border-white/[0.08] p-5 space-y-4 shadow-subtle-elevation">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Target className="w-4 h-4 text-champagne-400" />
                <h2 className="text-sm font-semibold text-slate-100 tracking-tight">Strategic Goals</h2>
              </div>
              <Link
                to="/goals"
                className="text-[11px] text-slate-400 hover:text-champagne-300 flex items-center space-x-1 transition"
              >
                <span>View Goals</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isAuthLoading || isLoadingGoals ? (
              <div className="p-6 text-center text-xs text-slate-500">Loading goals...</div>
            ) : !user ? (
              <div className="p-6 text-center rounded-2xl bg-slate-950/60 border border-white/[0.06] space-y-2">
                <Target className="w-5 h-5 text-champagne-400 mx-auto opacity-80" />
                <p className="text-xs text-slate-300 font-medium">Guest Mode</p>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Sign in to track strategic objectives, measurable milestones, and deadlines.
                </p>
              </div>
            ) : goalsError ? (
              <div className="p-5 text-center rounded-2xl bg-slate-900/40 border border-white/[0.06] text-xs text-slate-400">
                Goals temporarily unavailable.
              </div>
            ) : !goalsData?.items.length ? (
              <div className="p-6 text-center rounded-2xl bg-slate-950/60 border border-white/[0.06] space-y-2">
                <Target className="w-5 h-5 text-slate-600 mx-auto" />
                <p className="text-xs text-slate-300 font-medium">No active goals</p>
                <p className="text-[11px] text-slate-500">Set strategic horizons to orient your day-to-day work.</p>
                <Link
                  to="/goals"
                  className="inline-block mt-2 px-3.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs text-slate-300 hover:text-white transition shadow-sm"
                >
                  Create Goal
                </Link>
              </div>
            ) : (
              <div className="space-y-3">
                {goalsData.items.map((goal) => (
                  <div key={goal.id} className="p-3.5 rounded-xl bg-white/[0.025] hover:bg-white/[0.055] border border-white/[0.06] space-y-2.5 shadow-sm transition-all">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-200 truncate pr-2 tracking-tight">{goal.title}</span>
                      <span className="font-mono text-champagne-300 text-[11px] font-semibold flex-shrink-0">
                        {goal.progress_percentage ?? 0}%
                      </span>
                    </div>
                    <div className="w-full bg-slate-800/80 rounded-full h-1.5 overflow-hidden">
                      <div
                        className="h-full bg-champagne-400 rounded-full transition-all duration-300"
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
          <div className="rounded-2xl bg-white/[0.02] border border-white/[0.08] p-5 space-y-4 shadow-subtle-elevation">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <MessageSquare className="w-4 h-4 text-sky-400" />
                <h2 className="text-sm font-semibold text-slate-100 tracking-tight">Recent Conversations</h2>
              </div>
              <Link
                to="/chat"
                className="text-[11px] text-slate-400 hover:text-champagne-300 flex items-center space-x-1 transition"
              >
                <span>New Dialogue</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isAuthLoading || isLoadingConversations ? (
              <div className="p-6 text-center text-xs text-slate-500">Loading dialogue...</div>
            ) : !user ? (
              <div className="p-6 text-center rounded-2xl bg-slate-950/60 border border-white/[0.06] space-y-2">
                <MessageSquare className="w-5 h-5 text-sky-400 mx-auto opacity-80" />
                <p className="text-xs text-slate-300 font-medium">Guest Mode</p>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Sign in to access your persistent conversations across devices.
                </p>
                <Link
                  to="/chat"
                  className="inline-block mt-2 px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white transition shadow-sm"
                >
                  Start Dialogue
                </Link>
              </div>
            ) : conversationsError ? (
              <div className="p-5 text-center rounded-2xl bg-slate-900/40 border border-white/[0.06] text-xs text-slate-400">
                Dialogue history temporarily unavailable.
              </div>
            ) : !conversations.length ? (
              <div className="p-6 text-center rounded-2xl bg-slate-950/60 border border-white/[0.06] space-y-2">
                <MessageSquare className="w-5 h-5 text-slate-600 mx-auto" />
                <p className="text-xs text-slate-400">No active conversations</p>
                <Link
                  to="/chat"
                  className="inline-block mt-2 px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white transition shadow-sm"
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
                    className="p-3 rounded-xl hover:bg-white/[0.04] transition flex items-center justify-between group border border-transparent hover:border-white/[0.08]"
                  >
                    <div className="min-w-0 pr-2">
                      <span className="text-xs text-slate-300 group-hover:text-white block truncate font-medium tracking-tight">
                        {conv.title || 'Untitled Dialogue'}
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {new Date(conv.updated_at).toLocaleDateString()}
                      </span>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-slate-300 flex-shrink-0 transition-transform group-hover:translate-x-0.5" />
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

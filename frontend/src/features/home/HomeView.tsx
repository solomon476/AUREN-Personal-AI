/**
 * Home — AUREN Personal AI Command Center.
 * Unified operating environment integrating daily planning, high-priority tasks,
 * active projects, strategic goals, recent conversations, and central AI entry point.
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
  const { user } = useAuth();
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
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-y-auto text-slate-100 p-6 space-y-6">
      {/* Top Briefing Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-5 border-b border-slate-800/80 gap-4">
        <div>
          <div className="flex items-center space-x-2 text-xs font-medium text-indigo-400 mb-1">
            <Calendar className="w-3.5 h-3.5" />
            <span>{todayFormatted}</span>
            <span>•</span>
            <span className="text-slate-400">Personal Command Center</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-slate-100 via-slate-200 to-indigo-200 bg-clip-text text-transparent">
            {getGreeting()}{user?.email ? `, ${user.email.split('@')[0]}` : ''}
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Overview of your daily commitments, strategic milestones, and intelligence streams.
          </p>
        </div>

        {/* Quick KPI Snapshot */}
        {dashboard && (
          <div className="flex items-center gap-3">
            <div className="px-3.5 py-2 rounded-xl bg-slate-900/80 border border-slate-800 text-center min-w-[70px]">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-semibold">Tasks</span>
              <span className="text-lg font-bold text-indigo-400">{dashboard.active_tasks_count}</span>
            </div>
            <div className="px-3.5 py-2 rounded-xl bg-slate-900/80 border border-slate-800 text-center min-w-[70px]">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-semibold">Projects</span>
              <span className="text-lg font-bold text-emerald-400">{dashboard.active_projects_count}</span>
            </div>
            <div className="px-3.5 py-2 rounded-xl bg-slate-900/80 border border-slate-800 text-center min-w-[70px]">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-semibold">Goals</span>
              <span className="text-lg font-bold text-purple-400">{dashboard.active_goals_count}</span>
            </div>
          </div>
        )}
      </div>

      {/* Guest Mode Banner */}
      {!user && (
        <div className="rounded-2xl bg-indigo-950/30 border border-indigo-800/40 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-indigo-600/20 text-indigo-400 flex-shrink-0">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-xs font-semibold text-slate-100">Guest Preview Mode</h2>
              <p className="text-[11px] text-slate-400">
                You are exploring AUREN without an active session. Sign in to sync your tasks, projects, strategic goals, reflections, and persistent knowledge.
              </p>
            </div>
          </div>
          <Link
            to="/chat"
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition whitespace-nowrap text-center shadow-md shadow-indigo-600/20"
          >
            Open Assistant
          </Link>
        </div>
      )}

      {/* Central AI Assistant Entry Point */}
      <div className="relative rounded-2xl bg-gradient-to-r from-indigo-950/40 via-slate-900/70 to-sky-950/40 border border-indigo-800/40 p-5 shadow-xl shadow-indigo-950/10 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 text-xs font-semibold text-indigo-300">
            <Bot className="w-4 h-4 text-indigo-400" />
            <span>AUREN Intelligence Composer</span>
          </div>
          <Link
            to="/chat"
            className="text-[11px] text-indigo-400 hover:text-indigo-300 font-medium flex items-center space-x-1"
          >
            <span>Open Dedicated Assistant</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <form onSubmit={handleQuickAsk} className="relative flex items-center">
          <input
            type="text"
            value={promptInput}
            onChange={(e) => setPromptInput(e.target.value)}
            placeholder="Ask AUREN anything, plan today's priorities, or break down a project..."
            className="w-full bg-slate-950/80 border border-indigo-900/50 rounded-xl pl-4 pr-12 py-3 text-xs md:text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 shadow-inner"
          />
          <button
            type="submit"
            className="absolute right-2 p-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition shadow-md shadow-indigo-600/30"
            title="Ask AUREN"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>

        {/* Suggestion Chips */}
        <div className="flex items-center gap-2 overflow-x-auto pt-1 text-[11px] scrollbar-none text-slate-400">
          <span className="text-slate-500 text-[10px] uppercase font-semibold">Suggested:</span>
          <button
            onClick={() => {
              setPromptInput('What are my highest priority tasks and commitments today?');
            }}
            className="px-2.5 py-1 rounded-lg bg-slate-900/60 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition whitespace-nowrap"
          >
            Today's priorities
          </button>
          <button
            onClick={() => {
              setPromptInput('Break down my active goals into concrete next steps.');
            }}
            className="px-2.5 py-1 rounded-lg bg-slate-900/60 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition whitespace-nowrap"
          >
            Break down goals
          </button>
          <button
            onClick={() => {
              setPromptInput('Help me review my active projects and identify next actions.');
            }}
            className="px-2.5 py-1 rounded-lg bg-slate-900/60 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition whitespace-nowrap"
          >
            Review active projects
          </button>
        </div>
      </div>

      {/* Quick Actions Bar */}
      <div className="flex flex-wrap items-center gap-2.5">
        <Link
          to="/tasks"
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-900/70 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-200 transition"
        >
          <Plus className="w-3.5 h-3.5 text-indigo-400" />
          <span>New Task</span>
        </Link>
        <Link
          to="/projects"
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-900/70 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-200 transition"
        >
          <Plus className="w-3.5 h-3.5 text-emerald-400" />
          <span>New Project</span>
        </Link>
        <Link
          to="/goals"
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-900/70 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-200 transition"
        >
          <Plus className="w-3.5 h-3.5 text-purple-400" />
          <span>New Goal</span>
        </Link>
        <Link
          to="/journal"
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-900/70 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-200 transition"
        >
          <BookOpen className="w-3.5 h-3.5 text-sky-400" />
          <span>Write Reflection</span>
        </Link>
        <Link
          to="/search"
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-900/70 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-200 transition"
        >
          <Search className="w-3.5 h-3.5 text-violet-400" />
          <span>Search Everything</span>
        </Link>
      </div>

      {/* Main 2-Column Life Management Radar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2 spans): Tasks and Active Projects */}
        <div className="lg:col-span-2 space-y-6">
          {/* Priority Tasks Radar */}
          <div className="rounded-2xl bg-slate-900/40 border border-slate-800 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <CheckSquare className="w-4 h-4 text-indigo-400" />
                <h2 className="text-sm font-semibold text-slate-100">Priority Next Actions</h2>
              </div>
              <Link
                to="/tasks"
                className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center space-x-1 transition"
              >
                <span>View All Tasks</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isLoadingTasks ? (
              <div className="p-4 text-center text-xs text-slate-500">Loading priority tasks...</div>
            ) : !user ? (
              <div className="p-5 text-center rounded-xl bg-slate-950/50 border border-slate-800/60 space-y-2">
                <CheckSquare className="w-6 h-6 text-indigo-400 mx-auto" />
                <p className="text-xs text-slate-300 font-medium">Guest Mode</p>
                <p className="text-[11px] text-slate-500">
                  Sign in to view, prioritize, and check off your personal tasks.
                </p>
              </div>
            ) : tasksError ? (
              <div className="p-4 text-center rounded-xl bg-slate-900/40 border border-slate-800 text-xs text-slate-400">
                Tasks temporarily unavailable.
              </div>
            ) : !tasksData?.items.length ? (
              <div className="p-6 text-center rounded-xl bg-slate-950/50 border border-slate-800/60 space-y-2">
                <CheckCircle2 className="w-6 h-6 text-emerald-500 mx-auto" />
                <p className="text-xs text-slate-300 font-medium">All tasks cleared</p>
                <p className="text-[11px] text-slate-500">
                  You have no pending tasks. Click below to add an actionable item.
                </p>
                <Link
                  to="/tasks"
                  className="inline-block mt-2 px-3 py-1 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 hover:text-white transition"
                >
                  Create Task
                </Link>
              </div>
            ) : (
              <div className="space-y-2">
                {tasksData.items.map((task) => (
                  <div
                    key={task.id}
                    className="flex items-center justify-between p-3 rounded-xl bg-slate-900/60 hover:bg-slate-900 border border-slate-800/80 transition"
                  >
                    <div className="flex items-center space-x-3 min-w-0">
                      <button
                        onClick={() => handleToggleTask(task)}
                        className={`w-4 h-4 rounded border flex items-center justify-center transition flex-shrink-0 ${
                          task.status === 'completed'
                            ? 'bg-emerald-600 border-emerald-500 text-white'
                            : 'border-slate-700 hover:border-slate-500'
                        }`}
                      >
                        {task.status === 'completed' && <CheckCircle2 className="w-3.5 h-3.5" />}
                      </button>
                      <div className="min-w-0">
                        <span
                          className={`text-xs block truncate ${
                            task.status === 'completed' ? 'line-through text-slate-500' : 'text-slate-200'
                          }`}
                        >
                          {task.title}
                        </span>
                        {task.due_date && (
                          <span className="text-[10px] text-slate-500 flex items-center space-x-1 mt-0.5">
                            <Clock className="w-3 h-3" />
                            <span>Due {task.due_date}</span>
                          </span>
                        )}
                      </div>
                    </div>

                    <span
                      className={`text-[9px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wider flex-shrink-0 ${
                        task.priority === 'urgent'
                          ? 'bg-rose-950/60 text-rose-300 border-rose-800/40'
                          : task.priority === 'high'
                          ? 'bg-amber-950/60 text-amber-300 border-amber-800/40'
                          : 'bg-slate-800 text-slate-400 border-slate-700'
                      }`}
                    >
                      {task.priority}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Active Workspaces / Projects */}
          <div className="rounded-2xl bg-slate-900/40 border border-slate-800 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <FolderKanban className="w-4 h-4 text-emerald-400" />
                <h2 className="text-sm font-semibold text-slate-100">Active Projects</h2>
              </div>
              <Link
                to="/projects"
                className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center space-x-1 transition"
              >
                <span>View All Projects</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isLoadingProjects ? (
              <div className="p-4 text-center text-xs text-slate-500">Loading projects...</div>
            ) : !user ? (
              <div className="p-5 text-center rounded-xl bg-slate-950/50 border border-slate-800/60 space-y-2">
                <FolderKanban className="w-6 h-6 text-emerald-400 mx-auto" />
                <p className="text-xs text-slate-300 font-medium">Guest Mode</p>
                <p className="text-[11px] text-slate-500">
                  Sign in to view your multi-step project workspaces and completion progress.
                </p>
              </div>
            ) : projectsError ? (
              <div className="p-4 text-center rounded-xl bg-slate-900/40 border border-slate-800 text-xs text-slate-400">
                Projects temporarily unavailable.
              </div>
            ) : !projectsData?.items.length ? (
              <div className="p-6 text-center rounded-xl bg-slate-950/50 border border-slate-800/60 space-y-2">
                <FolderKanban className="w-6 h-6 text-slate-600 mx-auto" />
                <p className="text-xs text-slate-400">No active projects</p>
                <p className="text-[11px] text-slate-500">
                  Organize ongoing initiatives and multi-step efforts into structured projects.
                </p>
                <Link
                  to="/projects"
                  className="inline-block mt-2 px-3 py-1 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 hover:text-white transition"
                >
                  Create Project
                </Link>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {projectsData.items.map((project) => (
                  <Link
                    key={project.id}
                    to="/projects"
                    search={{ project_id: project.id }}
                    className="p-3.5 rounded-xl bg-slate-900/60 hover:bg-slate-900 border border-slate-800/80 transition flex flex-col justify-between space-y-3 group"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span
                          className="w-2.5 h-2.5 rounded-full"
                          style={{ backgroundColor: project.color || '#6366f1' }}
                        />
                        <span className="text-[10px] font-mono text-slate-400">
                          {project.progress_percentage}%
                        </span>
                      </div>
                      <h3 className="text-xs font-semibold text-slate-200 group-hover:text-white truncate">
                        {project.name}
                      </h3>
                      {project.description && (
                        <p className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">
                          {project.description}
                        </p>
                      )}
                    </div>

                    {/* Progress Bar */}
                    <div className="w-full bg-slate-800 rounded-full h-1 overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full transition-all duration-300"
                        style={{ width: `${project.progress_percentage}%` }}
                      />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column (1 span): Strategic Goals & Recent Intelligence */}
        <div className="space-y-6">
          {/* Strategic Goals Card */}
          <div className="rounded-2xl bg-slate-900/40 border border-slate-800 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Target className="w-4 h-4 text-purple-400" />
                <h2 className="text-sm font-semibold text-slate-100">Strategic Goals</h2>
              </div>
              <Link
                to="/goals"
                className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center space-x-1 transition"
              >
                <span>View Goals</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isLoadingGoals ? (
              <div className="p-4 text-center text-xs text-slate-500">Loading goals...</div>
            ) : !user ? (
              <div className="p-5 text-center rounded-xl bg-slate-950/50 border border-slate-800/60 space-y-2">
                <Target className="w-5 h-5 text-purple-400 mx-auto" />
                <p className="text-xs text-slate-300 font-medium">Guest Mode</p>
                <p className="text-[11px] text-slate-500">
                  Sign in to track strategic objectives, measurable milestones, and deadlines.
                </p>
              </div>
            ) : goalsError ? (
              <div className="p-4 text-center rounded-xl bg-slate-900/40 border border-slate-800 text-xs text-slate-400">
                Goals temporarily unavailable.
              </div>
            ) : !goalsData?.items.length ? (
              <div className="p-5 text-center rounded-xl bg-slate-950/50 border border-slate-800/60 space-y-2">
                <Target className="w-5 h-5 text-slate-600 mx-auto" />
                <p className="text-xs text-slate-400">No active goals</p>
                <Link
                  to="/goals"
                  className="inline-block mt-1 px-3 py-1 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 hover:text-white transition"
                >
                  Set Strategic Goal
                </Link>
              </div>
            ) : (
              <div className="space-y-3">
                {goalsData.items.map((goal) => (
                  <div key={goal.id} className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-slate-200 truncate pr-2">{goal.title}</span>
                      <span className="font-mono text-purple-400 text-[11px] flex-shrink-0">
                        {goal.progress_percentage ?? 0}%
                      </span>
                    </div>
                    <div className="w-full bg-slate-800 rounded-full h-1 overflow-hidden">
                      <div
                        className="h-full bg-purple-500 rounded-full"
                        style={{ width: `${goal.progress_percentage ?? 0}%` }}
                      />
                    </div>
                    {goal.target_date && (
                      <span className="text-[10px] text-slate-500 block">Target: {goal.target_date}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Conversations */}
          <div className="rounded-2xl bg-slate-900/40 border border-slate-800 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <MessageSquare className="w-4 h-4 text-sky-400" />
                <h2 className="text-sm font-semibold text-slate-100">Recent Conversations</h2>
              </div>
              <Link
                to="/chat"
                className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center space-x-1 transition"
              >
                <span>New Dialogue</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {isLoadingConversations ? (
              <div className="p-4 text-center text-xs text-slate-500">Loading dialogue...</div>
            ) : !user ? (
              <div className="p-5 text-center rounded-xl bg-slate-950/50 border border-slate-800/60 space-y-2">
                <MessageSquare className="w-5 h-5 text-sky-400 mx-auto" />
                <p className="text-xs text-slate-300 font-medium">Guest Mode</p>
                <p className="text-[11px] text-slate-500">
                  Sign in to access your persistent conversations across devices.
                </p>
                <Link
                  to="/chat"
                  className="inline-block mt-1 px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs text-white transition"
                >
                  Start Dialogue
                </Link>
              </div>
            ) : conversationsError ? (
              <div className="p-4 text-center rounded-xl bg-slate-900/40 border border-slate-800 text-xs text-slate-400">
                Dialogue history temporarily unavailable.
              </div>
            ) : !conversations.length ? (
              <div className="p-5 text-center rounded-xl bg-slate-950/50 border border-slate-800/60 space-y-2">
                <MessageSquare className="w-5 h-5 text-slate-600 mx-auto" />
                <p className="text-xs text-slate-400">No active conversations</p>
                <Link
                  to="/chat"
                  className="inline-block mt-1 px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs text-white transition"
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
                    className="p-2.5 rounded-xl hover:bg-slate-900/80 transition flex items-center justify-between group"
                  >
                    <div className="min-w-0 pr-2">
                      <span className="text-xs text-slate-300 group-hover:text-white block truncate">
                        {conv.title || 'Untitled Dialogue'}
                      </span>
                      <span className="text-[10px] text-slate-500">
                        {new Date(conv.updated_at).toLocaleDateString()}
                      </span>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-slate-300 flex-shrink-0" />
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

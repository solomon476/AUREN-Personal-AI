/**
 * Productivity Overview and Dashboard View for AUREN Phase 3C.4 Productivity Core.
 * Aggregates live KPI metrics from persisted tasks, projects, and goals.
 * Elevated with AUREN Obsidian & Champagne Design System.
 */

import React from 'react';
import {
  LayoutDashboard,
  CheckSquare,
  FolderKanban,
  Target,
  AlertTriangle,
  Clock,
  CheckCircle2,
  Calendar,
  ArrowRight,
  TrendingUp,
} from 'lucide-react';
import { Link } from '@tanstack/react-router';
import { useProductivityDashboard } from '../../hooks/useProductivity';
import { useAuth } from '../../context/AuthContext';

export const ProductivityDashboardView: React.FC = () => {
  const { user } = useAuth();
  const { data: dashboard, isLoading, error } = useProductivityDashboard(user?.id);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-950 text-slate-500 text-sm">
        <Clock className="w-5 h-5 animate-spin mr-2 text-indigo-400" />
        Loading productivity overview...
      </div>
    );
  }

  if (error || !dashboard) {
    return (
      <div className="p-6 bg-slate-950 text-slate-100 flex-1">
        <div className="p-6 bg-slate-900/60 border border-slate-800 rounded-2xl text-center space-y-2 max-w-lg mx-auto mt-12 shadow-subtle-elevation">
          <AlertTriangle className="w-6 h-6 text-indigo-400 mx-auto" />
          <div className="text-sm font-semibold text-slate-200">
            {!user ? 'Sign In to View Productivity Metrics' : 'Productivity Metrics Unavailable'}
          </div>
          <p className="text-xs text-slate-400 max-w-sm mx-auto leading-relaxed">
            {!user
              ? 'Sign in or register an account to track execution velocity, active task breakdowns, and goal progress.'
              : 'Unable to retrieve your productivity overview. Please verify your connection or try again later.'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-[#07080c] overflow-y-auto text-slate-100 p-6 space-y-6 scrollbar-thin">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center space-x-3.5">
            <div className="p-2.5 rounded-xl bg-champagne-500/10 border border-champagne-500/20 text-champagne-400 shadow-sm">
              <LayoutDashboard className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-xl font-bold tracking-tight text-white">Productivity Overview</h1>
                <span className="hidden sm:inline-flex text-[10px] font-mono px-2 py-0.5 rounded bg-graphite-800/90 text-champagne-300 border border-champagne-500/20">
                  Telemetry
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Real-time status of your active commitments, upcoming deadlines, and strategic execution.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* KPI Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3.5">
        <div className="p-4.5 rounded-2xl bg-[#0e1017]/70 border border-white/[0.06] shadow-subtle-elevation">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span>Active Tasks</span>
            <CheckSquare className="w-4 h-4 text-champagne-400" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">{dashboard.active_tasks_count}</div>
          <span className="text-[10px] text-slate-500">To do &amp; in progress</span>
        </div>

        <div className={`p-4.5 rounded-2xl border shadow-subtle-elevation ${dashboard.overdue_tasks_count > 0
          ? 'bg-rose-950/20 border-rose-900/50 text-rose-300'
          : 'bg-[#0e1017]/70 border-white/[0.06]'
          }`}>
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className={dashboard.overdue_tasks_count > 0 ? 'text-rose-400 font-medium' : 'text-slate-400'}>
              Overdue Tasks
            </span>
            <AlertTriangle className={`w-4 h-4 ${dashboard.overdue_tasks_count > 0 ? 'text-rose-400' : 'text-slate-500'}`} />
          </div>
          <div className="text-2xl font-bold font-mono">{dashboard.overdue_tasks_count}</div>
          <span className="text-[10px] opacity-75">Needs immediate review</span>
        </div>

        <div className="p-4.5 rounded-2xl bg-[#0e1017]/70 border border-white/[0.06] shadow-subtle-elevation">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span>Completed</span>
            <CheckCircle2 className="w-4 h-4 text-champagne-400" />
          </div>
          <div className="text-2xl font-bold text-champagne-200/90 font-mono">{dashboard.completed_tasks_count}</div>
          <span className="text-[10px] text-slate-500">All-time finished</span>
        </div>

        <div className="p-4.5 rounded-2xl bg-[#0e1017]/70 border border-white/[0.06] shadow-subtle-elevation">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span>Active Projects</span>
            <FolderKanban className="w-4 h-4 text-champagne-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 font-mono">{dashboard.active_projects_count}</div>
          <span className="text-[10px] text-slate-500">Workspaces in flight</span>
        </div>

        <div className="p-4.5 rounded-2xl bg-[#0e1017]/70 border border-white/[0.06] col-span-2 md:col-span-1 shadow-subtle-elevation">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span>Active Goals</span>
            <Target className="w-4 h-4 text-champagne-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 font-mono">{dashboard.active_goals_count}</div>
          <span className="text-[10px] text-slate-500">Strategic objectives</span>
        </div>
      </div>

      {/* Main Grid: Overdue & Upcoming */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Overdue / High Priority Tasks */}
        <div className="p-5 rounded-2xl bg-[#0e1017]/70 border border-white/[0.06] flex flex-col shadow-subtle-elevation">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center">
              <AlertTriangle className="w-4 h-4 mr-2 text-rose-400" />
              Overdue Commitments
            </h3>
            <Link to="/tasks" className="text-xs text-champagne-400 hover:text-champagne-300 flex items-center">
              View all <ArrowRight className="w-3 h-3 ml-1" />
            </Link>
          </div>

          {dashboard.overdue_tasks.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center p-6 text-center text-slate-500">
              <CheckCircle2 className="w-8 h-8 text-emerald-500/40 mb-2" />
              <p className="text-xs">No overdue tasks. All deadlines are on track!</p>
            </div>
          ) : (
            <div className="space-y-2">
              {dashboard.overdue_tasks.map((task) => (
                <div
                  key={task.id}
                  className="p-3 rounded-xl bg-rose-950/20 border border-rose-900/40 flex items-center justify-between text-xs"
                >
                  <div className="truncate mr-3">
                    <div className="font-medium text-rose-200 truncate">{task.title}</div>
                    <div className="text-[10px] text-rose-400 mt-0.5 flex items-center">
                      <Calendar className="w-3 h-3 mr-1" />
                      Due {new Date(task.due_date!).toLocaleDateString()}
                      {task.project_name && ` · ${task.project_name}`}
                    </div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-950 text-rose-300 border border-rose-800 flex-shrink-0">
                    {task.priority}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Upcoming Tasks */}
        <div className="p-5 rounded-2xl bg-[#0e111a]/80 border border-white/[0.07] flex flex-col shadow-subtle-elevation">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center">
              <Calendar className="w-4 h-4 mr-2 text-champagne-400" />
              Upcoming &amp; Priority Tasks
            </h3>
            <Link to="/tasks" className="text-xs text-champagne-300 hover:text-champagne-200 flex items-center">
              View all <ArrowRight className="w-3 h-3 ml-1" />
            </Link>
          </div>

          {dashboard.upcoming_tasks.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center p-6 text-center text-slate-500">
              <CheckSquare className="w-8 h-8 text-slate-700 mb-2" />
              <p className="text-xs">No upcoming tasks scheduled.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {dashboard.upcoming_tasks.map((task) => (
                <div
                  key={task.id}
                  className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-center justify-between text-xs"
                >
                  <div className="truncate mr-3">
                    <div className="font-medium text-slate-200 truncate">{task.title}</div>
                    <div className="text-[10px] text-slate-400 mt-0.5 flex items-center">
                      {task.due_date ? (
                        <>
                          <Calendar className="w-3 h-3 mr-1 text-slate-500" />
                          Due {new Date(task.due_date).toLocaleDateString()}
                        </>
                      ) : (
                        'No deadline set'
                      )}
                      {task.project_name && ` · ${task.project_name}`}
                    </div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-[#07080c] text-champagne-300 border border-white/[0.08] flex-shrink-0">
                    {task.priority}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Projects and Goals In Progress */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active Projects */}
        <div className="p-5 rounded-2xl bg-[#0e111a]/80 border border-white/[0.07] shadow-subtle-elevation">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center">
              <FolderKanban className="w-4 h-4 mr-2 text-emerald-400" />
              Active Projects
            </h3>
            <Link to="/projects" className="text-xs text-champagne-300 hover:text-champagne-200 flex items-center">
              View all <ArrowRight className="w-3 h-3 ml-1" />
            </Link>
          </div>

          {dashboard.active_projects.length === 0 ? (
            <div className="p-6 text-center text-slate-500 text-xs">No active projects found.</div>
          ) : (
            <div className="space-y-3">
              {dashboard.active_projects.map((p) => (
                <div key={p.id} className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] text-xs">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-medium text-slate-200">{p.name}</span>
                    <span className="font-semibold text-emerald-400 font-mono">{p.progress_percentage}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-[#07080c] rounded-full overflow-hidden mb-1.5">
                    <div
                      className="h-full rounded-full bg-emerald-500 transition-all duration-300"
                      style={{
                        width: `${p.progress_percentage}%`,
                      }}
                    />
                  </div>
                  <div className="text-[10px] text-slate-400">
                    {p.completed_task_count} of {p.task_count} tasks completed
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Strategic Goals */}
        <div className="p-5 rounded-2xl bg-[#0e111a]/80 border border-white/[0.07] shadow-subtle-elevation">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center">
              <Target className="w-4 h-4 mr-2 text-champagne-400" />
              Goals In Progress
            </h3>
            <Link to="/goals" className="text-xs text-champagne-300 hover:text-champagne-200 flex items-center">
              View all <ArrowRight className="w-3 h-3 ml-1" />
            </Link>
          </div>

          {dashboard.active_goals.length === 0 ? (
            <div className="p-6 text-center text-slate-500 text-xs">No active goals found.</div>
          ) : (
            <div className="space-y-3">
              {dashboard.active_goals.map((g) => (
                <div key={g.id} className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800/80 text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-slate-200">{g.title}</span>
                    {g.progress_percentage != null && (
                      <span className="font-semibold text-purple-300 font-mono">{g.progress_percentage}%</span>
                    )}
                  </div>
                  {g.target_value ? (
                    <div className="text-[10px] text-slate-400 flex items-center">
                      <TrendingUp className="w-3 h-3 mr-1 text-purple-400" />
                      {g.current_value || 0} / {g.target_value} {g.unit || ''}
                    </div>
                  ) : (
                    <div className="text-[10px] text-slate-400">
                      {g.project_count} projects · {g.task_count} tasks linked
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

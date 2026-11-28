/**
 * Home Weekly Analytics & Momentum Scorecard.
 * Renders a lightweight, responsive SVG 7-day completion/due bar graph and
 * overall execution ring using already-fetched ProductivityDashboard data.
 */

import React, { useMemo, useState } from 'react';
import { ArrowRight, BarChart3, CheckCircle2, Clock, AlertTriangle } from 'lucide-react';
import { Link } from '@tanstack/react-router';
import { Goal, ProductivityDashboard, Project, Task } from '../../api/productivity';

interface HomeAnalyticsSectionProps {
  dashboard?: ProductivityDashboard;
  tasks?: Task[];
  projects?: Project[];
  goals?: Goal[];
  isAuthenticated: boolean;
}

function toLocalDayKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function normalizeDateKey(isoOrDate?: string | null): string | null {
  if (!isoOrDate) return null;
  const s = String(isoOrDate).trim();
  if (!s) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const parsed = new Date(s);
  if (Number.isNaN(parsed.getTime())) return s.slice(0, 10);
  return toLocalDayKey(parsed);
}

export const HomeAnalyticsSection: React.FC<HomeAnalyticsSectionProps> = ({
  dashboard,
  tasks = [],
  projects = [],
  goals = [],
  isAuthenticated,
}) => {
  const [selectedIdx, setSelectedIdx] = useState<number>(6); // Default to Today (last bar)

  const analytics = useMemo(() => {
    const activeCount = Number(dashboard?.active_tasks_count ?? 0);
    const completedCount = Number(dashboard?.completed_tasks_count ?? 0);
    const overdueCount = Number(dashboard?.overdue_tasks_count ?? 0);
    const totalTasks = activeCount + completedCount;
    const completionRate = totalTasks > 0 ? Math.round((completedCount / totalTasks) * 100) : 0;

    const projectItems = dashboard?.active_projects?.length ? dashboard.active_projects : projects;
    const avgProjectProgress =
      projectItems.length > 0
        ? Math.round(projectItems.reduce((acc, p) => acc + Number(p.progress_percentage ?? 0), 0) / projectItems.length)
        : 0;

    const goalItems = dashboard?.active_goals?.length ? dashboard.active_goals : goals;
    const avgGoalProgress =
      goalItems.length > 0
        ? Math.round(goalItems.reduce((acc, g) => acc + Number(g.progress_percentage ?? 0), 0) / goalItems.length)
        : 0;

    // Combine deduplicated tasks from dashboard lists + active tasks prop
    const taskMap = new Map<string, Task>();
    for (const src of [
      ...(dashboard?.recently_completed_tasks ?? []),
      ...(dashboard?.upcoming_tasks ?? []),
      ...(dashboard?.overdue_tasks ?? []),
      ...tasks,
    ]) {
      if (src?.id) taskMap.set(src.id, src);
    }

    const now = new Date();
    const dayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const buckets = [];
    for (let offset = -6; offset <= 0; offset++) {
      const d = new Date(now);
      d.setDate(now.getDate() + offset);
      const key = toLocalDayKey(d);
      buckets.push({
        key,
        shortDay: dayLabels[d.getDay()],
        dayNum: String(d.getDate()).padStart(2, '0'),
        completed: 0,
        scheduled: 0,
        isToday: offset === 0,
      });
    }
    const bucketByKey = new Map(buckets.map((b) => [b.key, b]));

    for (const t of taskMap.values()) {
      if (t.status === 'completed') {
        const doneKey = normalizeDateKey(t.completed_at || t.updated_at);
        if (doneKey && bucketByKey.has(doneKey)) {
          bucketByKey.get(doneKey)!.completed += 1;
        }
      } else if (t.status !== 'cancelled') {
        const dueKey = normalizeDateKey(t.due_date);
        if (dueKey && bucketByKey.has(dueKey)) {
          bucketByKey.get(dueKey)!.scheduled += 1;
        }
      }
    }

    const maxBarValue = Math.max(
      1,
      ...buckets.map((b) => Math.max(b.completed, b.scheduled))
    );
    const hasActivityBars = buckets.some((b) => b.completed > 0 || b.scheduled > 0);

    return {
      activeCount,
      completedCount,
      overdueCount,
      totalTasks,
      completionRate,
      avgProjectProgress,
      avgGoalProgress,
      buckets,
      maxBarValue,
      hasActivityBars,
    };
  }, [dashboard, goals, projects, tasks]);

  if (!isAuthenticated) {
    return null;
  }

  const selectedDay = analytics.buckets[Math.min(Math.max(selectedIdx, 0), analytics.buckets.length - 1)];
  const ringRadius = 34;
  const ringCircumference = 2 * Math.PI * ringRadius;
  const ringDashOffset = ringCircumference - (analytics.completionRate / 100) * ringCircumference;

  return (
    <section
      aria-label="Productivity & Execution Analytics"
      className="rounded-2xl bg-white border border-slate-200 p-4 sm:p-6 shadow-sm space-y-5"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3.5">
        <div className="flex items-center space-x-2.5">
          <div className="p-2 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-600">
            <BarChart3 className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm sm:text-base font-bold text-slate-900 tracking-tight">
              Execution &amp; Momentum Analytics
            </h2>
            <p className="text-[11px] text-slate-500">
              7-day completion trend, due workload, and overall goal velocity
            </p>
          </div>
        </div>
        <Link
          to="/productivity"
          className="text-[11px] text-emerald-700 hover:text-emerald-800 font-semibold flex items-center space-x-1 transition self-start sm:self-auto"
        >
          <span>Productivity Hub</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 items-stretch">
        {/* Left/Main (2 cols): 7-Day Activity & Momentum Bar Chart */}
        <div className="lg:col-span-2 rounded-xl bg-slate-50/80 border border-slate-200/80 p-4 flex flex-col justify-between space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-bold text-slate-800">7-Day Task Activity</span>
            <div className="flex items-center gap-3 text-[10px] font-medium text-slate-600">
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500 inline-block" />
                Completed
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm bg-slate-400 inline-block" />
                Due / Active
              </span>
            </div>
          </div>

          <div className="w-full">
            <svg
              viewBox="0 0 350 132"
              className="w-full h-36 overflow-visible"
              role="img"
              aria-label="7-day completed and scheduled tasks bar chart"
            >
              {/* Horizontal baseline & guide lines */}
              <line x1="8" y1="22" x2="342" y2="22" stroke="#e2e8f0" strokeDasharray="3 3" strokeWidth="1" />
              <line x1="8" y1="62" x2="342" y2="62" stroke="#e2e8f0" strokeDasharray="3 3" strokeWidth="1" />
              <line x1="8" y1="102" x2="342" y2="102" stroke="#cbd5e1" strokeWidth="1.2" />

              {analytics.buckets.map((bucket, idx) => {
                const groupX = 14 + idx * 48;
                const chartHeight = 76;
                const compHeight =
                  bucket.completed > 0
                    ? Math.max(6, Math.round((bucket.completed / analytics.maxBarValue) * chartHeight))
                    : 3;
                const schedHeight =
                  bucket.scheduled > 0
                    ? Math.max(6, Math.round((bucket.scheduled / analytics.maxBarValue) * chartHeight))
                    : 3;
                const isSelected = idx === selectedIdx;

                return (
                  <g
                    key={bucket.key}
                    onClick={() => setSelectedIdx(idx)}
                    className="cursor-pointer"
                  >
                    {isSelected && (
                      <rect
                        x={groupX - 4}
                        y={12}
                        width="38"
                        height="114"
                        rx="8"
                        fill="#ecfdf5"
                        stroke="#a7f3d0"
                        strokeWidth="1"
                      />
                    )}
                    {/* Completed bar */}
                    <rect
                      x={groupX + 2}
                      y={102 - compHeight}
                      width="11"
                      height={compHeight}
                      rx="3"
                      fill={bucket.completed > 0 ? '#10b981' : '#cbd5e1'}
                    />
                    {/* Scheduled/Due bar */}
                    <rect
                      x={groupX + 16}
                      y={102 - schedHeight}
                      width="11"
                      height={schedHeight}
                      rx="3"
                      fill={bucket.scheduled > 0 ? '#64748b' : '#e2e8f0'}
                    />
                    <text
                      x={groupX + 14}
                      y="116"
                      textAnchor="middle"
                      fontSize="9"
                      fontWeight={bucket.isToday ? '700' : '600'}
                      fill={bucket.isToday ? '#047857' : '#64748b'}
                    >
                      {bucket.isToday ? 'Today' : bucket.shortDay}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-200/70 text-[11px]">
            {analytics.hasActivityBars ? (
              <span className="text-slate-700 font-medium">
                <strong className="text-slate-900">
                  {selectedDay.isToday ? 'Today' : `${selectedDay.shortDay} ${selectedDay.dayNum}`}:
                </strong>{' '}
                {selectedDay.completed} completed · {selectedDay.scheduled} scheduled due
              </span>
            ) : (
              <span className="text-slate-500">
                Complete or schedule dated tasks to plot your 7-day execution curve.
              </span>
            )}
            <Link to="/tasks" className="text-emerald-700 hover:text-emerald-800 font-semibold">
              Open Timetable →
            </Link>
          </div>
        </div>

        {/* Right: Completion Donut Ring & Key Health Counters */}
        <div className="rounded-xl bg-slate-50/80 border border-slate-200/80 p-4 flex flex-col justify-between space-y-4">
          <div className="flex items-center gap-4">
            <div className="relative w-20 h-20 flex-shrink-0">
              <svg viewBox="0 0 84 84" className="w-20 h-20 -rotate-90" aria-hidden="true">
                <circle
                  cx="42"
                  cy="42"
                  r={ringRadius}
                  fill="none"
                  stroke="#e2e8f0"
                  strokeWidth="8"
                />
                <circle
                  cx="42"
                  cy="42"
                  r={ringRadius}
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={ringCircumference}
                  strokeDashoffset={ringDashOffset}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-base font-extrabold font-mono text-slate-900">
                  {analytics.completionRate}%
                </span>
                <span className="text-[9px] uppercase tracking-wider font-semibold text-slate-500">
                  Done
                </span>
              </div>
            </div>

            <div className="min-w-0 space-y-1">
              <span className="text-xs font-bold text-slate-900 block">Overall Completion</span>
              <p className="text-[11px] text-slate-500 leading-snug">
                {analytics.completedCount} completed out of {analytics.totalTasks} tracked tasks.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-2.5 rounded-lg bg-white border border-slate-200">
              <span className="flex items-center gap-1 text-[10px] text-slate-500 font-semibold uppercase">
                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                Completed
              </span>
              <span className="text-sm font-bold font-mono text-slate-900 mt-0.5 block">
                {analytics.completedCount}
              </span>
            </div>

            <div className="p-2.5 rounded-lg bg-white border border-slate-200">
              <span className="flex items-center gap-1 text-[10px] text-slate-500 font-semibold uppercase">
                {analytics.overdueCount > 0 ? (
                  <AlertTriangle className="w-3 h-3 text-amber-600" />
                ) : (
                  <Clock className="w-3 h-3 text-slate-500" />
                )}
                Overdue
              </span>
              <span
                className={`text-sm font-bold font-mono mt-0.5 block ${
                  analytics.overdueCount > 0 ? 'text-amber-700' : 'text-slate-900'
                }`}
              >
                {analytics.overdueCount}
              </span>
            </div>

            <div className="p-2.5 rounded-lg bg-white border border-slate-200 col-span-2 flex items-center justify-between">
              <span className="text-[10px] text-slate-500 font-semibold uppercase">
                Avg Project / Goal Progress
              </span>
              <span className="text-xs font-bold font-mono text-emerald-700">
                {analytics.avgProjectProgress}% · {analytics.avgGoalProgress}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};


/**
 * Strategic Goals & Milestones View for AUREN Phase 3C.4 Productivity Core.
 * Tracks high-level strategic objectives, target dates, and measurable progress.
 */

import React, { useState } from 'react';
import {
  Target,
  Plus,
  Search,
  Calendar,
  Clock,
  AlertCircle,
  Edit2,
  Trash2,
  FolderKanban,
  TrendingUp,
  ArrowRight,
} from 'lucide-react';
import { Link } from '@tanstack/react-router';
import { Goal, GoalCreateInput, GoalUpdateInput } from '../../api/productivity';
import {
  useCreateGoal,
  useDeleteGoal,
  useGoal,
  useGoals,
  useUpdateGoal,
} from '../../hooks/useProductivity';
import { useAuth } from '../../context/AuthContext';
import { GoalModal } from '../../components/productivity/GoalModal';

export const GoalsView: React.FC = () => {
  const { user } = useAuth();
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [page, setPage] = useState<number>(1);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<Goal | null>(null);
  const [activeGoalId, setActiveGoalId] = useState<string | null>(null);

  const { data: goalsData, isLoading, error } = useGoals({
    status: selectedStatus || undefined,
    query: searchQuery || undefined,
    page,
    page_size: 20,
  }, user?.id);

  const { data: activeGoalDetail } = useGoal(activeGoalId || undefined, user?.id);

  const createGoalMutation = useCreateGoal(user?.id);
  const updateGoalMutation = useUpdateGoal(user?.id);
  const deleteGoalMutation = useDeleteGoal(user?.id);

  const handleOpenCreate = () => {
    setEditingGoal(null);
    setIsModalOpen(true);
  };

  const handleOpenEdit = (e: React.MouseEvent, goal: Goal) => {
    e.stopPropagation();
    setEditingGoal(goal);
    setIsModalOpen(true);
  };

  const handleDelete = async (e: React.MouseEvent, goalId: string) => {
    e.stopPropagation();
    if (window.confirm('Delete this goal? (Linked projects and tasks will be unlinked and preserved)')) {
      await deleteGoalMutation.mutateAsync(goalId);
      if (activeGoalId === goalId) {
        setActiveGoalId(null);
      }
    }
  };

  const handleModalSubmit = async (data: GoalCreateInput | GoalUpdateInput) => {
    if (editingGoal) {
      await updateGoalMutation.mutateAsync({ goalId: editingGoal.id, input: data });
    } else {
      await createGoalMutation.mutateAsync(data as GoalCreateInput);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden text-slate-100">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between p-6 border-b border-slate-800 bg-slate-900/40 gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-400">
              <Target className="w-5 h-5" />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-100">Strategic Goals</h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Define long-term objectives, milestones, and verifiable metrics.
          </p>
        </div>

        <button
          onClick={handleOpenCreate}
          className="flex items-center justify-center space-x-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors shadow-lg shadow-indigo-600/20 self-start md:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>New Goal</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-6 pb-2 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search goals..."
            className="w-full pl-9 pr-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div>
          <select
            value={selectedStatus}
            onChange={(e) => {
              setSelectedStatus(e.target.value);
              setPage(1);
            }}
            className="w-full px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
          >
            <option value="">All Statuses</option>
            <option value="in_progress">In Progress</option>
            <option value="not_started">Not Started</option>
            <option value="achieved">Achieved</option>
            <option value="paused">Paused</option>
            <option value="abandoned">Abandoned</option>
          </select>
        </div>
      </div>

      {/* Goals Content */}
      <div className="flex-1 flex overflow-hidden p-6 gap-6">
        <div className={`flex-1 overflow-y-auto space-y-3 ${activeGoalId ? 'hidden lg:block' : ''}`}>
          {isLoading ? (
            <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
              <Clock className="w-5 h-5 animate-spin mr-2" />
              Loading goals...
            </div>
          ) : error ? (
            <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl text-center space-y-2">
              <AlertCircle className="w-5 h-5 text-indigo-400 mx-auto" />
              <div className="text-sm font-semibold text-slate-200">
                {!user ? 'Sign In to Access Goals' : 'Failed to load goals'}
              </div>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                {!user
                  ? 'Sign in or register to track long-term milestones, objectives, and execution progress.'
                  : 'Could not connect to the goals service. Please verify network connectivity and try again.'}
              </p>
            </div>
          ) : goalsData?.items.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 border border-dashed border-slate-800 rounded-xl p-8 text-center bg-slate-900/20">
              <Target className="w-12 h-12 text-slate-600 mb-3" />
              <h3 className="text-sm font-semibold text-slate-300">No goals set</h3>
              <p className="text-xs text-slate-500 max-w-sm mt-1 mb-4">
                Establish high-level personal or professional goals to guide your daily tasks.
              </p>
              <button
                onClick={handleOpenCreate}
                className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg transition-colors border border-slate-700"
              >
                Create Goal
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {goalsData?.items.map((goal) => {
                const isSelected = activeGoalId === goal.id;

                return (
                  <div
                    key={goal.id}
                    onClick={() => setActiveGoalId(isSelected ? null : goal.id)}
                    className={`group relative p-4 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${
                      isSelected
                        ? 'bg-slate-900 border-indigo-500/80 ring-1 ring-indigo-500/30'
                        : 'bg-slate-900/60 border-slate-800/80 hover:border-slate-700 hover:bg-slate-900'
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider border ${
                            goal.status === 'achieved'
                              ? 'bg-emerald-950/80 text-emerald-300 border-emerald-800/50'
                              : goal.status === 'in_progress'
                              ? 'bg-purple-950/80 text-purple-300 border-purple-800/50'
                              : 'bg-slate-800 text-slate-300 border-slate-700'
                          }`}
                        >
                          {goal.status.replace('_', ' ')}
                        </span>

                        <div className="flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={(e) => handleOpenEdit(e, goal)}
                            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                            title="Edit Goal"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={(e) => handleDelete(e, goal.id)}
                            className="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-slate-800"
                            title="Delete Goal"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>

                      <h3 className="text-base font-semibold text-slate-100 group-hover:text-indigo-300 transition-colors">
                        {goal.title}
                      </h3>

                      {goal.description && (
                        <p className="text-xs text-slate-400 mt-1 line-clamp-2">{goal.description}</p>
                      )}
                    </div>

                    <div className="mt-4 pt-3 border-t border-slate-800/60">
                      {/* Metric or Dates */}
                      <div className="flex items-center justify-between text-xs mb-1.5">
                        <span className="text-slate-400 flex items-center">
                          {goal.target_value ? (
                            <>
                              <TrendingUp className="w-3.5 h-3.5 mr-1 text-purple-400" />
                              {goal.current_value || 0} / {goal.target_value} {goal.unit || ''}
                            </>
                          ) : (
                            <>
                              <FolderKanban className="w-3.5 h-3.5 mr-1 text-slate-500" />
                              {goal.project_count} projects · {goal.task_count} tasks
                            </>
                          )}
                        </span>

                        {goal.progress_percentage != null && (
                          <span className="font-semibold text-slate-200">
                            {goal.progress_percentage}%
                          </span>
                        )}
                      </div>

                      {goal.progress_percentage != null && (
                        <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-purple-500 rounded-full transition-all duration-300"
                            style={{ width: `${goal.progress_percentage}%` }}
                          />
                        </div>
                      )}

                      {goal.target_date && (
                        <div className="mt-2 text-[11px] text-slate-400 flex items-center">
                          <Calendar className="w-3 h-3 mr-1" />
                          Target: {new Date(goal.target_date).toLocaleDateString()}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected Goal Detail Drawer */}
        {activeGoalId && activeGoalDetail && (
          <div className="w-full lg:w-96 flex flex-col bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden p-5 animate-in slide-in-from-right duration-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="font-semibold text-slate-100">{activeGoalDetail.title}</h3>
              <button
                onClick={() => setActiveGoalId(null)}
                className="text-xs text-slate-400 hover:text-slate-200"
              >
                Close
              </button>
            </div>

            <div className="py-3 text-xs text-slate-400 border-b border-slate-800">
              {activeGoalDetail.description || 'No description provided.'}
            </div>

            <div className="flex-1 overflow-y-auto py-3 space-y-4">
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  Linked Projects ({activeGoalDetail.projects.length})
                </h4>
                {activeGoalDetail.projects.length === 0 ? (
                  <div className="text-xs text-slate-500">No linked projects.</div>
                ) : (
                  activeGoalDetail.projects.map((proj) => (
                    <Link
                      key={proj.id}
                      to="/projects"
                      search={{ project_id: proj.id }}
                      className="p-2.5 rounded-lg bg-slate-950/60 hover:bg-slate-900 border border-slate-800/80 text-xs mb-1.5 flex items-center justify-between group transition"
                    >
                      <div>
                        <div className="font-medium text-slate-200 group-hover:text-indigo-400 transition">{proj.name}</div>
                        <div className="text-[10px] text-slate-400 mt-0.5">
                          {proj.progress_percentage}% completed
                        </div>
                      </div>
                      <ArrowRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-indigo-400 transition" />
                    </Link>
                  ))
                )}
              </div>

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  Linked Tasks ({activeGoalDetail.tasks.length})
                </h4>
                {activeGoalDetail.tasks.length === 0 ? (
                  <div className="text-xs text-slate-500">No directly linked tasks.</div>
                ) : (
                  activeGoalDetail.tasks.map((task) => (
                    <Link
                      key={task.id}
                      to="/tasks"
                      search={{ goal_id: activeGoalDetail.id }}
                      className="p-2 rounded bg-slate-950/60 hover:bg-slate-900 border border-slate-800/80 text-xs flex items-center justify-between mb-1 group transition"
                    >
                      <span className="truncate text-slate-300 group-hover:text-white transition">{task.title}</span>
                      <span className="text-[10px] text-slate-400 uppercase">{task.status}</span>
                    </Link>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      <GoalModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleModalSubmit}
        initialGoal={editingGoal}
      />
    </div>
  );
};

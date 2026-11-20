/**
 * Strategic Goals & Milestones View for AUREN Phase 3C.4 Productivity Core.
 * Tracks high-level strategic objectives, target dates, and measurable progress.
 * Elevated with AUREN Obsidian & Champagne Design System.
 */

import React, { useState } from 'react';
import {
  Target,
  Plus,
  Search,
  Clock,
  AlertCircle,
  Edit2,
  Trash2,
} from 'lucide-react';
import { Goal, GoalCreateInput, GoalUpdateInput } from '../../api/productivity';
import {
  useCreateGoal,
  useDeleteGoal,
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

  const { data: goalsData, isLoading, error } = useGoals({
    status: selectedStatus || undefined,
    query: searchQuery || undefined,
    page,
    page_size: 20,
  }, user?.id);

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
    <div className="flex-1 flex flex-col h-full bg-[#07080c] overflow-hidden text-slate-100">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between p-4 sm:p-6 border-b border-white/[0.06] bg-[#0e1017]/70 backdrop-blur-md gap-3 sm:gap-4">
        <div>
          <div className="flex items-center space-x-3.5">
            <div className="p-2.5 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400 shadow-sm">
              <Target className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-xl font-bold tracking-tight text-white">Strategic Goals</h1>
                <span className="hidden sm:inline-flex text-[10px] font-mono px-2 py-0.5 rounded bg-graphite-800/90 text-champagne-300 border border-champagne-500/20">
                  Target Vector
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Define long-term objectives, milestones, and verifiable metrics.
              </p>
            </div>
          </div>
        </div>

        <button
          onClick={handleOpenCreate}
          className="flex items-center justify-center space-x-2 px-4 py-2.5 min-h-[44px] bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white text-xs font-semibold rounded-xl transition-all shadow-md shadow-indigo-600/20 self-start md:self-auto touch-target cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          <span>New Goal</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-4 sm:p-6 pb-2 grid grid-cols-1 md:grid-cols-2 gap-2.5 sm:gap-3 border-b border-white/[0.06] bg-[#0e1017]/30">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search goals..."
            className="w-full pl-10 pr-3.5 py-2.5 bg-[#07080c] border border-white/[0.08] rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-champagne-500/50 transition min-h-[42px]"
          />
        </div>

        <div>
          <select
            value={selectedStatus}
            onChange={(e) => {
              setSelectedStatus(e.target.value);
              setPage(1);
            }}
            className="w-full px-3.5 py-2.5 bg-[#07080c] border border-white/[0.08] rounded-xl text-xs text-slate-300 focus:outline-none focus:border-champagne-500/50 transition min-h-[42px]"
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
        <div className="flex-1 overflow-y-auto space-y-3.5 scrollbar-thin">
          {isLoading ? (
            <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
              <Clock className="w-5 h-5 animate-spin mr-2 text-champagne-400" />
              Loading goals...
            </div>
          ) : error ? (
            <div className="p-5 bg-[#0e1017]/60 border border-white/[0.08] rounded-2xl text-center space-y-2 shadow-sm">
              <AlertCircle className="w-5 h-5 text-champagne-400 mx-auto" />
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
            <div className="flex flex-col items-center justify-center h-64 border border-dashed border-white/[0.08] rounded-2xl p-8 text-center bg-[#0e1017]/20">
              <Target className="w-12 h-12 text-slate-600 mb-3" />
              <h3 className="text-sm font-semibold text-slate-300">No goals set</h3>
              <p className="text-xs text-slate-500 max-w-sm mt-1 mb-4">
                Establish high-level personal or professional goals to guide your daily tasks.
              </p>
              <button
                onClick={handleOpenCreate}
                className="px-4 py-2 bg-white/[0.06] hover:bg-white/[0.1] text-slate-200 text-xs font-medium rounded-xl transition-colors border border-white/[0.08] cursor-pointer"
              >
                Create Goal
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {goalsData?.items.map((goal) => {
                const currentVal = goal.current_value || 0;
                const targetVal = goal.target_value || 100;
                const percent = Math.min(100, Math.round((currentVal / targetVal) * 100));

                return (
                  <div
                    key={goal.id}
                    className="p-5 rounded-2xl bg-[#0e1017]/70 border border-white/[0.06] hover:border-champagne-500/30 hover:bg-[#0e1017]/95 transition-all duration-200 shadow-subtle-elevation flex flex-col justify-between"
                  >
                    <div className="space-y-2">
                      <div className="flex items-start justify-between">
                        <span className="text-sm font-semibold text-slate-100">{goal.title}</span>
                        <div className="flex items-center space-x-1">
                          <button
                            onClick={(e) => handleOpenEdit(e, goal)}
                            className="p-2 -m-1 sm:p-1 sm:m-0 rounded-md text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] transition touch-target flex items-center justify-center cursor-pointer"
                            title="Edit goal"
                            aria-label="Edit goal"
                          >
                            <Edit2 className="w-4 h-4 sm:w-3.5 sm:h-3.5" />
                          </button>
                          <button
                            onClick={(e) => handleDelete(e, goal.id)}
                            className="p-2 -m-1 sm:p-1 sm:m-0 rounded-md text-slate-400 hover:text-rose-400 hover:bg-white/[0.06] transition touch-target flex items-center justify-center cursor-pointer"
                            title="Delete goal"
                            aria-label="Delete goal"
                          >
                            <Trash2 className="w-4 h-4 sm:w-3.5 sm:h-3.5" />
                          </button>
                        </div>
                      </div>

                      {goal.description && (
                        <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">{goal.description}</p>
                      )}
                    </div>

                    <div className="mt-4 pt-3 border-t border-white/[0.06]">
                      <div className="flex items-center justify-between text-xs mb-1.5 font-medium">
                        <span className="text-slate-400">{currentVal} / {targetVal} {goal.unit || '%'}</span>
                        <span className="text-purple-400 font-mono font-semibold">{percent}%</span>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-[#07080c] overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-purple-500 to-indigo-500 rounded-full transition-all duration-300"
                          style={{ width: `${percent}%` }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
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

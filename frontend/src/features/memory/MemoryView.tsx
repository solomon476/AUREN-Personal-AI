/**
 * Memory Explorer Feature View.
 * Core user interface for exploring, filtering, confirming, correcting,
 * and managing long-term persistent memories and their epistemic status.
 * Elevated with AUREN Obsidian & Champagne Design System.
 */

import React, { useState, useEffect } from 'react';
import {
  Brain,
  Search,
  Plus,
  CheckCircle2,
  XCircle,
  Sparkles,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
  Loader2,
  AlertCircle,
  Eye,
  Star,
  X,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import {
  useMemories,
  useConfirmMemory,
  useRejectMemory,
  useCorrectMemory,
  useArchiveMemory,
  useRestoreMemory,
  useOutdateMemory,
  useCreateMemory,
} from '../../hooks/useMemories';
import {
  Memory,
  MemoryType,
  MemoryCategory,
} from '../../api/memories';
import { MemoryDetailModal } from '../../components/memory/MemoryDetailModal';

export const MemoryView: React.FC = () => {
  const { user } = useAuth();

  // Search & Filter State
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedConfirmation, setSelectedConfirmation] = useState<string>('');
  const [selectedLifecycle, setSelectedLifecycle] = useState<string>('active');
  const [page, setPage] = useState<number>(1);
  const pageSize = 12;

  // Debounce search query to prevent flooding queries on every keystroke
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery);
    }, 250);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Selected Memory for Detail Modal
  const [activeMemory, setActiveMemory] = useState<Memory | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);

  // New Memory Modal State
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [newType, setNewType] = useState<MemoryType>('fact');
  const [newCategory, setNewCategory] = useState<MemoryCategory>('general');
  const [newImportance, setNewImportance] = useState(3);
  const [createError, setCreateError] = useState<string | null>(null);

  // Queries and Mutations
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useMemories(user?.id, {
    query: debouncedSearchQuery || undefined,
    memory_type: selectedType || undefined,
    category: selectedCategory || undefined,
    confirmation_status: selectedConfirmation || undefined,
    lifecycle_status: selectedLifecycle || undefined,
    page,
    page_size: pageSize,
  });

  const confirmMutation = useConfirmMemory(user?.id);
  const rejectMutation = useRejectMemory(user?.id);
  const correctMutation = useCorrectMemory(user?.id);
  const archiveMutation = useArchiveMemory(user?.id);
  const restoreMutation = useRestoreMemory(user?.id);
  const outdateMutation = useOutdateMemory(user?.id);
  const createMutation = useCreateMemory(user?.id);

  const handleOpenDetail = (memory: Memory) => {
    setActiveMemory(memory);
    setIsDetailOpen(true);
  };

  const handleCloseDetail = () => {
    setIsDetailOpen(false);
    setActiveMemory(null);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) {
      setCreateError('Memory content cannot be empty.');
      return;
    }

    setCreateError(null);
    try {
      await createMutation.mutateAsync({
        content: newContent.trim(),
        memory_type: newType,
        category: newCategory,
        importance: newImportance,
      });
      setIsCreateOpen(false);
      setNewContent('');
      setPage(1);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create memory.');
    }
  };

  const handleResetFilters = () => {
    setSearchQuery('');
    setSelectedType('');
    setSelectedCategory('');
    setSelectedConfirmation('');
    setSelectedLifecycle('active');
    setPage(1);
  };

  const hasActiveFilters = Boolean(
    searchQuery ||
    selectedType ||
    selectedCategory ||
    selectedConfirmation ||
    (selectedLifecycle && selectedLifecycle !== 'active')
  );

  const renderEpistemicBadge = (status: string) => {
    switch (status) {
      case 'confirmed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-emerald-950/70 text-emerald-300 border border-emerald-800/50 shadow-sm">
            <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-400" />
            Confirmed
          </span>
        );
      case 'unconfirmed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-amber-950/70 text-amber-300 border border-amber-800/50 shadow-sm">
            <Sparkles className="w-3 h-3 mr-1 text-amber-400" />
            Inference
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-rose-950/70 text-rose-300 border border-rose-800/50 shadow-sm">
            <XCircle className="w-3 h-3 mr-1 text-rose-400" />
            Rejected
          </span>
        );
      case 'system_asserted':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-indigo-950/70 text-indigo-300 border border-indigo-800/50 shadow-sm">
            <ShieldCheck className="w-3 h-3 mr-1 text-indigo-400" />
            System
          </span>
        );
      default:
        return null;
    }
  };

  const renderLifecyclePill = (status: string) => {
    if (status === 'active') return null;
    const colors: Record<string, string> = {
      superseded: 'bg-slate-800/80 text-slate-400 border-slate-700',
      expired: 'bg-amber-950/60 text-amber-400 border-amber-900/50',
      archived: 'bg-slate-800/80 text-slate-400 border-slate-700',
      rejected: 'bg-rose-950/60 text-rose-400 border-rose-900/50',
    };
    return (
      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] uppercase font-mono border ${colors[status] || 'bg-slate-800 text-slate-400'}`}>
        {status}
      </span>
    );
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 text-slate-100 overflow-hidden">
      {/* Top Header */}
      <div className="flex-shrink-0 px-6 py-5 border-b border-slate-800/80 bg-slate-900/40 backdrop-blur">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center space-x-3.5">
            <div className="p-2.5 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-sm">
              <Brain className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-xl font-bold text-white tracking-tight">Long-term Memory Explorer</h1>
                <span className="hidden sm:inline-flex text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                  Epistemic Knowledge Base
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Browse, verify inferences, correct inaccuracies, and manage what AUREN remembers
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex items-center justify-center px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition-all duration-200"
          >
            <Plus className="w-4 h-4 mr-1.5" />
            Add Memory
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex-shrink-0 px-6 py-3.5 border-b border-slate-800/80 bg-slate-900/20">
        <div className="flex flex-wrap items-center gap-3">
          {/* Search Box */}
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3.5 top-2.5 h-4 w-4 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(1);
              }}
              placeholder="Search memory content..."
              className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-10 pr-4 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 transition-all duration-150"
            />
          </div>

          {/* Type Select */}
          <select
            value={selectedType}
            onChange={(e) => {
              setSelectedType(e.target.value);
              setPage(1);
            }}
            className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
            aria-label="Filter by memory type"
          >
            <option value="">All Types</option>
            <option value="fact">Fact</option>
            <option value="preference">Preference</option>
            <option value="goal">Goal</option>
            <option value="project">Project</option>
            <option value="context">Context</option>
            <option value="observation">Observation</option>
          </select>

          {/* Category Select */}
          <select
            value={selectedCategory}
            onChange={(e) => {
              setSelectedCategory(e.target.value);
              setPage(1);
            }}
            className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
            aria-label="Filter by category"
          >
            <option value="">All Categories</option>
            <option value="personal">Personal</option>
            <option value="work">Work</option>
            <option value="technical">Technical</option>
            <option value="health_lifestyle">Health & Lifestyle</option>
            <option value="financial">Financial</option>
            <option value="general">General</option>
          </select>

          {/* Epistemic Confirmation Select */}
          <select
            value={selectedConfirmation}
            onChange={(e) => {
              setSelectedConfirmation(e.target.value);
              setPage(1);
            }}
            className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
            aria-label="Filter by confirmation status"
          >
            <option value="">All Epistemic States</option>
            <option value="confirmed">Confirmed</option>
            <option value="unconfirmed">Unconfirmed (Inferred)</option>
            <option value="system_asserted">System Asserted</option>
            <option value="rejected">Rejected</option>
          </select>

          {/* Lifecycle Select */}
          <select
            value={selectedLifecycle}
            onChange={(e) => {
              setSelectedLifecycle(e.target.value);
              setPage(1);
            }}
            className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition"
            aria-label="Filter by lifecycle status"
          >
            <option value="active">Active Only</option>
            <option value="archived">Archived</option>
            <option value="expired">Outdated / Expired</option>
            <option value="superseded">Superseded (Lineage)</option>
            <option value="">All Lifecycle States</option>
          </select>

          {/* Clear Filters */}
          {hasActiveFilters && (
            <button
              onClick={handleResetFilters}
              className="text-xs text-slate-400 hover:text-white px-2.5 py-1.5 rounded-lg hover:bg-slate-800 border border-slate-800 transition"
            >
              Reset Filters
            </button>
          )}
        </div>
      </div>

      {/* Main Grid Content */}
      <div className="flex-1 overflow-y-auto p-6 scrollbar-thin">
        {isLoading && (
          <div className="py-24 flex flex-col items-center justify-center space-y-3 text-slate-400">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
            <p className="text-xs">Loading memories...</p>
          </div>
        )}

        {isError && (
          <div className="py-16 flex flex-col items-center justify-center space-y-3 text-rose-400">
            <AlertCircle className="w-8 h-8" />
            <p className="text-sm font-medium">
              {error instanceof Error ? error.message : 'Failed to load memories.'}
            </p>
            <button
              onClick={() => refetch()}
              className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-white transition"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !isError && data && data.items.length === 0 && (
          <div className="py-24 text-center space-y-3 max-w-md mx-auto">
            <div className="p-3.5 rounded-2xl bg-slate-900 border border-slate-800 inline-block text-slate-500 shadow-sm">
              <Brain className="w-8 h-8" />
            </div>
            <h3 className="text-base font-semibold text-white tracking-tight">No memories found</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              {hasActiveFilters
                ? 'No memories matched your search query and filters. Try clearing some filters or searching for something else.'
                : 'AUREN has not recorded any persistent memories yet. Start chatting or add a verified memory manually.'}
            </p>
            {hasActiveFilters && (
              <button
                onClick={handleResetFilters}
                className="inline-flex items-center px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-indigo-300 border border-slate-700 transition"
              >
                Clear all filters
              </button>
            )}
          </div>
        )}

        {!isLoading && !isError && data && data.items.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.items.map((mem) => (
              <div
                key={mem.id}
                onClick={() => handleOpenDetail(mem)}
                className="group relative flex flex-col justify-between p-4.5 rounded-2xl bg-slate-900/60 border border-slate-800/80 hover:border-indigo-500/40 hover:bg-slate-900/90 transition-all duration-200 shadow-subtle-elevation cursor-pointer"
              >
                <div className="space-y-3">
                  {/* Status header */}
                  <div className="flex items-center justify-between">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {renderEpistemicBadge(mem.confirmation_status)}
                      {renderLifecyclePill(mem.lifecycle_status)}
                    </div>
                    <div className="flex items-center text-slate-500 text-[11px]">
                      {[1, 2, 3, 4, 5].map((s) => (
                        <Star
                          key={s}
                          className={`w-2.5 h-2.5 ${s <= mem.importance ? 'text-amber-400 fill-amber-400' : 'text-slate-800'}`}
                        />
                      ))}
                    </div>
                  </div>

                  {/* Content snippet */}
                  <p className="text-xs text-slate-200 line-clamp-3 leading-relaxed font-sans">
                    {mem.content}
                  </p>
                </div>

                {/* Footer meta & actions */}
                <div className="pt-3 mt-3 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-400">
                  <div className="flex items-center space-x-2">
                    <span className="capitalize px-2 py-0.5 rounded-md bg-slate-950 border border-slate-800 text-[10px] text-slate-400 font-mono">
                      {mem.memory_type}
                    </span>
                    <span className="capitalize text-slate-500 text-[10px]">
                      {mem.category.replace('_', ' ')}
                    </span>
                  </div>

                  <div className="flex items-center space-x-1.5">
                    {mem.confirmation_status === 'unconfirmed' && mem.lifecycle_status === 'active' && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          confirmMutation.mutate(mem.id);
                        }}
                        title="Confirm inference"
                        className="p-1 rounded-md text-emerald-400 hover:bg-emerald-950/60 transition"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleOpenDetail(mem);
                      }}
                      className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition"
                    >
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pagination Footer */}
      {!isLoading && !isError && data && data.total > 0 && (
        <div className="flex-shrink-0 px-6 py-3.5 border-t border-slate-800/80 bg-slate-900/40 flex items-center justify-between text-xs text-slate-400">
          <div>
            Showing <span className="text-white font-medium">{(page - 1) * pageSize + 1}</span> to{' '}
            <span className="text-white font-medium">{Math.min(page * pageSize, data.total)}</span> of{' '}
            <span className="text-white font-medium">{data.total}</span> memories
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="p-1.5 rounded-lg border border-slate-800 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition"
              aria-label="Previous page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-2 font-mono text-slate-300">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="p-1.5 rounded-lg border border-slate-800 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition"
              aria-label="Next page"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Memory Detail Modal */}
      <MemoryDetailModal
        memory={activeMemory}
        isOpen={isDetailOpen}
        onClose={handleCloseDetail}
        onConfirm={async (id) => {
          const updated = await confirmMutation.mutateAsync(id);
          setActiveMemory(updated);
        }}
        onReject={async (id) => {
          const updated = await rejectMutation.mutateAsync(id);
          setActiveMemory(updated);
        }}
        onCorrect={async (id, payload) => {
          const updated = await correctMutation.mutateAsync({ memoryId: id, payload });
          setActiveMemory(updated);
        }}
        onArchive={async (id) => {
          const updated = await archiveMutation.mutateAsync(id);
          setActiveMemory(updated);
        }}
        onRestore={async (id) => {
          const updated = await restoreMutation.mutateAsync(id);
          setActiveMemory(updated);
        }}
        onOutdate={async (id) => {
          const updated = await outdateMutation.mutateAsync(id);
          setActiveMemory(updated);
        }}
      />

      {/* New Memory Modal */}
      {isCreateOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-memory-title"
        >
          <div className="relative w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2.5">
                <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  <Plus className="h-4 w-4" />
                </div>
                <h2 id="create-memory-title" className="text-base font-semibold text-white">
                  Add Confirmed Memory
                </h2>
              </div>
              <button
                onClick={() => setIsCreateOpen(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {createError && (
              <div className="p-2.5 rounded-lg bg-rose-950/60 border border-rose-800/50 text-rose-300 text-xs">
                {createError}
              </div>
            )}

            <form onSubmit={handleCreateSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Memory Statement
                </label>
                <textarea
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  placeholder="e.g., Prefers technical documentation with practical code examples..."
                  rows={3}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  required
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Type</label>
                  <select
                    value={newType}
                    onChange={(e) => setNewType(e.target.value as MemoryType)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl p-2 text-xs text-white"
                  >
                    <option value="fact">Fact</option>
                    <option value="preference">Preference</option>
                    <option value="goal">Goal</option>
                    <option value="project">Project</option>
                    <option value="context">Context</option>
                    <option value="observation">Observation</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Category</label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value as MemoryCategory)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl p-2 text-xs text-white"
                  >
                    <option value="general">General</option>
                    <option value="personal">Personal</option>
                    <option value="work">Work</option>
                    <option value="technical">Technical</option>
                    <option value="health_lifestyle">Health & Lifestyle</option>
                    <option value="financial">Financial</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Importance</label>
                  <select
                    value={newImportance}
                    onChange={(e) => setNewImportance(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl p-2 text-xs text-white"
                  >
                    <option value="1">1 - Minimal</option>
                    <option value="2">2 - Low</option>
                    <option value="3">3 - Normal</option>
                    <option value="4">4 - High</option>
                    <option value="5">5 - Critical</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end space-x-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-3.5 py-1.5 rounded-lg border border-slate-700 text-xs font-medium text-slate-300 hover:bg-slate-800 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="inline-flex items-center px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition"
                >
                  {createMutation.isPending && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
                  Save Confirmed Memory
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

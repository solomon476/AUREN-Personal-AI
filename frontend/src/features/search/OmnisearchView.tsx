/**
 * Phase 3C.5: Omnisearch View
 *
 * Global search across conversations, messages, memories, tasks, projects,
 * and goals. All results are user-scoped and authenticated. Journal entries
 * are excluded by backend design.
 */

import React, { useState, useCallback, useDeferredValue } from 'react';
import {
  Search,
  MessageSquare,
  Brain,
  CheckSquare,
  FolderKanban,
  Target,
  MessageCircle,
  Filter,
  X,
  Clock,
  ChevronRight,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { useNavigate } from '@tanstack/react-router';
import { useAuth } from '../../context/AuthContext';
import { useOmnisearch } from '../../hooks/useSearch';
import { SourceType, SearchResultItem } from '../../api/search';

// ---------------------------------------------------------------------------
// Source type configuration
// ---------------------------------------------------------------------------

const SOURCE_CONFIG: Record<
  SourceType,
  { label: string; icon: React.ReactNode; color: string; badgeColor: string }
> = {
  conversation: {
    label: 'Conversations',
    icon: <MessageCircle className="w-3.5 h-3.5" />,
    color: 'text-sky-400',
    badgeColor: 'bg-sky-950/60 text-sky-300 border-sky-800/40',
  },
  message: {
    label: 'Messages',
    icon: <MessageSquare className="w-3.5 h-3.5" />,
    color: 'text-blue-400',
    badgeColor: 'bg-blue-950/60 text-blue-300 border-blue-800/40',
  },
  memory: {
    label: 'Memories',
    icon: <Brain className="w-3.5 h-3.5" />,
    color: 'text-violet-400',
    badgeColor: 'bg-violet-950/60 text-violet-300 border-violet-800/40',
  },
  task: {
    label: 'Tasks',
    icon: <CheckSquare className="w-3.5 h-3.5" />,
    color: 'text-emerald-400',
    badgeColor: 'bg-emerald-950/60 text-emerald-300 border-emerald-800/40',
  },
  project: {
    label: 'Projects',
    icon: <FolderKanban className="w-3.5 h-3.5" />,
    color: 'text-amber-400',
    badgeColor: 'bg-amber-950/60 text-amber-300 border-amber-800/40',
  },
  goal: {
    label: 'Goals',
    icon: <Target className="w-3.5 h-3.5" />,
    color: 'text-rose-400',
    badgeColor: 'bg-rose-950/60 text-rose-300 border-rose-800/40',
  },
};

const ALL_SOURCE_TYPES = Object.keys(SOURCE_CONFIG) as SourceType[];

// ---------------------------------------------------------------------------
// ResultCard
// ---------------------------------------------------------------------------

interface ResultCardProps {
  item: SearchResultItem;
}

const ResultCard: React.FC<ResultCardProps> = ({ item }) => {
  const navigate = useNavigate();
  const cfg = SOURCE_CONFIG[item.source_type];

  const handleClick = () => {
    navigate({ to: item.navigation_path as never });
  };

  return (
    <button
      onClick={handleClick}
      className="w-full text-left bg-slate-900/60 border border-slate-800/60 rounded-lg p-4 hover:bg-slate-800/60 hover:border-slate-700/60 transition-all group"
    >
      <div className="flex items-start gap-3">
        {/* Source icon */}
        <div className={`mt-0.5 flex-shrink-0 ${cfg.color}`}>{cfg.icon}</div>

        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded border ${cfg.badgeColor}`}
            >
              {cfg.label}
            </span>
            <span className="text-slate-200 text-sm font-medium truncate">{item.title}</span>
          </div>

          {/* Snippet */}
          <p className="text-slate-400 text-xs line-clamp-2 leading-relaxed">{item.snippet}</p>

          {/* Footer */}
          <div className="flex items-center gap-3 mt-2">
            <span className="text-slate-600 text-xs flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {new Date(item.created_at).toLocaleDateString()}
            </span>
            <span className="text-slate-600 text-xs">{item.provenance}</span>
            <span className="text-slate-600 text-xs ml-auto">
              {Math.round(item.score * 100)}% match
            </span>
          </div>
        </div>

        <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-slate-400 flex-shrink-0 mt-1 transition-colors" />
      </div>
    </button>
  );
};

// ---------------------------------------------------------------------------
// OmnisearchView
// ---------------------------------------------------------------------------

export const OmnisearchView: React.FC = () => {
  const { user } = useAuth();
  const userId = user?.id;

  const [rawQuery, setRawQuery] = useState('');
  const [selectedSources, setSelectedSources] = useState<SourceType[]>([]);
  const [page, setPage] = useState(1);

  // Defer the query so typing doesn't trigger requests mid-keystroke
  const query = useDeferredValue(rawQuery);

  const { data, isLoading, isFetching, error } = useOmnisearch(
    userId,
    {
      q: query,
      sources: selectedSources.length > 0 ? selectedSources : undefined,
      page,
      page_size: 20,
    },
    { enabled: query.trim().length >= 2 }
  );

  const toggleSource = useCallback((src: SourceType) => {
    setSelectedSources((prev) =>
      prev.includes(src) ? prev.filter((s) => s !== src) : [...prev, src]
    );
    setPage(1);
  }, []);

  const handleQueryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setRawQuery(e.target.value);
    setPage(1);
  };

  const clearQuery = () => {
    setRawQuery('');
    setPage(1);
  };

  const isSearching = isLoading || isFetching;
  const hasResults = data && data.results.length > 0;
  const hasQuery = query.trim().length >= 2;

  return (
    <div className="flex flex-col h-full bg-slate-950">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-slate-800/60 px-6 py-5">
        <div className="flex items-center gap-3 mb-1">
          <Search className="w-5 h-5 text-violet-400" />
          <h1 className="text-lg font-semibold text-slate-100">Omnisearch</h1>
          <span className="text-xs text-slate-500 bg-slate-800/60 border border-slate-700/40 px-2 py-0.5 rounded-full">
            Phase 3C.5
          </span>
        </div>
        <p className="text-slate-500 text-sm">
          Search across conversations, memories, tasks, projects, and goals.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
        {/* Search input */}
        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none" />
          <input
            type="text"
            value={rawQuery}
            onChange={handleQueryChange}
            placeholder="Search everything… (min 2 characters)"
            className="w-full bg-slate-900/80 border border-slate-700/60 rounded-lg pl-10 pr-10 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-violet-600/60 focus:ring-1 focus:ring-violet-600/20 transition-all"
          />
          {rawQuery && (
            <button
              onClick={clearQuery}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Source filters */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="flex items-center gap-1 text-xs text-slate-500">
            <Filter className="w-3 h-3" /> Filter:
          </span>
          {ALL_SOURCE_TYPES.map((src) => {
            const cfg = SOURCE_CONFIG[src];
            const active = selectedSources.includes(src);
            return (
              <button
                key={src}
                onClick={() => toggleSource(src)}
                className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all ${
                  active
                    ? `${cfg.badgeColor} border-current`
                    : 'bg-slate-900/40 text-slate-500 border-slate-700/40 hover:border-slate-600/60 hover:text-slate-400'
                }`}
              >
                {cfg.icon}
                {cfg.label}
              </button>
            );
          })}
          {selectedSources.length > 0 && (
            <button
              onClick={() => setSelectedSources([])}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              Clear
            </button>
          )}
        </div>

        {/* Loading state */}
        {isSearching && hasQuery && (
          <div className="flex items-center gap-2 text-slate-500 text-sm py-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            Searching…
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="flex items-center gap-2 text-rose-400 text-sm bg-rose-950/20 border border-rose-800/30 rounded-lg p-3">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            Search failed. Please try again.
          </div>
        )}

        {/* Empty state — no query */}
        {!hasQuery && !isSearching && (
          <div className="text-center py-16 text-slate-600">
            <Search className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Type at least 2 characters to search</p>
            <p className="text-xs mt-1">
              Searches conversations, memories, tasks, projects, and goals
            </p>
          </div>
        )}

        {/* Empty results */}
        {hasQuery && !isSearching && data && data.results.length === 0 && (
          <div className="text-center py-12 text-slate-600">
            <Search className="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">No results found for "{query}"</p>
            <p className="text-xs mt-1">Try different keywords or remove source filters</p>
          </div>
        )}

        {/* Results */}
        {hasResults && (
          <>
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span>
                {data.total_count} result{data.total_count !== 1 ? 's' : ''}
                {selectedSources.length > 0 &&
                  ` in ${selectedSources.map((s) => SOURCE_CONFIG[s].label).join(', ')}`}
              </span>
              <span>
                Page {data.page} of {Math.ceil(data.total_count / data.page_size)}
              </span>
            </div>

            <div className="space-y-2">
              {data.results.map((item) => (
                <ResultCard key={`${item.source_type}-${item.id}`} item={item} />
              ))}
            </div>

            {/* Pagination */}
            {(page > 1 || data.has_more) && (
              <div className="flex items-center justify-center gap-3 pt-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="text-xs text-slate-400 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors px-3 py-1.5 rounded border border-slate-700/40 hover:border-slate-600/60"
                >
                  Previous
                </button>
                <span className="text-xs text-slate-500">Page {page}</span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={!data.has_more}
                  className="text-xs text-slate-400 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors px-3 py-1.5 rounded border border-slate-700/40 hover:border-slate-600/60"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

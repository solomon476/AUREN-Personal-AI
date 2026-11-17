/**
 * Phase 3C.5: Reflective Intelligence View
 *
 * Displays AI-detected contradictions, staleness review items, and insight counts.
 * All findings are framed as suggestions for user review — no records are modified
 * through this view. Journal entries are excluded by backend design.
 */

import React, { useState } from 'react';
import {
  Sparkles,
  AlertTriangle,
  Clock,
  Link2,
  RefreshCw,
  CheckSquare,
  FolderKanban,
  Target,
  Brain,
  MessageCircle,
  ChevronDown,
  ChevronRight,
  Loader2,
  Info,
} from 'lucide-react';
import { useNavigate } from '@tanstack/react-router';
import { useAuth } from '../../context/AuthContext';
import { useReflectionInsights, useStaleness, useContradictions } from '../../hooks/useSearch';
import { StalenessItem, ContradictionItem, SourceType } from '../../api/search';

// ---------------------------------------------------------------------------
// Source icon helper
// ---------------------------------------------------------------------------

const SOURCE_ICONS: Record<SourceType, React.ReactNode> = {
  conversation: <MessageCircle className="w-3.5 h-3.5" />,
  message: <MessageCircle className="w-3.5 h-3.5" />,
  memory: <Brain className="w-3.5 h-3.5" />,
  task: <CheckSquare className="w-3.5 h-3.5" />,
  project: <FolderKanban className="w-3.5 h-3.5" />,
  goal: <Target className="w-3.5 h-3.5" />,
};

const SOURCE_COLORS: Record<SourceType, string> = {
  conversation: 'text-sky-400',
  message: 'text-blue-400',
  memory: 'text-violet-400',
  task: 'text-emerald-400',
  project: 'text-amber-400',
  goal: 'text-rose-400',
};

// ---------------------------------------------------------------------------
// Staleness Card
// ---------------------------------------------------------------------------

interface StalenessCardProps {
  item: StalenessItem;
}

const StalenessCard: React.FC<StalenessCardProps> = ({ item }) => {
  const navigate = useNavigate();
  const scorePercent = Math.round(item.staleness_score * 100);
  const scoreColor =
    scorePercent >= 80
      ? 'text-rose-400'
      : scorePercent >= 50
      ? 'text-amber-400'
      : 'text-yellow-400';

  return (
    <div className="bg-slate-900/60 border border-slate-800/60 rounded-lg p-3.5 hover:border-slate-700/60 transition-colors">
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 flex-shrink-0 ${SOURCE_COLORS[item.source_type]}`}>
          {SOURCE_ICONS[item.source_type]}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-slate-200 text-sm font-medium truncate">{item.title}</span>
            <span className={`text-xs font-mono flex-shrink-0 ${scoreColor}`}>
              {scorePercent}%
            </span>
          </div>
          <p className="text-slate-400 text-xs mb-2 leading-relaxed">{item.reason}</p>
          {item.last_updated && (
            <p className="text-slate-600 text-xs flex items-center gap-1">
              <Clock className="w-3 h-3" />
              Last updated: {new Date(item.last_updated).toLocaleDateString()}
            </p>
          )}
        </div>
        <button
          onClick={() => navigate({ to: item.navigation_path as never })}
          className="flex-shrink-0 text-xs text-slate-500 hover:text-slate-300 transition-colors flex items-center gap-1 mt-0.5"
        >
          View <ChevronRight className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Contradiction Card
// ---------------------------------------------------------------------------

interface ContradictionCardProps {
  item: ContradictionItem;
}

const ContradictionCard: React.FC<ContradictionCardProps> = ({ item }) => {
  const [expanded, setExpanded] = useState(false);

  const typeLabel =
    item.contradiction_type === 'value_conflict'
      ? 'Value Conflict'
      : item.contradiction_type === 'supersession_chain'
      ? 'Supersession Chain'
      : 'Temporal Inconsistency';

  const confidencePercent = Math.round(item.confidence * 100);

  return (
    <div className="bg-slate-900/60 border border-amber-900/30 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded((p) => !p)}
        className="w-full text-left px-4 py-3.5 flex items-start gap-3 hover:bg-slate-800/40 transition-colors"
      >
        <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-xs bg-amber-950/60 text-amber-300 border border-amber-800/40 px-1.5 py-0.5 rounded">
              {typeLabel}
            </span>
            <span className="text-xs text-slate-500">{confidencePercent}% confidence</span>
          </div>
          <p className="text-slate-300 text-xs line-clamp-1 leading-relaxed">
            {item.memory_a_content}
          </p>
        </div>
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-slate-500 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-slate-500 flex-shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-slate-800/60">
          <div className="pt-3 grid grid-cols-1 gap-2">
            <div className="bg-slate-800/40 rounded p-2.5">
              <span className="text-xs text-slate-500 block mb-1">
                Memory A ({item.memory_a_status})
              </span>
              <p className="text-slate-300 text-xs">{item.memory_a_content}</p>
            </div>
            <div className="bg-slate-800/40 rounded p-2.5">
              <span className="text-xs text-slate-500 block mb-1">
                Memory B ({item.memory_b_status})
              </span>
              <p className="text-slate-300 text-xs">{item.memory_b_content}</p>
            </div>
          </div>
          <div className="bg-amber-950/20 border border-amber-900/30 rounded p-2.5">
            <p className="text-amber-300 text-xs font-medium mb-1">Explanation</p>
            <p className="text-slate-400 text-xs">{item.explanation}</p>
          </div>
          <div className="bg-slate-800/30 rounded p-2.5">
            <p className="text-slate-400 text-xs font-medium mb-1">Suggested action</p>
            <p className="text-slate-400 text-xs">{item.suggested_action}</p>
          </div>
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// InsightStat
// ---------------------------------------------------------------------------

interface InsightStatProps {
  label: string;
  value: number;
  icon: React.ReactNode;
  color: string;
}

const InsightStat: React.FC<InsightStatProps> = ({ label, value, icon, color }) => (
  <div className="bg-slate-900/60 border border-slate-800/60 rounded-lg p-4 flex items-center gap-3">
    <div className={`flex-shrink-0 ${color}`}>{icon}</div>
    <div>
      <p className="text-2xl font-semibold text-slate-100">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// ReflectionView
// ---------------------------------------------------------------------------

export const ReflectionView: React.FC = () => {
  const { user } = useAuth();
  const userId = user?.id;
  const [activeTab, setActiveTab] = useState<'staleness' | 'contradictions'>('staleness');

  const {
    data: insights,
    isLoading: insightsLoading,
    refetch: refetchInsights,
    isFetching: insightsFetching,
  } = useReflectionInsights(userId);

  const { data: stalenessData, isLoading: stalenessLoading } = useStaleness(userId);
  const { data: contradictionsData, isLoading: contradictionsLoading } = useContradictions(userId);

  const isLoading = insightsLoading || stalenessLoading || contradictionsLoading;

  return (
    <div className="flex flex-col h-full bg-slate-950">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-slate-800/60 px-6 py-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <Sparkles className="w-5 h-5 text-violet-400" />
              <h1 className="text-lg font-semibold text-slate-100">Reflective Intelligence</h1>
              <span className="text-xs text-slate-500 bg-slate-800/60 border border-slate-700/40 px-2 py-0.5 rounded-full">
                Phase 3C.5
              </span>
            </div>
            <p className="text-slate-500 text-sm">
              AI-assisted review of potential conflicts, outdated records, and connections.
            </p>
          </div>
          <button
            onClick={() => refetchInsights()}
            disabled={insightsFetching}
            className="flex items-center gap-2 text-xs text-slate-400 hover:text-slate-200 transition-colors px-3 py-1.5 rounded border border-slate-700/40 hover:border-slate-600/60 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${insightsFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
        {/* Epistemic note */}
        <div className="flex items-start gap-2 bg-slate-900/40 border border-slate-800/40 rounded-lg p-3">
          <Info className="w-4 h-4 text-slate-500 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-slate-500 leading-relaxed">
            All findings are <strong className="text-slate-400">suggestions for your review</strong>,
            not established facts. No records are modified through this view.
            Contradictions and staleness are detected heuristically and may contain false positives.
          </p>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center gap-2 text-slate-500 text-sm py-4">
            <Loader2 className="w-4 h-4 animate-spin" />
            Analysing your data…
          </div>
        )}

        {/* Insight stats */}
        {insights && (
          <div className="grid grid-cols-3 gap-3">
            <InsightStat
              label="Potential contradictions"
              value={insights.contradiction_count}
              icon={<AlertTriangle className="w-5 h-5" />}
              color="text-amber-400"
            />
            <InsightStat
              label="Staleness items"
              value={insights.staleness_count}
              icon={<Clock className="w-5 h-5" />}
              color="text-sky-400"
            />
            <InsightStat
              label="Superseded memories"
              value={insights.inferred_link_count}
              icon={<Link2 className="w-5 h-5" />}
              color="text-violet-400"
            />
          </div>
        )}

        {/* Tab navigation */}
        <div className="flex gap-1 bg-slate-900/40 border border-slate-800/40 rounded-lg p-1">
          <button
            onClick={() => setActiveTab('staleness')}
            className={`flex-1 text-xs py-1.5 px-3 rounded transition-all ${
              activeTab === 'staleness'
                ? 'bg-slate-800 text-slate-100'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <span className="flex items-center justify-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              Staleness Review ({stalenessData?.count ?? 0})
            </span>
          </button>
          <button
            onClick={() => setActiveTab('contradictions')}
            className={`flex-1 text-xs py-1.5 px-3 rounded transition-all ${
              activeTab === 'contradictions'
                ? 'bg-slate-800 text-slate-100'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <span className="flex items-center justify-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              Contradictions ({contradictionsData?.count ?? 0})
            </span>
          </button>
        </div>

        {/* Staleness tab */}
        {activeTab === 'staleness' && (
          <div className="space-y-2">
            {stalenessLoading && (
              <div className="flex items-center gap-2 text-slate-500 text-sm py-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading…
              </div>
            )}
            {!stalenessLoading && stalenessData && stalenessData.items.length === 0 && (
              <div className="text-center py-10 text-slate-600">
                <Clock className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No staleness items found</p>
                <p className="text-xs mt-1">All your records appear up to date</p>
              </div>
            )}
            {stalenessData?.items.map((item) => (
              <StalenessCard key={`${item.source_type}-${item.id}`} item={item} />
            ))}
          </div>
        )}

        {/* Contradictions tab */}
        {activeTab === 'contradictions' && (
          <div className="space-y-2">
            {contradictionsLoading && (
              <div className="flex items-center gap-2 text-slate-500 text-sm py-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading…
              </div>
            )}
            {!contradictionsLoading &&
              contradictionsData &&
              contradictionsData.contradictions.length === 0 && (
                <div className="text-center py-10 text-slate-600">
                  <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">No contradictions detected</p>
                  <p className="text-xs mt-1">Your memories appear consistent</p>
                </div>
              )}
            {contradictionsData?.contradictions.map((item, i) => (
              <ContradictionCard key={`${item.memory_a_id}-${item.memory_b_id}-${i}`} item={item} />
            ))}
          </div>
        )}

        {insights && (
          <p className="text-xs text-slate-700 text-center">
            Analysis generated at{' '}
            {new Date(insights.generated_at).toLocaleString()}
          </p>
        )}
      </div>
    </div>
  );
};

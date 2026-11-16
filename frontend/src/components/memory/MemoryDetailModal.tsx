/**
 * Memory Detail Modal with Epistemic Verification and Lineage Controls.
 * Displays full provenance, epistemic confidence, and lineage tracking.
 */

import React, { useState } from 'react';
import {
  X,
  CheckCircle2,
  XCircle,
  Edit3,
  Archive,
  RotateCcw,
  Clock,
  Sparkles,
  Info,
  ShieldCheck,
  AlertTriangle,
  GitBranch,
  Star,
  Loader2,
} from 'lucide-react';
import { Memory, CorrectMemoryPayload, MemoryType, MemoryCategory } from '../../api/memories';

interface MemoryDetailModalProps {
  memory: Memory | null;
  isOpen: boolean;
  onClose: () => void;
  onConfirm?: (id: string) => Promise<void>;
  onReject?: (id: string) => Promise<void>;
  onCorrect?: (id: string, payload: CorrectMemoryPayload) => Promise<void>;
  onArchive?: (id: string) => Promise<void>;
  onRestore?: (id: string) => Promise<void>;
  onOutdate?: (id: string) => Promise<void>;
}

export const MemoryDetailModal: React.FC<MemoryDetailModalProps> = ({
  memory,
  isOpen,
  onClose,
  onConfirm,
  onReject,
  onCorrect,
  onArchive,
  onRestore,
  onOutdate,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [editType, setEditType] = useState<MemoryType>('fact');
  const [editCategory, setEditCategory] = useState<MemoryCategory>('general');
  const [editImportance, setEditImportance] = useState(3);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!isOpen || !memory) return null;

  const handleStartEditing = () => {
    setEditContent(memory.content);
    setEditType(memory.memory_type);
    setEditCategory(memory.category);
    setEditImportance(memory.importance);
    setIsEditing(true);
    setActionError(null);
  };

  const handleSaveCorrection = async () => {
    if (!editContent.trim()) {
      setActionError('Memory content cannot be empty.');
      return;
    }
    if (!onCorrect) return;

    setActionLoading(true);
    setActionError(null);
    try {
      await onCorrect(memory.id, {
        content: editContent.trim(),
        memory_type: editType,
        category: editCategory,
        importance: editImportance,
      });
      setIsEditing(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to save correction.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleAction = async (actionFn?: (id: string) => Promise<void>) => {
    if (!actionFn) return;
    setActionLoading(true);
    setActionError(null);
    try {
      await actionFn(memory.id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Action failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && !isEditing) {
      onClose();
    }
  };

  const renderEpistemicBadge = () => {
    switch (memory.confirmation_status) {
      case 'confirmed':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-800/50">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1 text-emerald-400" />
            Confirmed Fact
          </span>
        );
      case 'unconfirmed':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-950/80 text-amber-300 border border-amber-800/50">
            <Sparkles className="w-3.5 h-3.5 mr-1 text-amber-400" />
            Unconfirmed Inference
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-950/80 text-rose-300 border border-rose-800/50">
            <XCircle className="w-3.5 h-3.5 mr-1 text-rose-400" />
            Rejected
          </span>
        );
      case 'system_asserted':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-950/80 text-purple-300 border border-purple-800/50">
            <ShieldCheck className="w-3.5 h-3.5 mr-1 text-purple-400" />
            System Asserted
          </span>
        );
      default:
        return null;
    }
  };

  const renderLifecycleBadge = () => {
    const statusMap: Record<string, { label: string; color: string }> = {
      active: { label: 'Active', color: 'bg-cyan-950/80 text-cyan-300 border-cyan-800/50' },
      superseded: { label: 'Superseded (Corrected)', color: 'bg-slate-800 text-slate-400 border-slate-700' },
      expired: { label: 'Outdated / Expired', color: 'bg-amber-950/60 text-amber-400 border-amber-900/50' },
      archived: { label: 'Archived', color: 'bg-slate-800 text-slate-400 border-slate-700' },
      rejected: { label: 'Rejected', color: 'bg-rose-950/60 text-rose-400 border-rose-900/50' },
      forgotten: { label: 'Forgotten (Purged)', color: 'bg-slate-900 text-slate-500 border-slate-800' },
    };
    const conf = statusMap[memory.lifecycle_status] || { label: memory.lifecycle_status, color: 'bg-slate-800 text-slate-400 border-slate-700' };
    return (
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${conf.color}`}>
        {conf.label}
      </span>
    );
  };

  const getEpistemicExplanation = () => {
    switch (memory.confirmation_status) {
      case 'confirmed':
        return 'Explicitly confirmed through direct user verification or edit. AUREN treats this as an established fact in conversational reasoning.';
      case 'unconfirmed':
        return 'Inferred by AUREN from conversation context. Not yet confirmed by you; interpreted as tentative context until verified.';
      case 'rejected':
        return 'Rejected by you as inaccurate or unwanted. This memory is permanently excluded from retrieval and cannot be reactivated.';
      case 'system_asserted':
        return 'System-asserted baseline preference or constraint.';
      default:
        return 'Epistemic status tracked in database.';
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200"
      onKeyDown={handleKeyDown}
      role="dialog"
      aria-modal="true"
      aria-labelledby="memory-detail-title"
    >
      <div className="relative w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto">
        {/* Modal Header */}
        <div className="flex items-start justify-between pb-3 border-b border-slate-800">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-1.5">
              <h2 id="memory-detail-title" className="text-lg font-semibold text-white">
                Memory Details
              </h2>
              {renderEpistemicBadge()}
              {renderLifecycleBadge()}
            </div>
            <p className="text-xs text-slate-400">
              Audit trail, provenance, and epistemic verification controls
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Action Error Banner */}
        {actionError && (
          <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-800/50 flex items-start space-x-2 text-rose-300 text-xs">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 text-rose-400 mt-0.5" />
            <span>{actionError}</span>
          </div>
        )}

        {/* Epistemic Meaning Explanatory Banner */}
        <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800/80 flex items-start space-x-2.5">
          <Info className="w-4 h-4 text-cyan-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-slate-300 space-y-0.5">
            <span className="font-semibold text-cyan-300">Epistemic Status: </span>
            {getEpistemicExplanation()}
          </div>
        </div>

        {/* Memory Content Section */}
        {isEditing ? (
          <div className="space-y-4 p-4 rounded-xl bg-slate-950/80 border border-cyan-800/40">
            <div className="flex items-center space-x-2 text-cyan-400 text-xs font-semibold uppercase tracking-wider">
              <Edit3 className="w-3.5 h-3.5" />
              <span>Correct Memory (Preserves Historical Lineage)</span>
            </div>
            <p className="text-xs text-slate-400">
              Updating this memory will not erase the past. The current record will be marked as{' '}
              <span className="font-semibold text-slate-300">superseded</span> and a new verified version will be created linked to it.
            </p>
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              className="w-full h-24 bg-slate-900 border border-slate-700 rounded-lg p-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
              placeholder="Corrected memory content..."
            />
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Type</label>
                <select
                  value={editType}
                  onChange={(e) => setEditType(e.target.value as MemoryType)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-xs text-white"
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
                  value={editCategory}
                  onChange={(e) => setEditCategory(e.target.value as MemoryCategory)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-xs text-white"
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
                <label className="block text-xs font-medium text-slate-400 mb-1">Importance (1-5)</label>
                <select
                  value={editImportance}
                  onChange={(e) => setEditImportance(Number(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-xs text-white"
                >
                  <option value="1">1 - Minimal</option>
                  <option value="2">2 - Low</option>
                  <option value="3">3 - Normal</option>
                  <option value="4">4 - High</option>
                  <option value="5">5 - Critical</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setIsEditing(false)}
                disabled={actionLoading}
                className="px-3 py-1.5 rounded-lg border border-slate-700 text-xs font-medium text-slate-300 hover:bg-slate-800 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveCorrection}
                disabled={actionLoading}
                className="inline-flex items-center px-4 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold transition"
              >
                {actionLoading && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
                Save Lineage-Preserving Correction
              </button>
            </div>
          </div>
        ) : (
          <div className="p-4 rounded-xl bg-slate-950/50 border border-slate-800 space-y-2">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Memory Content</span>
            <p className="text-sm text-slate-100 whitespace-pre-wrap leading-relaxed">{memory.content}</p>
          </div>
        )}

        {/* Classification & Metadata Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="p-2.5 rounded-lg bg-slate-950/40 border border-slate-800/80">
            <span className="text-slate-500 block mb-0.5">Type</span>
            <span className="font-semibold text-slate-200 capitalize">{memory.memory_type}</span>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-950/40 border border-slate-800/80">
            <span className="text-slate-500 block mb-0.5">Category</span>
            <span className="font-semibold text-slate-200 capitalize">{memory.category.replace('_', ' ')}</span>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-950/40 border border-slate-800/80">
            <span className="text-slate-500 block mb-0.5">Importance</span>
            <div className="flex items-center space-x-1">
              {[1, 2, 3, 4, 5].map((star) => (
                <Star
                  key={star}
                  className={`w-3 h-3 ${star <= memory.importance ? 'text-amber-400 fill-amber-400' : 'text-slate-700'}`}
                />
              ))}
              <span className="font-semibold text-slate-200 ml-1">{memory.importance}/5</span>
            </div>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-950/40 border border-slate-800/80">
            <span className="text-slate-500 block mb-0.5" title="Model processing score; does not denote factual truth probability">
              Extraction score
            </span>
            <span className="font-semibold text-slate-200">
              {memory.confidence != null ? `${Math.round(memory.confidence * 100)}%` : 'Explicit'}
            </span>
            <span className="text-[10px] text-slate-500 block mt-0.5 leading-tight">
              Pipeline extraction score, not factual probability
            </span>
          </div>
        </div>

        {/* Provenance & Lineage Section */}
        <div className="p-3.5 rounded-xl bg-slate-950/50 border border-slate-800 space-y-2 text-xs">
          <div className="flex items-center space-x-1.5 text-slate-400 font-semibold uppercase tracking-wider mb-1">
            <GitBranch className="w-3.5 h-3.5 text-cyan-400" />
            <span>Provenance & Historical Lineage</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-slate-400">
            <div>
              <span className="text-slate-500">Origin: </span>
              <span className="font-mono text-slate-300">{memory.origin}</span>
            </div>
            <div>
              <span className="text-slate-500">Access Count: </span>
              <span className="text-slate-300">{memory.access_count} times</span>
            </div>
            <div>
              <span className="text-slate-500">Created: </span>
              <span className="text-slate-300">{new Date(memory.created_at).toLocaleString()}</span>
            </div>
            <div>
              <span className="text-slate-500">Last Updated: </span>
              <span className="text-slate-300">{new Date(memory.updated_at).toLocaleString()}</span>
            </div>
            {memory.last_confirmed_at && (
              <div>
                <span className="text-slate-500">Confirmed: </span>
                <span className="text-emerald-400">{new Date(memory.last_confirmed_at).toLocaleString()}</span>
              </div>
            )}
            {memory.previous_version_id && (
              <div className="sm:col-span-2">
                <span className="text-slate-500">Successor to (Previous Version): </span>
                <code className="text-cyan-400 font-mono text-[11px]">{memory.previous_version_id}</code>
              </div>
            )}
            {memory.superseded_by_id && (
              <div className="sm:col-span-2">
                <span className="text-slate-500">Superseded By (Newer Version): </span>
                <code className="text-amber-400 font-mono text-[11px]">{memory.superseded_by_id}</code>
              </div>
            )}
            {memory.source_conversation_id && (
              <div className="sm:col-span-2">
                <span className="text-slate-500">Source Conversation: </span>
                <code className="text-slate-300 font-mono text-[11px]">{memory.source_conversation_id}</code>
              </div>
            )}
          </div>
        </div>

        {/* Epistemic Action Controls Footer */}
        {!isEditing && (
          <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-slate-800">
            <div className="flex flex-wrap items-center gap-2">
              {/* Unconfirmed Controls */}
              {memory.confirmation_status === 'unconfirmed' && memory.lifecycle_status === 'active' && (
                <>
                  <button
                    type="button"
                    onClick={() => handleAction(onConfirm)}
                    disabled={actionLoading}
                    className="inline-flex items-center px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition"
                  >
                    {actionLoading ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5 mr-1" />}
                    Confirm Inference
                  </button>
                  <button
                    type="button"
                    onClick={() => handleAction(onReject)}
                    disabled={actionLoading}
                    className="inline-flex items-center px-3 py-1.5 rounded-lg bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-800/60 text-xs font-semibold transition"
                  >
                    {actionLoading ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <XCircle className="w-3.5 h-3.5 mr-1" />}
                    Reject Inference
                  </button>
                </>
              )}

              {/* Active State Actions */}
              {memory.lifecycle_status === 'active' && (
                <>
                  <button
                    type="button"
                    onClick={handleStartEditing}
                    disabled={actionLoading}
                    className="inline-flex items-center px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-cyan-800/40 text-xs font-medium transition"
                  >
                    <Edit3 className="w-3.5 h-3.5 mr-1" />
                    Correct Memory
                  </button>
                  <button
                    type="button"
                    onClick={() => handleAction(onOutdate)}
                    disabled={actionLoading}
                    className="inline-flex items-center px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-amber-300 border border-amber-800/40 text-xs font-medium transition"
                  >
                    <Clock className="w-3.5 h-3.5 mr-1" />
                    Mark Outdated
                  </button>
                  <button
                    type="button"
                    onClick={() => handleAction(onArchive)}
                    disabled={actionLoading}
                    className="inline-flex items-center px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-xs font-medium transition"
                  >
                    <Archive className="w-3.5 h-3.5 mr-1" />
                    Archive
                  </button>
                </>
              )}

              {/* Archived or Expired Actions */}
              {(memory.lifecycle_status === 'archived' || memory.lifecycle_status === 'expired') && (
                <button
                  type="button"
                  onClick={() => handleAction(onRestore)}
                  disabled={actionLoading}
                  className="inline-flex items-center px-3 py-1.5 rounded-lg bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-800/50 text-xs font-medium transition"
                >
                  {actionLoading ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5 mr-1" />}
                  Restore to Active
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white text-xs font-medium transition"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * Context Inspector Modal for In-Chat Memory Transparency.
 * Exposes exact context provenance and memories injected into an assistant response.
 */

import React from 'react';
import {
  X,
  Brain,
  ShieldCheck,
  CheckCircle2,
  Sparkles,
  Lock,
  Star,
  Loader2,
  AlertCircle,
  HelpCircle,
} from 'lucide-react';
import { useMessageContext } from '../../hooks/useMemories';

interface ContextInspectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  conversationId?: string;
  messageId?: string;
  userId?: string;
}

export const ContextInspectorModal: React.FC<ContextInspectorModalProps> = ({
  isOpen,
  onClose,
  conversationId,
  messageId,
  userId,
}) => {
  const { data, isLoading, isError, error } = useMessageContext(userId, conversationId, messageId);

  if (!isOpen) return null;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  const renderEpistemicBadge = (status: string) => {
    switch (status) {
      case 'confirmed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-800/50">
            <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-400" />
            Confirmed
          </span>
        );
      case 'unconfirmed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-amber-950/80 text-amber-300 border border-amber-800/50">
            <Sparkles className="w-3 h-3 mr-1 text-amber-400" />
            Unconfirmed
          </span>
        );
      case 'system_asserted':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-purple-950/80 text-purple-300 border border-purple-800/50">
            <ShieldCheck className="w-3 h-3 mr-1 text-purple-400" />
            System
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
            {status}
          </span>
        );
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200"
      onKeyDown={handleKeyDown}
      role="dialog"
      aria-modal="true"
      aria-labelledby="context-inspector-title"
    >
      <div className="relative w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between pb-3 border-b border-slate-800 flex-shrink-0">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-xl bg-cyan-950/80 text-cyan-400 border border-cyan-800/40">
              <Brain className="h-5 w-5" />
            </div>
            <div>
              <h2 id="context-inspector-title" className="text-base font-semibold text-white">
                Context Inspector & Memory Provenance
              </h2>
              <p className="text-xs text-slate-400">
                Transparent view of long-term memory candidates injected into this response
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Journal Isolation Notice */}
        <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 flex items-start space-x-2 text-xs flex-shrink-0">
          <Lock className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
          <p className="text-slate-300 leading-relaxed">
            <strong className="text-emerald-400 font-medium">Strict Journal Isolation: </strong>
            Private journal entries are cryptographically protected and never injected into conversation context without your explicit HMAC consent.
          </p>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto pr-1 space-y-3">
          {isLoading && (
            <div className="py-12 flex flex-col items-center justify-center space-y-3 text-slate-400">
              <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
              <p className="text-xs">Fetching recorded context provenance...</p>
            </div>
          )}

          {isError && (
            <div className="py-8 flex flex-col items-center justify-center space-y-2 text-rose-400">
              <AlertCircle className="w-6 h-6" />
              <p className="text-xs font-medium">
                {error instanceof Error ? error.message : 'Failed to load context provenance.'}
              </p>
            </div>
          )}

          {!isLoading && !isError && data && (
            <>
              {/* Context Summary Meta */}
              <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-lg bg-slate-950/40 border border-slate-800/80 text-xs">
                <div className="flex items-center space-x-2">
                  <span className="text-slate-400">Model:</span>
                  <span className="font-mono text-cyan-300">{data.model || 'Unknown'}</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-slate-400">Memories Injected:</span>
                  <span className="font-semibold text-white">{data.memory_count}</span>
                </div>
              </div>

              {/* Memory List */}
              {data.retrieved_memories.length === 0 ? (
                <div className="py-10 text-center space-y-2 border border-dashed border-slate-800 rounded-xl p-6">
                  <HelpCircle className="w-8 h-8 text-slate-600 mx-auto" />
                  <p className="text-sm font-medium text-slate-300">No Memories Injected into Context</p>
                  <p className="text-xs text-slate-500 max-w-sm mx-auto">
                    AUREN answered this prompt without injecting persistent long-term memories. Either no relevant memories were found, or retrieval was disabled.
                  </p>
                </div>
              ) : (
                <div className="space-y-2.5">
                  {data.retrieved_memories.map((mem) => (
                    <div
                      key={mem.id}
                      className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800/90 space-y-2 hover:border-cyan-900/50 transition"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          {renderEpistemicBadge(mem.confirmation_status)}
                          <span className="text-[11px] font-medium text-slate-400 capitalize px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                            {mem.memory_type}
                          </span>
                          <span className="text-[11px] font-medium text-slate-400 capitalize px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                            {mem.category}
                          </span>
                        </div>
                        <div className="flex items-center space-x-1.5 text-xs text-cyan-400 font-mono">
                          <span>Relevance:</span>
                          <span className="font-semibold">{Math.round(mem.score * 100)}%</span>
                        </div>
                      </div>

                      <p className="text-xs text-slate-200 leading-relaxed font-sans">{mem.content}</p>

                      <div className="flex items-center justify-between pt-1 border-t border-slate-900 text-[11px] text-slate-500">
                        <div className="flex items-center space-x-1">
                          <span>Importance:</span>
                          <div className="flex items-center">
                            {[1, 2, 3, 4, 5].map((s) => (
                              <Star
                                key={s}
                                className={`w-2.5 h-2.5 ${s <= mem.importance ? 'text-amber-400 fill-amber-400' : 'text-slate-800'}`}
                              />
                            ))}
                          </div>
                        </div>
                        <code className="text-slate-600 font-mono text-[10px]">{mem.id}</code>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="pt-2 border-t border-slate-800 flex justify-end flex-shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white text-xs font-medium transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

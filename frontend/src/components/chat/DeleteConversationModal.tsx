/**
 * Accessible Confirmation Modal for Deleting a Conversation Thread.
 */

import React, { useState } from 'react';
import { X, Trash2, AlertTriangle, Loader2, AlertCircle } from 'lucide-react';

interface DeleteConversationModalProps {
  isOpen: boolean;
  conversationTitle: string;
  onClose: () => void;
  onConfirmDelete: () => Promise<void>;
}

export const DeleteConversationModal: React.FC<DeleteConversationModalProps> = ({
  isOpen,
  conversationTitle,
  onClose,
  onConfirmDelete,
}) => {
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  if (!isOpen) return null;

  const handleDelete = async () => {
    setIsDeleting(true);
    setError(null);
    try {
      await onConfirmDelete();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete conversation');
      setIsDeleting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200"
      onKeyDown={handleKeyDown}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-dialog-title"
    >
      <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
        <div className="flex items-center justify-between pb-2 border-b border-slate-800">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-xl bg-rose-950/80 text-rose-400 border border-rose-800/40">
              <Trash2 className="h-4 w-4" />
            </div>
            <h2 id="delete-dialog-title" className="text-base font-semibold text-white">
              Delete Conversation
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <div className="flex items-center space-x-2 text-xs text-rose-400 bg-rose-950/40 border border-rose-800/50 p-3 rounded-xl">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex items-start space-x-3 p-3 bg-rose-950/20 border border-rose-900/30 rounded-xl">
          <AlertTriangle className="h-5 w-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-slate-300 space-y-1">
            <p className="font-medium text-white">
              Are you sure you want to delete this conversation?
            </p>
            <p className="text-slate-400 italic">
              "{conversationTitle}"
            </p>
            <p className="text-rose-300/80 pt-1">
              All messages in this conversation will be permanently deleted. This action cannot be undone.
            </p>
          </div>
        </div>

        <div className="flex items-center justify-end space-x-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 rounded-xl transition"
            disabled={isDeleting}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={isDeleting}
            className="flex items-center space-x-1.5 px-4 py-2 text-xs font-semibold bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white rounded-xl shadow-md shadow-rose-600/20 transition"
          >
            {isDeleting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Deleting...</span>
              </>
            ) : (
              <span>Delete Conversation</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};


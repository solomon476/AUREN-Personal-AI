/**
 * Task Creation and Editing Modal Dialog.
 */

import React, { useState, useEffect } from 'react';
import { X, Calendar, Flag, FolderKanban, Target, Tag, BellRing } from 'lucide-react';
import { Task, TaskCreateInput, TaskPriority, TaskStatus, TaskUpdateInput } from '../../api/productivity';
import { useProjects, useGoals } from '../../hooks/useProductivity';

interface TaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: TaskCreateInput | TaskUpdateInput) => Promise<void>;
  initialTask?: Task | null;
  defaultProjectId?: string | null;
  initialDueDate?: string | null;
}

export const TaskModal: React.FC<TaskModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  initialTask,
  defaultProjectId,
  initialDueDate,
}) => {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState<TaskStatus>('todo');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [projectId, setProjectId] = useState<string>('');
  const [goalId, setGoalId] = useState<string>('');
  const [dueDate, setDueDate] = useState<string>('');
  const [tagsInput, setTagsInput] = useState<string>('');
  const [reminderOption, setReminderOption] = useState<'none' | 'at_due' | 'before_15' | 'before_30' | 'before_60' | 'before_1440' | 'custom'>('none');
  const [customReminderAt, setCustomReminderAt] = useState<string>('');
  const [reminderIsAlarm, setReminderIsAlarm] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: projectsData } = useProjects({ page_size: 100 });
  const { data: goalsData } = useGoals({ page_size: 100 });

  useEffect(() => {
    if (initialTask) {
      setTitle(initialTask.title);
      setDescription(initialTask.description || '');
      setStatus(initialTask.status);
      setPriority(initialTask.priority);
      setProjectId(initialTask.project_id || '');
      setGoalId(initialTask.goal_id || '');
      setDueDate(initialTask.due_date ? initialTask.due_date.slice(0, 16) : '');
      setTagsInput(initialTask.tags?.join(', ') || '');
      setReminderOption('none');
      setCustomReminderAt('');
      setReminderIsAlarm(false);
    } else {
      setTitle('');
      setDescription('');
      setStatus('todo');
      setPriority('medium');
      setProjectId(defaultProjectId || '');
      setGoalId('');
      setDueDate(initialDueDate ? initialDueDate.slice(0, 16) : '');
      setTagsInput('');
      setReminderOption('none');
      setCustomReminderAt('');
      setReminderIsAlarm(false);
    }
    setError(null);
  }, [initialTask, defaultProjectId, initialDueDate, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError('Title is required');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    let browserTz = 'UTC';
    try {
      browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch {
      browserTz = 'UTC';
    }

    let reminder_mode: TaskCreateInput['reminder_mode'] | undefined;
    let reminder_offset_minutes: number | undefined;
    let reminder_at: string | null | undefined;

    if (reminderOption === 'at_due') {
      reminder_mode = 'at_due';
    } else if (reminderOption.startsWith('before_')) {
      reminder_mode = 'before_due';
      reminder_offset_minutes = parseInt(reminderOption.replace('before_', ''), 10);
    } else if (reminderOption === 'custom' && customReminderAt) {
      reminder_mode = 'custom';
      reminder_at = new Date(customReminderAt).toISOString();
    }

    const payload: TaskCreateInput = {
      title: title.trim(),
      description: description.trim() || null,
      status,
      priority,
      project_id: projectId || null,
      goal_id: goalId || null,
      due_date: dueDate ? new Date(dueDate).toISOString() : null,
      tags,
      ...(reminder_mode ? { reminder_mode, reminder_offset_minutes, reminder_at, reminder_is_alarm: reminderIsAlarm, reminder_timezone: browserTz } : {}),
    };

    try {
      await onSubmit(payload);
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to save task');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-lg bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="task-modal-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/50">
          <h2 id="task-modal-title" className="text-lg font-semibold text-slate-100">
            {initialTask ? 'Edit Task' : 'Create New Task'}
          </h2>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            aria-label="Close dialog"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          {error && (
            <div className="p-3 bg-red-950/50 border border-red-800/80 rounded-lg text-sm text-red-300">
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
              Title *
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="What needs to be done?"
              autoFocus
              className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Add details, notes, or acceptance criteria..."
              className="w-full px-3.5 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-sm resize-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                <Flag className="w-3.5 h-3.5 inline mr-1 text-slate-400" />
                Priority
              </label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as TaskPriority)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 text-sm focus:outline-none focus:border-indigo-500"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                Status
              </label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as TaskStatus)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 text-sm focus:outline-none focus:border-indigo-500"
              >
                <option value="todo">To Do</option>
                <option value="in_progress">In Progress</option>
                <option value="blocked">Blocked</option>
                <option value="completed">Completed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                <Calendar className="w-3.5 h-3.5 inline mr-1 text-slate-400" />
                Due Date
              </label>
              <input
                type="datetime-local"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 text-sm focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                <FolderKanban className="w-3.5 h-3.5 inline mr-1 text-slate-400" />
                Project
              </label>
              <select
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 text-sm focus:outline-none focus:border-indigo-500"
              >
                <option value="">No Project (Standalone)</option>
                {projectsData?.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                <Target className="w-3.5 h-3.5 inline mr-1 text-slate-400" />
                Strategic Goal
              </label>
              <select
                value={goalId}
                onChange={(e) => setGoalId(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 text-sm focus:outline-none focus:border-indigo-500"
              >
                <option value="">No Linked Goal</option>
                {goalsData?.items.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.title}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                <Tag className="w-3.5 h-3.5 inline mr-1 text-slate-400" />
                Tags (comma separated)
              </label>
              <input
                type="text"
                value={tagsInput}
                onChange={(e) => setTagsInput(e.target.value)}
                placeholder="dev, frontend, release"
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>
          </div>

          {/* Distinct Reminder Schedule (separate from Task Deadline) */}
          <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 flex items-center">
                <BellRing className="w-3.5 h-3.5 mr-1.5 text-emerald-400" />
                {initialTask ? 'Add Task Reminder (Optional)' : 'Reminder Alert (Distinct from Deadline)'}
              </label>
              <select
                value={reminderOption}
                onChange={(e) => setReminderOption(e.target.value as any)}
                className="px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              >
                <option value="none">{initialTask ? 'Keep existing reminders' : 'No reminder'}</option>
                <option value="at_due" disabled={!dueDate}>At due time</option>
                <option value="before_15" disabled={!dueDate}>15 min before due</option>
                <option value="before_30" disabled={!dueDate}>30 min before due</option>
                <option value="before_60" disabled={!dueDate}>1 hour before due</option>
                <option value="before_1440" disabled={!dueDate}>1 day before due</option>
                <option value="custom">Custom reminder time</option>
              </select>
            </div>

            {reminderOption === 'custom' && (
              <input
                type="datetime-local"
                value={customReminderAt}
                onChange={(e) => setCustomReminderAt(e.target.value)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100"
              />
            )}

            {reminderOption !== 'none' && (
              <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={reminderIsAlarm}
                  onChange={(e) => setReminderIsAlarm(e.target.checked)}
                  className="accent-amber-500"
                />
                <span>Alarm-style prominent alert + sound</span>
              </label>
            )}
          </div>

          {/* Footer Actions */}
          <div className="pt-4 flex items-center justify-end space-x-3 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-5 py-2 text-sm font-medium bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors shadow-lg shadow-indigo-600/20 disabled:opacity-50"
            >
              {isSubmitting ? 'Saving...' : initialTask ? 'Update Task' : 'Create Task'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};


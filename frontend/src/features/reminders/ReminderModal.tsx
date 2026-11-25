/**
 * Reminder Creation, Editing, and Rescheduling Modal Dialog.
 */

import React, { useEffect, useState } from 'react';
import { AlarmClock, Bell, Calendar, Clock, Flag, FolderKanban, Repeat, Volume2, X } from 'lucide-react';
import {
  RecurrenceFrequency,
  RecurrenceRule,
  Reminder,
  ReminderCreateInput,
  ReminderPriority,
  ReminderUpdateInput,
} from '../../api/reminders';
import { useTasks } from '../../hooks/useProductivity';
import { useUserProfile } from '../../hooks/useSettings';
import { useAuth } from '../../context/AuthContext';
import { playAlertSound } from '../../lib/soundAlert';

interface ReminderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: ReminderCreateInput | ReminderUpdateInput) => Promise<void>;
  initialReminder?: Reminder | null;
  defaultTaskId?: string | null;
}

const COMMON_TIMEZONES = [
  'UTC',
  'Africa/Nairobi',
  'Africa/Lagos',
  'Africa/Johannesburg',
  'Africa/Cairo',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
];

const WEEKDAYS = [
  { val: 0, label: 'Mon' },
  { val: 1, label: 'Tue' },
  { val: 2, label: 'Wed' },
  { val: 3, label: 'Thu' },
  { val: 4, label: 'Fri' },
  { val: 5, label: 'Sat' },
  { val: 6, label: 'Sun' },
];

function toLocalDateTimeInput(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    const offset = d.getTimezoneOffset();
    const local = new Date(d.getTime() - offset * 60000);
    return local.toISOString().slice(0, 16);
  } catch {
    return '';
  }
}

export const ReminderModal: React.FC<ReminderModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  initialReminder,
  defaultTaskId,
}) => {
  const { user } = useAuth();
  const { data: profile } = useUserProfile(user?.id);
  const { data: tasksData } = useTasks({ page_size: 100 }, user?.id);

  const detectedTz = (() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch {
      return 'UTC';
    }
  })();

  const defaultUserTz = String(profile?.preferences?.timezone || detectedTz || 'UTC');

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [triggerLocal, setTriggerLocal] = useState('');
  const [timezone, setTimezone] = useState(defaultUserTz);
  const [priority, setPriority] = useState<ReminderPriority>('normal');
  const [isAlarm, setIsAlarm] = useState(false);
  const [soundKey, setSoundKey] = useState('chime');
  const [taskId, setTaskId] = useState('');
  const [recurrenceFreq, setRecurrenceFreq] = useState<'none' | RecurrenceFrequency>('none');
  const [daysOfWeek, setDaysOfWeek] = useState<number[]>([]);
  const [dayOfMonth, setDayOfMonth] = useState<number>(1);
  const [intervalCount, setIntervalCount] = useState<number>(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    if (initialReminder) {
      setTitle(initialReminder.title);
      setDescription(initialReminder.description || '');
      setTriggerLocal(toLocalDateTimeInput(initialReminder.trigger_at));
      setTimezone(initialReminder.timezone || defaultUserTz);
      setPriority(initialReminder.priority);
      setIsAlarm(initialReminder.is_alarm);
      setSoundKey(initialReminder.sound_key || String(profile?.preferences?.reminder_sound || 'chime'));
      setTaskId(initialReminder.task_id || '');
      if (initialReminder.recurrence_rule) {
        setRecurrenceFreq(initialReminder.recurrence_rule.frequency);
        setDaysOfWeek(initialReminder.recurrence_rule.days_of_week || []);
        setDayOfMonth(initialReminder.recurrence_rule.day_of_month || 1);
        setIntervalCount(initialReminder.recurrence_rule.interval || 1);
      } else {
        setRecurrenceFreq('none');
        setDaysOfWeek([]);
      }
    } else {
      const oneHourFromNow = new Date(Date.now() + 60 * 60 * 1000);
      setTitle('');
      setDescription('');
      setTriggerLocal(toLocalDateTimeInput(oneHourFromNow.toISOString()));
      setTimezone(defaultUserTz);
      setPriority('normal');
      setIsAlarm(profile?.preferences?.default_reminder_behavior === 'alarm');
      setSoundKey(String(profile?.preferences?.reminder_sound || 'chime'));
      setTaskId(defaultTaskId || '');
      setRecurrenceFreq('none');
      setDaysOfWeek([]);
      setDayOfMonth(1);
      setIntervalCount(1);
    }
    setError(null);
  }, [initialReminder, defaultTaskId, isOpen, defaultUserTz, profile?.preferences]);

  if (!isOpen) return null;

  const toggleWeekday = (wd: number) => {
    setDaysOfWeek((prev) => (prev.includes(wd) ? prev.filter((d) => d !== wd) : [...prev, wd].sort()));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError('Reminder title is required.');
      return;
    }
    if (!triggerLocal) {
      setError('Scheduled date and time are required.');
      return;
    }

    const triggerIso = new Date(triggerLocal).toISOString();
    const localTimeHhMm = triggerLocal.slice(11, 16) || '09:00';

    let recurrenceRule: RecurrenceRule | null = null;
    let recurrenceText: string | null = null;

    if (recurrenceFreq !== 'none') {
      recurrenceRule = {
        frequency: recurrenceFreq,
        interval: Math.max(1, intervalCount),
        time_of_day: localTimeHhMm,
        days_of_week: recurrenceFreq === 'weekly' ? (daysOfWeek.length > 0 ? daysOfWeek : [new Date(triggerLocal).getDay() === 0 ? 6 : new Date(triggerLocal).getDay() - 1]) : undefined,
        day_of_month: recurrenceFreq === 'monthly' ? dayOfMonth : undefined,
      };
      if (recurrenceFreq === 'daily') recurrenceText = `Daily at ${localTimeHhMm}`;
      else if (recurrenceFreq === 'weekdays') recurrenceText = `Weekdays at ${localTimeHhMm}`;
      else if (recurrenceFreq === 'weekly') {
        const names = (recurrenceRule.days_of_week || []).map((d) => WEEKDAYS.find((w) => w.val === d)?.label || '');
        recurrenceText = `Every ${names.join(', ')} at ${localTimeHhMm}`;
      } else if (recurrenceFreq === 'monthly') {
        recurrenceText = `Monthly on day ${dayOfMonth} at ${localTimeHhMm}`;
      } else {
        recurrenceText = `Every ${intervalCount} ${recurrenceFreq.replace('interval_', '')}`;
      }
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const payload: ReminderCreateInput | ReminderUpdateInput = {
        title: title.trim(),
        description: description.trim() || null,
        trigger_at: triggerIso,
        timezone,
        priority: isAlarm ? 'alarm' : priority,
        is_alarm: isAlarm,
        sound_key: soundKey,
        task_id: taskId || null,
        recurrence_rule: recurrenceRule,
        recurrence_text: recurrenceText,
        ...(initialReminder ? { clear_recurrence: recurrenceFreq === 'none' } : {}),
      };
      await onSubmit(payload);
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to save reminder.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const tzOptions = Array.from(new Set([timezone, defaultUserTz, detectedTz, ...COMMON_TIMEZONES].filter(Boolean)));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-sm animate-in fade-in duration-150">
      <div
        className="w-full max-w-lg bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reminder-modal-title"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center space-x-2">
            {isAlarm ? <AlarmClock className="w-5 h-5 text-amber-600" /> : <Bell className="w-5 h-5 text-emerald-600" />}
            <h2 id="reminder-modal-title" className="text-base font-bold text-slate-900">
              {initialReminder ? 'Edit / Reschedule Reminder' : 'Schedule Reminder'}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/70 transition cursor-pointer"
            aria-label="Close reminder dialog"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-5 space-y-4">
          {error && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 font-medium">
              {error}
            </div>
          )}

          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Reminder Title *
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Continue working on AUREN, Review finances..."
              autoFocus
              className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
            />
          </div>

          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Notes / Details
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Optional context or instructions..."
              className="w-full px-3.5 py-2 bg-white border border-slate-300 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-emerald-500 resize-none"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                <Calendar className="w-3.5 h-3.5 inline mr-1 text-emerald-600" />
                Date &amp; Time *
              </label>
              <input
                type="datetime-local"
                value={triggerLocal}
                onChange={(e) => setTriggerLocal(e.target.value)}
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl text-xs text-slate-900 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                <Clock className="w-3.5 h-3.5 inline mr-1 text-slate-500" />
                Timezone
              </label>
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl text-xs text-slate-800 focus:outline-none focus:border-emerald-500"
              >
                {tzOptions.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Recurrence */}
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-bold uppercase tracking-wider text-slate-600 flex items-center">
                <Repeat className="w-3.5 h-3.5 mr-1.5 text-emerald-600" />
                Recurrence
              </label>
              <select
                value={recurrenceFreq}
                onChange={(e) => setRecurrenceFreq(e.target.value as any)}
                className="px-2.5 py-1.5 bg-white border border-slate-300 rounded-lg text-xs text-slate-800"
              >
                <option value="none">One-time</option>
                <option value="daily">Every day</option>
                <option value="weekdays">Every weekday (Mon–Fri)</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="interval_hours">Every N hours</option>
                <option value="interval_days">Every N days</option>
              </select>
            </div>

            {recurrenceFreq === 'weekly' && (
              <div className="flex flex-wrap gap-1.5">
                {WEEKDAYS.map((wd) => (
                  <button
                    key={wd.val}
                    type="button"
                    onClick={() => toggleWeekday(wd.val)}
                    className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold border cursor-pointer transition ${
                      daysOfWeek.includes(wd.val)
                        ? 'bg-emerald-600 text-white border-emerald-600'
                        : 'bg-white text-slate-700 border-slate-200'
                    }`}
                  >
                    {wd.label}
                  </button>
                ))}
              </div>
            )}

            {recurrenceFreq === 'monthly' && (
              <div className="flex items-center space-x-2 text-xs text-slate-700">
                <span>Day of month:</span>
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={dayOfMonth}
                  onChange={(e) => setDayOfMonth(Math.min(31, Math.max(1, Number(e.target.value) || 1)))}
                  className="w-16 px-2 py-1 bg-white border border-slate-300 rounded-lg text-xs"
                />
              </div>
            )}

            {(recurrenceFreq === 'interval_hours' || recurrenceFreq === 'interval_days') && (
              <div className="flex items-center space-x-2 text-xs text-slate-700">
                <span>Repeat every</span>
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={intervalCount}
                  onChange={(e) => setIntervalCount(Math.max(1, Number(e.target.value) || 1))}
                  className="w-16 px-2 py-1 bg-white border border-slate-300 rounded-lg text-xs"
                />
                <span>{recurrenceFreq === 'interval_hours' ? 'hour(s)' : 'day(s)'}</span>
              </div>
            )}
          </div>

          {/* Alarm Style, Sound & Priority */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                <Flag className="w-3.5 h-3.5 inline mr-1" />
                Priority
              </label>
              <select
                value={priority}
                onChange={(e) => {
                  const p = e.target.value as ReminderPriority;
                  setPriority(p);
                  if (p === 'alarm') setIsAlarm(true);
                }}
                className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl text-xs text-slate-800"
              >
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="alarm">Urgent Alarm</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                <Volume2 className="w-3.5 h-3.5 inline mr-1" />
                Alert Sound
              </label>
              <div className="flex items-center space-x-1.5">
                <select
                  value={soundKey}
                  onChange={(e) => setSoundKey(e.target.value)}
                  className="flex-1 px-3 py-2 bg-white border border-slate-300 rounded-xl text-xs text-slate-800"
                >
                  <option value="chime">Executive Chime</option>
                  <option value="bell">Crystal Bell</option>
                  <option value="pulse">Alarm Pulse</option>
                  <option value="gentle">Gentle Tone</option>
                  <option value="silent">Silent (Visual only)</option>
                </select>
                <button
                  type="button"
                  onClick={() => playAlertSound(soundKey, isAlarm)}
                  className="px-2.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-xs font-semibold text-slate-700 cursor-pointer"
                  title="Test sound"
                >
                  Test
                </button>
              </div>
            </div>
          </div>

          <label className="flex items-center justify-between p-3 rounded-xl bg-amber-50/60 border border-amber-200 cursor-pointer">
            <div>
              <span className="text-xs font-bold text-slate-900 block">Alarm-Style Persistent Alert</span>
              <span className="text-[11px] text-slate-600">
                Displays a full-attention modal popup &amp; repeating tone until dismissed or snoozed.
              </span>
            </div>
            <input
              type="checkbox"
              checked={isAlarm}
              onChange={(e) => setIsAlarm(e.target.checked)}
              className="w-4 h-4 accent-amber-600"
            />
          </label>

          {/* Optional Task Link */}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              <FolderKanban className="w-3.5 h-3.5 inline mr-1" />
              Link to Task (Optional)
            </label>
            <select
              value={taskId}
              onChange={(e) => setTaskId(e.target.value)}
              className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl text-xs text-slate-800"
            >
              <option value="">Standalone Reminder</option>
              {tasksData?.items.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title}
                </option>
              ))}
            </select>
          </div>

          <div className="pt-3 flex items-center justify-end space-x-2.5 border-t border-slate-200">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-5 py-2.5 text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl shadow-sm transition disabled:opacity-50 cursor-pointer"
            >
              {isSubmitting ? 'Saving...' : initialReminder ? 'Save Changes' : 'Schedule Reminder'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};


/**
 * Alarm-Style Modal & Floating In-App Notification Popup Overlay.
 * Handles both urgent alarm-style full attention prompts and clean reminder toasts
 * with Complete, Snooze, Open, Mute Sound, and Dismiss actions.
 */

import React from 'react';
import {
  AlarmClock,
  BellRing,
  CheckCircle2,
  Clock,
  ExternalLink,
  VolumeX,
  X,
} from 'lucide-react';
import { useNotificationCenter } from '../../context/NotificationContext';
import { stopAlertSound } from '../../lib/soundAlert';

export const AlarmNotificationOverlay: React.FC = () => {
  const {
    activePopup,
    activeAlarm,
    dismissActiveAlert,
    completeFromNotification,
    snoozeFromNotification,
    openFromNotification,
  } = useNotificationCenter();

  return (
    <>
      {/* 1. Prominent Alarm-Style Alert Dialog */}
      {activeAlarm && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-md animate-in fade-in duration-200"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="auren-alarm-title"
        >
          <div className="w-full max-w-md rounded-3xl bg-white border-2 border-amber-400 shadow-2xl overflow-hidden">
            <div className="bg-gradient-to-r from-amber-500 via-orange-500 to-rose-500 px-6 py-4 flex items-center justify-between text-white">
              <div className="flex items-center space-x-2.5">
                <div className="p-2 rounded-xl bg-white/20 animate-bounce">
                  <AlarmClock className="w-5 h-5" />
                </div>
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-widest block opacity-90">
                    AUREN Alarm
                  </span>
                  <span className="text-xs font-semibold">Scheduled Alert Due Now</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => stopAlertSound()}
                className="p-2 rounded-xl bg-white/15 hover:bg-white/25 transition touch-target flex items-center justify-center cursor-pointer"
                title="Mute sound"
                aria-label="Mute alarm sound"
              >
                <VolumeX className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              <div>
                <h2 id="auren-alarm-title" className="text-lg font-extrabold text-slate-900 leading-snug">
                  {activeAlarm.title}
                </h2>
                {activeAlarm.body && (
                  <p className="text-xs text-slate-600 mt-1.5 leading-relaxed">{activeAlarm.body}</p>
                )}
                {activeAlarm.metadata?.quiet_hours_suppressed && (
                  <span className="inline-block mt-2 text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                    Quiet Hours Active (Sound Muted)
                  </span>
                )}
              </div>

              {/* Snooze Options */}
              <div className="space-y-1.5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block">
                  Snooze Alarm
                </span>
                <div className="grid grid-cols-3 gap-2">
                  {[5, 10, 30].map((mins) => (
                    <button
                      key={mins}
                      type="button"
                      onClick={() => snoozeFromNotification(activeAlarm, mins)}
                      className="py-2.5 px-3 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-xs font-bold text-slate-800 transition flex items-center justify-center space-x-1 touch-target cursor-pointer"
                    >
                      <Clock className="w-3.5 h-3.5 text-amber-600" />
                      <span>{mins}m</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Primary Actions */}
              <div className="flex flex-col sm:flex-row gap-2.5 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => completeFromNotification(activeAlarm)}
                  className="flex-1 py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-md shadow-emerald-600/20 flex items-center justify-center space-x-2 touch-target cursor-pointer"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Complete</span>
                </button>
                <button
                  type="button"
                  onClick={() => openFromNotification(activeAlarm)}
                  className="py-3 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold flex items-center justify-center space-x-1.5 touch-target cursor-pointer"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Open</span>
                </button>
                <button
                  type="button"
                  onClick={() => dismissActiveAlert(activeAlarm.id)}
                  className="py-3 px-4 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold touch-target cursor-pointer"
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 2. Floating Standard In-App Reminder Popup */}
      {activePopup && !activeAlarm && (
        <div
          className="fixed top-4 right-4 left-4 sm:left-auto sm:w-96 z-[60] rounded-2xl bg-white border-2 border-emerald-500 shadow-2xl p-4 space-y-3 animate-in slide-in-from-top-4 duration-200"
          role="alert"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-start space-x-2.5 min-w-0">
              <div className="p-2 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-600 flex-shrink-0">
                <BellRing className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 block">
                  {activePopup.metadata?.missed_window ? 'Missed Reminder' : 'Reminder Due'}
                </span>
                <h3 className="text-xs sm:text-sm font-bold text-slate-900 truncate">
                  {activePopup.title}
                </h3>
                {activePopup.body && (
                  <p className="text-[11px] text-slate-600 line-clamp-2 mt-0.5">{activePopup.body}</p>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => dismissActiveAlert(activePopup.id)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer"
              aria-label="Dismiss notification"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={() => completeFromNotification(activePopup)}
              className="flex-1 py-2 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center justify-center space-x-1.5 transition cursor-pointer"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Complete</span>
            </button>
            <button
              type="button"
              onClick={() => snoozeFromNotification(activePopup)}
              className="py-2 px-3 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-800 text-xs font-semibold flex items-center space-x-1 transition cursor-pointer"
            >
              <Clock className="w-3.5 h-3.5 text-amber-600" />
              <span>Snooze</span>
            </button>
            <button
              type="button"
              onClick={() => openFromNotification(activePopup)}
              className="py-2 px-3 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold flex items-center space-x-1 transition cursor-pointer"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Open</span>
            </button>
          </div>
        </div>
      )}
    </>
  );
};


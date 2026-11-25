/**
 * Notification Bell & In-App Notification Center Popover.
 * Displays real unread badge counts, unread vs notification history tabs,
 * inline Complete / Snooze / Open actions, and non-intrusive Push Notification onboarding.
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  AlarmClock,
  Bell,
  BellRing,
  CheckCheck,
  CheckCircle2,
  Clock,
  ExternalLink,
  Smartphone,
  X,
} from 'lucide-react';
import { Link } from '@tanstack/react-router';
import { useNotificationCenter } from '../../context/NotificationContext';
import {
  enableDeviceWebPush,
  getBrowserNotificationPermission,
  hasUserDeclinedPush,
  isWebPushSupported,
  markUserDeclinedPush,
} from '../../lib/pushNotifications';
import { useUpdateUserProfile } from '../../hooks/useSettings';
import { useAuth } from '../../context/AuthContext';

export const NotificationBell: React.FC = () => {
  const { user } = useAuth();
  const {
    notifications,
    unreadCount,
    markAllRead,
    completeFromNotification,
    snoozeFromNotification,
    openFromNotification,
    dismissActiveAlert,
  } = useNotificationCenter();

  const updateProfile = useUpdateUserProfile(user?.id);
  const [isOpen, setIsOpen] = useState(false);
  const [tab, setTab] = useState<'unread' | 'history'>('unread');
  const [pushMessage, setPushMessage] = useState<string | null>(null);
  const [showOnboarding, setShowOnboarding] = useState<boolean>(() => {
    return (
      isWebPushSupported() &&
      getBrowserNotificationPermission() === 'default' &&
      !hasUserDeclinedPush()
    );
  });

  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  if (!user) return null;

  const filtered =
    tab === 'unread'
      ? notifications.filter((n) => n.status === 'unread')
      : notifications;

  const handleEnablePush = async () => {
    setPushMessage(null);
    const res = await enableDeviceWebPush();
    if (res.success) {
      setShowOnboarding(false);
      setPushMessage('Push alerts activated for this device.');
      updateProfile.mutate({ preferences: { browser_push_enabled: true } });
    } else {
      setShowOnboarding(false);
      setPushMessage(res.error || 'Could not enable push notifications.');
    }
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200 touch-target flex items-center justify-center transition cursor-pointer"
        aria-label="Open Notification Center"
        title="Notifications & Reminders"
      >
        <Bell className={`h-4 w-4 ${unreadCount > 0 ? 'text-emerald-600' : ''}`} />
        {unreadCount > 0 && (
          <span
            data-testid="notification-unread-badge"
            className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-emerald-600 text-white text-[10px] font-bold flex items-center justify-center shadow-sm ring-2 ring-white font-mono"
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          className="fixed inset-x-3 top-14 sm:inset-x-auto sm:absolute sm:right-0 sm:top-full sm:mt-2 sm:w-96 rounded-2xl bg-white border border-slate-200 shadow-2xl z-50 overflow-hidden flex flex-col max-h-[80vh]"
          role="dialog"
          aria-label="Notification Center"
        >
          {/* Header */}
          <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between bg-slate-50">
            <div className="flex items-center space-x-2">
              <BellRing className="w-4 h-4 text-emerald-600" />
              <span className="text-xs font-bold text-slate-900">Notification Center</span>
              {unreadCount > 0 && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-emerald-100 text-emerald-800">
                  {unreadCount} new
                </span>
              )}
            </div>
            <div className="flex items-center space-x-1">
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={() => markAllRead()}
                  className="text-[11px] font-semibold text-emerald-700 hover:text-emerald-800 px-2 py-1 rounded-lg hover:bg-emerald-50 flex items-center space-x-1 cursor-pointer"
                >
                  <CheckCheck className="w-3.5 h-3.5" />
                  <span>Mark all read</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1 text-slate-400 hover:text-slate-700 rounded-lg cursor-pointer"
                aria-label="Close Notification Center"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Unobtrusive One-Time Push Onboarding */}
          {showOnboarding && (
            <div className="p-3 bg-emerald-50/80 border-b border-emerald-200 flex items-center justify-between gap-2">
              <div className="flex items-start space-x-2">
                <Smartphone className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-[11px] font-bold text-emerald-950">Enable Background Push Alerts</p>
                  <p className="text-[10px] text-emerald-800 leading-snug">
                    Receive due reminders even when the AUREN tab is closed.
                  </p>
                </div>
              </div>
              <div className="flex items-center space-x-1.5 flex-shrink-0">
                <button
                  type="button"
                  onClick={handleEnablePush}
                  className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-semibold cursor-pointer"
                >
                  Enable
                </button>
                <button
                  type="button"
                  onClick={() => {
                    markUserDeclinedPush();
                    setShowOnboarding(false);
                  }}
                  className="p-1 text-emerald-700 hover:bg-emerald-100 rounded-lg cursor-pointer"
                  aria-label="No thanks"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}

          {pushMessage && (
            <div className="px-3.5 py-2 bg-slate-100 border-b border-slate-200 text-[11px] text-slate-700">
              {pushMessage}
            </div>
          )}

          {/* Tabs */}
          <div className="flex border-b border-slate-100 px-3 pt-2 gap-2">
            <button
              type="button"
              onClick={() => setTab('unread')}
              className={`pb-2 px-2 text-xs font-semibold border-b-2 transition cursor-pointer ${
                tab === 'unread'
                  ? 'border-emerald-600 text-emerald-700'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              Unread ({unreadCount})
            </button>
            <button
              type="button"
              onClick={() => setTab('history')}
              className={`pb-2 px-2 text-xs font-semibold border-b-2 transition cursor-pointer ${
                tab === 'history'
                  ? 'border-emerald-600 text-emerald-700'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              History ({notifications.length})
            </button>
          </div>

          {/* Notification Items */}
          <div className="flex-1 overflow-y-auto divide-y divide-slate-100 scrollbar-thin">
            {filtered.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">
                <Bell className="w-6 h-6 mx-auto text-slate-300 mb-2" />
                {tab === 'unread' ? 'You are all caught up!' : 'No notification history yet.'}
              </div>
            ) : (
              filtered.map((item) => (
                <div
                  key={item.id}
                  className={`p-3.5 space-y-2 transition ${
                    item.status === 'unread' ? 'bg-emerald-50/30' : 'bg-white'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start space-x-2 min-w-0">
                      {item.is_alarm ? (
                        <AlarmClock className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                      ) : (
                        <BellRing className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" />
                      )}
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-slate-900 truncate">{item.title}</p>
                        {item.body && (
                          <p className="text-[11px] text-slate-600 line-clamp-2 mt-0.5">{item.body}</p>
                        )}
                        <span className="text-[10px] text-slate-400 font-mono block mt-1">
                          {new Date(item.triggered_at).toLocaleString()}
                          {item.metadata?.quiet_hours_suppressed ? ' • Quiet Hours' : ''}
                        </span>
                      </div>
                    </div>
                    {item.status === 'unread' && (
                      <button
                        type="button"
                        onClick={() => dismissActiveAlert(item.id)}
                        className="p-1 text-slate-400 hover:text-slate-700 rounded cursor-pointer"
                        title="Dismiss"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 pl-6">
                    {item.reminder_id && (
                      <>
                        <button
                          type="button"
                          onClick={() => completeFromNotification(item)}
                          className="px-2 py-1 rounded-lg bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 text-[11px] font-semibold text-emerald-800 flex items-center space-x-1 cursor-pointer"
                        >
                          <CheckCircle2 className="w-3 h-3" />
                          <span>Complete</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => snoozeFromNotification(item)}
                          className="px-2 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 border border-slate-200 text-[11px] font-semibold text-slate-700 flex items-center space-x-1 cursor-pointer"
                        >
                          <Clock className="w-3 h-3" />
                          <span>Snooze</span>
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setIsOpen(false);
                        openFromNotification(item);
                      }}
                      className="px-2 py-1 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-[11px] font-semibold text-slate-700 flex items-center space-x-1 cursor-pointer"
                    >
                      <ExternalLink className="w-3 h-3" />
                      <span>Open</span>
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Footer Link to Full Reminder Center */}
          <div className="p-2.5 border-t border-slate-100 bg-slate-50">
            <Link
              to="/reminders"
              onClick={() => setIsOpen(false)}
              className="w-full py-2 rounded-xl bg-white hover:bg-slate-100 border border-slate-200 text-xs font-bold text-slate-800 flex items-center justify-center transition"
            >
              Open Reminder Center
            </Link>
          </div>
        </div>
      )}
    </div>
  );
};


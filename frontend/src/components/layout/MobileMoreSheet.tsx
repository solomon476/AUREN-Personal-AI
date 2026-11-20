/**
 * Mobile Secondary Navigation Sheet (Bottom Sheet Drawer).
 * Provides accessible, one-handed touch access to all secondary AUREN surfaces:
 * Memory, Projects, Goals, Productivity, Reflection, Search, Settings, and System.
 * Elevated with AUREN Obsidian & Champagne Design System.
 */

import React from 'react';
import {
  X,
  Brain,
  FolderKanban,
  Target,
  LayoutDashboard,
  Sparkles,
  Search,
  Settings,
  Activity,
  LogOut,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';
import { Link } from '@tanstack/react-router';
import { useAuth } from '../../context/AuthContext';

interface MobileMoreSheetProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenAuth: (mode: 'signin' | 'signup') => void;
}

export const MobileMoreSheet: React.FC<MobileMoreSheetProps> = ({
  isOpen,
  onClose,
  onOpenAuth,
}) => {
  const { user, signOut } = useAuth();

  if (!isOpen) return null;

  const secondaryNavItems = [
    {
      to: '/memories',
      label: 'Long-term Memory',
      desc: 'Epistemic knowledge base',
      icon: Brain,
      color: 'text-indigo-400 bg-indigo-950/60 border-indigo-800/40',
    },
    {
      to: '/projects',
      label: 'Projects',
      desc: 'Workspaces & initiatives',
      icon: FolderKanban,
      color: 'text-emerald-400 bg-emerald-950/60 border-emerald-800/40',
    },
    {
      to: '/goals',
      label: 'Goals & Milestones',
      desc: 'Strategic horizon targets',
      icon: Target,
      color: 'text-purple-400 bg-purple-950/60 border-purple-800/40',
    },
    {
      to: '/productivity',
      label: 'Productivity Overview',
      desc: 'Execution KPIs & velocity',
      icon: LayoutDashboard,
      color: 'text-sky-400 bg-sky-950/60 border-sky-800/40',
    },
    {
      to: '/reflection',
      label: 'Reflective Insights',
      desc: 'AI contradiction audit',
      icon: Sparkles,
      color: 'text-champagne-300 bg-champagne-950/60 border-champagne-800/40',
    },
    {
      to: '/search',
      label: 'Omnisearch',
      desc: 'Cross-entity global search',
      icon: Search,
      color: 'text-slate-300 bg-slate-900 border-slate-800',
    },
    {
      to: '/settings',
      label: 'Settings & Preferences',
      desc: 'Model, theme & GDPR export',
      icon: Settings,
      color: 'text-slate-300 bg-slate-900 border-slate-800',
    },
    {
      to: '/system',
      label: 'System & Database',
      desc: 'API health & PostgreSQL RLS',
      icon: Activity,
      color: 'text-teal-400 bg-teal-950/60 border-teal-800/40',
    },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end md:hidden animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-label="More Navigation Surfaces"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-950/80 backdrop-blur-md"
        onClick={onClose}
      />

      {/* Sheet Content Container */}
      <div className="relative w-full bg-slate-950/95 border-t border-slate-800/80 rounded-t-3xl shadow-modal-elevation z-10 flex flex-col max-h-[85dvh] overflow-hidden">
        {/* Pull Handle & Header */}
        <div className="pt-3 pb-3 px-6 flex flex-col items-center border-b border-slate-800/80 bg-slate-900/40">
          <div className="w-10 h-1 bg-slate-700/80 rounded-full mb-3" />
          <div className="w-full flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-white tracking-tight">AUREN Navigation Hub</h2>
              <p className="text-[11px] text-slate-400">All command surfaces &amp; personal controls</p>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 touch-target flex items-center justify-center transition"
              aria-label="Close more navigation"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Surfaces List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2 scrollbar-thin">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {secondaryNavItems.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  onClick={onClose}
                  className="flex items-center justify-between p-3.5 rounded-2xl bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.07] hover:border-white/[0.12] transition-all group touch-target"
                >
                  <div className="flex items-center space-x-3 min-w-0">
                    <div className={`p-2.5 rounded-xl border flex-shrink-0 ${item.color}`}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <span className="text-xs font-semibold text-slate-200 group-hover:text-white block truncate tracking-tight">
                        {item.label}
                      </span>
                      <span className="text-[10px] text-slate-500 block truncate">
                        {item.desc}
                      </span>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-slate-300 flex-shrink-0 transition-transform group-hover:translate-x-0.5" />
                </Link>
              );
            })}
          </div>

          {/* User Account / Session Section */}
          <div className="mt-4 pt-3 border-t border-slate-800/80">
            {user ? (
              <div className="p-3.5 rounded-2xl bg-white/[0.03] border border-white/[0.07] flex items-center justify-between">
                <div className="flex items-center space-x-3 min-w-0">
                  <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-champagne-300 p-0.5 flex items-center justify-center text-white flex-shrink-0 shadow-sm">
                    <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center font-bold text-xs text-champagne-300">
                      {user.email ? user.email.charAt(0).toUpperCase() : 'U'}
                    </div>
                  </div>
                  <div className="min-w-0">
                    <span className="text-xs font-semibold text-slate-200 block truncate">
                      {user.email}
                    </span>
                    <span className="text-[10px] text-emerald-400 flex items-center space-x-1">
                      <ShieldCheck className="w-3 h-3" />
                      <span>Authenticated Session</span>
                    </span>
                  </div>
                </div>
                <button
                  onClick={async () => {
                    await signOut();
                    onClose();
                  }}
                  className="p-2 rounded-xl text-slate-400 hover:text-rose-400 hover:bg-rose-950/30 transition flex items-center justify-center touch-target"
                  title="Sign Out"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2 pt-1">
                <button
                  onClick={() => onOpenAuth('signin')}
                  className="w-full py-2.5 px-3 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs font-medium text-slate-300 hover:text-white transition touch-target flex items-center justify-center"
                >
                  Sign In
                </button>
                <button
                  onClick={() => onOpenAuth('signup')}
                  className="w-full py-2.5 px-3 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition touch-target flex items-center justify-center"
                >
                  Create Account
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

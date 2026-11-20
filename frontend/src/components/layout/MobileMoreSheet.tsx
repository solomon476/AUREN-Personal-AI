/**
 * Mobile Secondary Navigation Sheet (Bottom Sheet Drawer).
 * Provides accessible, one-handed touch access to all secondary AUREN surfaces:
 * Memory, Projects, Goals, Productivity, Reflection, Search, Settings, and System.
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
  User,
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
      color: 'text-amber-400 bg-amber-950/60 border-amber-800/40',
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
      <div className="relative w-full bg-slate-950 border-t border-slate-800/80 rounded-t-3xl shadow-2xl z-10 flex flex-col max-h-[85dvh] overflow-hidden">
        {/* Pull Handle & Header */}
        <div className="pt-3 pb-2 px-6 flex flex-col items-center border-b border-slate-800/80 bg-slate-900/40">
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
                  className="flex items-center space-x-3 p-3 rounded-2xl bg-slate-900/60 border border-slate-800/80 hover:bg-slate-900 hover:border-slate-700 transition active:scale-[0.98] touch-target"
                >
                  <div className={`p-2.5 rounded-xl border ${item.color} flex-shrink-0`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-xs font-semibold text-slate-200 block truncate">
                      {item.label}
                    </span>
                    <span className="text-[10px] text-slate-400 block truncate">
                      {item.desc}
                    </span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-600 flex-shrink-0" />
                </Link>
              );
            })}
          </div>

          {/* Account Footer Inside Sheet */}
          <div className="mt-4 pt-4 border-t border-slate-800/80">
            {user ? (
              <div className="p-3.5 rounded-2xl bg-slate-900/40 border border-slate-800/80 flex items-center justify-between">
                <div className="flex items-center space-x-3 min-w-0">
                  <div className="w-8 h-8 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center flex-shrink-0">
                    <User className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <span className="text-xs font-medium text-slate-200 block truncate">
                      {user.email}
                    </span>
                    <span className="text-[10px] text-emerald-400 flex items-center font-mono">
                      <ShieldCheck className="w-3 h-3 mr-1" />
                      RLS Protected
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => {
                    signOut();
                    onClose();
                  }}
                  className="p-2 rounded-xl text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition"
                  title="Sign Out"
                  aria-label="Sign Out"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => {
                  onOpenAuth('signin');
                  onClose();
                }}
                className="w-full flex items-center justify-center space-x-2 py-3 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-500 text-white font-semibold text-xs shadow-md shadow-indigo-600/20 transition touch-target"
              >
                <span>Sign In to AUREN</span>
              </button>
            )}
          </div>
        </div>

        {/* Bottom Safe Area Spacer */}
        <div className="h-[env(safe-area-inset-bottom,0.75rem)]" />
      </div>
    </div>
  );
};


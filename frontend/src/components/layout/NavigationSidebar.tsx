/**
 * Persistent Application Navigation Sidebar.
 * Displays the six core AUREN product areas:
 * 1. Home — Personal Command Center (/home)
 * 2. Assistant — Central AI Intelligence (/chat)
 * 3. Memory — Personal Knowledge & Context (/memories)
 * 4. Life Management — Tasks, Projects, Goals, Productivity
 * 5. Reflection — Private Journal & Reflective Intelligence
 * 6. Settings — Privacy, Preferences & Control
 * Elevated with High-Contrast White, Slate, Emerald, and Gold Design System.
 */

import React from 'react';
import { 
  Bot, 
  Home,
  MessageSquare, 
  LayoutDashboard, 
  Brain, 
  CheckSquare, 
  FolderKanban, 
  Target, 
  BookOpen, 
  Settings,
  LogIn,
  Activity,
  Search,
  Sparkles,
  Download,
  MapPin,
} from 'lucide-react';
import { Link, useRouterState } from '@tanstack/react-router';
import { useAuth } from '../../context/AuthContext';
import { UserProfileMenu } from '../auth/UserProfileMenu';

interface NavigationSidebarProps {
  onNavigate?: () => void;
  onOpenAuth?: (mode: 'signin' | 'signup') => void;
  onOpenInstall?: () => void;
  isInstalled?: boolean;
}

export const NavigationSidebar: React.FC<NavigationSidebarProps> = ({
  onNavigate,
  onOpenAuth,
  onOpenInstall,
  isInstalled = false,
}) => {
  const { user, isLoading } = useAuth();
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  const coreNavItems = [
    {
      to: '/home',
      label: 'Command Center',
      icon: Home,
      badge: 'Home',
      badgeColor: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    },
    {
      to: '/chat',
      label: 'AI Assistant',
      icon: MessageSquare,
      badge: 'Active',
      badgeColor: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    },
    {
      to: '/memories',
      label: 'Long-term Memory',
      icon: Brain,
      badge: null,
      badgeColor: '',
    },
  ];

  const lifeManagementItems = [
    {
      to: '/tasks',
      label: 'Tasks & Timetable',
      icon: CheckSquare,
      badge: null,
      badgeColor: '',
    },
    {
      to: '/projects',
      label: 'Projects',
      icon: FolderKanban,
      badge: null,
      badgeColor: '',
    },
    {
      to: '/goals',
      label: 'Goals & Milestones',
      icon: Target,
      badge: null,
      badgeColor: '',
    },
    {
      to: '/productivity',
      label: 'Productivity Overview',
      icon: LayoutDashboard,
      badge: null,
      badgeColor: '',
    },
    {
      to: '/operations',
      label: 'Operations & GPS',
      icon: MapPin,
      badge: 'Live',
      badgeColor: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    },
  ];

  const reflectionAndSettingsItems = [
    {
      to: '/journal',
      label: 'Private Journal',
      icon: BookOpen,
      badge: 'Isolated',
      badgeColor: 'bg-rose-50 text-rose-700 border-rose-200',
    },
    {
      to: '/reflection',
      label: 'Reflective Insights',
      icon: Sparkles,
      badge: null,
      badgeColor: '',
    },
    {
      to: '/search',
      label: 'Omnisearch',
      icon: Search,
      badge: null,
      badgeColor: '',
    },
    {
      to: '/settings',
      label: 'Settings & Privacy',
      icon: Settings,
      badge: null,
      badgeColor: '',
    },
    {
      to: '/system',
      label: 'System & Database',
      icon: Activity,
      badge: null,
      badgeColor: '',
    },
  ];

  const isRouteActive = (to: string) => {
    if (to === '/chat') {
      return currentPath.startsWith('/chat');
    }
    return currentPath === to;
  };

  const renderNavGroup = (items: typeof coreNavItems) => (
    <div className="space-y-1">
      {items.map((item) => {
        const active = isRouteActive(item.to);
        const Icon = item.icon;
        return (
          <Link
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            className={`group w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold transition-all duration-150 ${
              active
                ? 'bg-emerald-50 text-emerald-900 shadow-sm border border-emerald-200/80 font-bold'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/80 border border-transparent'
            }`}
          >
            <div className="flex items-center space-x-2.5">
              <Icon
                className={`h-4 w-4 transition-colors ${
                  active ? 'text-emerald-600' : 'text-slate-400 group-hover:text-slate-700'
                }`}
              />
              <span className="tracking-tight">{item.label}</span>
            </div>
            {item.badge ? (
              <span
                className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border transition-colors ${
                  active
                    ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
                    : item.badgeColor
                }`}
              >
                {item.badge}
              </span>
            ) : active ? (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
            ) : null}
          </Link>
        );
      })}
    </div>
  );

  return (
    <aside className="w-64 bg-slate-50/95 border-r border-slate-200 flex flex-col h-full select-none backdrop-blur-md text-slate-900">
      {/* Brand Header */}
      <div className="p-4 border-b border-slate-200 flex items-center justify-between">
        <Link to="/home" onClick={onNavigate} className="flex items-center space-x-2.5 group">
          <div className="h-8 w-8 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 shadow-sm group-hover:scale-105 transition-transform duration-200">
            <Bot className="h-4 w-4 text-emerald-600 group-hover:text-emerald-700 transition-colors" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center">
              <span className="text-base font-extrabold tracking-[0.18em] text-slate-900">
                AUREN
              </span>
              <span className="ml-1.5 text-[8px] text-emerald-700 uppercase tracking-widest font-bold px-1 py-0.2 bg-emerald-50 rounded border border-emerald-200">
                Personal AI
              </span>
            </div>
            <span className="text-[9px] text-slate-500 tracking-wider uppercase font-semibold">Command Center</span>
          </div>
        </Link>
      </div>

      {/* Navigation Links Scroll Container */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6 scrollbar-thin">
        {/* Core Intelligence */}
        <div className="space-y-1">
          <p className="px-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">
            Command &amp; Intelligence
          </p>
          {renderNavGroup(coreNavItems)}
        </div>

        {/* Life Management */}
        <div className="space-y-1">
          <p className="px-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">
            Life Management
          </p>
          {renderNavGroup(lifeManagementItems)}
        </div>

        {/* Reflection, Search & Settings */}
        <div className="space-y-1">
          <p className="px-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">
            Reflection &amp; Settings
          </p>
          {renderNavGroup(reflectionAndSettingsItems)}
        </div>
      </div>

      {/* PWA Standalone Desktop Installation Prompt */}
      {!isInstalled && onOpenInstall && (
        <div className="px-3 pb-2">
          <button
            onClick={onOpenInstall}
            className="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-white hover:bg-slate-100 border border-slate-200 hover:border-slate-300 text-xs text-slate-700 hover:text-slate-900 transition group touch-target cursor-pointer shadow-sm"
            title="Install AUREN as standalone desktop app"
          >
            <div className="flex items-center space-x-2">
              <Download className="w-3.5 h-3.5 text-emerald-600 group-hover:scale-110 transition-transform" />
              <span className="font-semibold text-[11px]">Install Desktop App</span>
            </div>
            <span className="text-[9px] font-mono text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200 font-bold">
              PWA
            </span>
          </button>
        </div>
      )}

      {/* Persistent User Account Footer */}
      <div className="p-3 border-t border-slate-200 bg-slate-50/90">
        {isLoading ? (
          <div className="h-10 w-full rounded-xl bg-slate-100 animate-pulse border border-slate-200" />
        ) : user ? (
          <UserProfileMenu />
        ) : (
          <div className="space-y-2">
            <button
              onClick={() => onOpenAuth?.('signin')}
              className="w-full flex items-center justify-center space-x-1.5 py-2 px-3 text-xs font-semibold text-slate-700 hover:text-slate-900 hover:bg-slate-100 rounded-xl transition border border-slate-300 shadow-sm"
            >
              <LogIn className="h-3.5 w-3.5" />
              <span>Sign In</span>
            </button>
            <button
              onClick={() => onOpenAuth?.('signup')}
              className="w-full flex items-center justify-center py-2 px-3 text-xs font-semibold bg-emerald-500 hover:bg-emerald-400 text-white rounded-xl shadow-sm hover:shadow-[0_0_16px_rgba(16,185,129,0.3)] transition"
            >
              Get Started
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};

/**
 * Persistent Application Navigation Sidebar.
 * Displays the six core AUREN product areas:
 * 1. Home — Personal Command Center (/home)
 * 2. Assistant — Central AI Intelligence (/chat)
 * 3. Memory — Personal Knowledge & Context (/memories)
 * 4. Life Management — Tasks, Projects, Goals, Productivity
 * 5. Reflection — Private Journal & Reflective Intelligence
 * 6. Settings — Privacy, Preferences & Control
 * Elevated with AUREN Obsidian, Graphite & Champagne Design System.
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
      badgeColor: 'bg-indigo-950/70 text-indigo-300 border-indigo-800/40',
    },
    {
      to: '/chat',
      label: 'AI Assistant',
      icon: MessageSquare,
      badge: 'Active',
      badgeColor: 'bg-indigo-950/70 text-indigo-300 border-indigo-800/40',
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
  ];

  const reflectionAndSettingsItems = [
    {
      to: '/journal',
      label: 'Private Journal',
      icon: BookOpen,
      badge: 'Isolated',
      badgeColor: 'bg-purple-950/70 text-purple-300 border-purple-800/40',
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
            className={`group w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition-all duration-150 ${
              active
                ? 'bg-white/[0.06] text-white shadow-subtle-elevation border border-white/[0.09]'
                : 'text-slate-400 hover:text-slate-100 hover:bg-white/[0.03] border border-transparent'
            }`}
          >
            <div className="flex items-center space-x-2.5">
              <Icon
                className={`h-4 w-4 transition-colors ${
                  active ? 'text-champagne-300' : 'text-slate-400 group-hover:text-slate-200'
                }`}
              />
              <span className="tracking-tight">{item.label}</span>
            </div>
            {item.badge ? (
              <span
                className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border transition-colors ${
                  active
                    ? 'bg-champagne-950/80 text-champagne-300 border-champagne-700/50'
                    : item.badgeColor
                }`}
              >
                {item.badge}
              </span>
            ) : active ? (
              <span className="w-1.5 h-1.5 rounded-full bg-champagne-400 shadow-[0_0_8px_rgba(215,186,131,0.6)]" />
            ) : null}
          </Link>
        );
      })}
    </div>
  );

  return (
    <aside className="w-64 bg-[#07080c]/95 border-r border-white/[0.06] flex flex-col h-full select-none backdrop-blur-md">
      {/* Brand Header */}
      <div className="p-4 border-b border-white/[0.06] flex items-center justify-between">
        <Link to="/home" onClick={onNavigate} className="flex items-center space-x-2.5 group">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-br from-[#d7ba83] via-[#be8c42] to-[#6c4327] p-0.5 flex items-center justify-center text-white shadow-md shadow-[#d7ba83]/10 group-hover:scale-105 transition-transform duration-200">
            <div className="w-full h-full bg-[#07080c] rounded-[10px] flex items-center justify-center">
              <Bot className="h-4 w-4 text-champagne-300 group-hover:text-[#e6d4b0] transition-colors" />
            </div>
          </div>
          <div className="flex flex-col">
            <div className="flex items-center">
              <span className="text-base font-extrabold tracking-[0.18em] text-white">
                AUREN
              </span>
              <span className="ml-1.5 text-[8px] text-champagne-300 uppercase tracking-widest font-semibold px-1 py-0.2 bg-champagne-950/70 rounded border border-champagne-800/40">
                Personal AI
              </span>
            </div>
            <span className="text-[9px] text-slate-500 tracking-wider uppercase font-medium">Command Center</span>
          </div>
        </Link>
      </div>

      {/* Navigation Links Scroll Container */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6 scrollbar-thin">
        {/* Core Intelligence */}
        <div className="space-y-1">
          <p className="px-2 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            Command &amp; Intelligence
          </p>
          {renderNavGroup(coreNavItems)}
        </div>

        {/* Life Management */}
        <div className="space-y-1">
          <p className="px-2 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            Life Management
          </p>
          {renderNavGroup(lifeManagementItems)}
        </div>

        {/* Reflection, Search & Settings */}
        <div className="space-y-1">
          <p className="px-2 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
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
            className="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.07] hover:border-champagne-400/30 text-xs text-slate-300 hover:text-white transition group touch-target cursor-pointer"
            title="Install AUREN as standalone desktop app"
          >
            <div className="flex items-center space-x-2">
              <Download className="w-3.5 h-3.5 text-champagne-400 group-hover:scale-110 transition-transform" />
              <span className="font-medium text-[11px]">Install Desktop App</span>
            </div>
            <span className="text-[9px] font-mono text-champagne-400/80 bg-champagne-950/60 px-1.5 py-0.5 rounded border border-champagne-700/30">
              PWA
            </span>
          </button>
        </div>
      )}

      {/* Persistent User Account Footer */}
      <div className="p-3 border-t border-white/[0.06] bg-[#07080c]/90">
        {isLoading ? (
          <div className="h-10 w-full rounded-xl bg-white/[0.04] animate-pulse border border-white/[0.05]" />
        ) : user ? (
          <UserProfileMenu />
        ) : (
          <div className="space-y-2">
            <button
              onClick={() => onOpenAuth?.('signin')}
              className="w-full flex items-center justify-center space-x-1.5 py-2 px-3 text-xs font-medium text-slate-300 hover:text-white hover:bg-white/[0.04] rounded-xl transition border border-white/[0.08] hover:border-white/[0.14]"
            >
              <LogIn className="h-3.5 w-3.5" />
              <span>Sign In</span>
            </button>
            <button
              onClick={() => onOpenAuth?.('signup')}
              className="w-full flex items-center justify-center py-2 px-3 text-xs font-semibold bg-[#d7ba83] hover:bg-[#e6d4b0] text-[#07080c] rounded-xl shadow-sm hover:shadow-[0_0_16px_rgba(215,186,131,0.25)] border border-[#e6d4b0]/40 transition"
            >
              Get Started
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};

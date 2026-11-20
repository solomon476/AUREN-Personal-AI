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
} from 'lucide-react';
import { Link, useRouterState } from '@tanstack/react-router';
import { useAuth } from '../../context/AuthContext';
import { UserProfileMenu } from '../auth/UserProfileMenu';

interface NavigationSidebarProps {
  onNavigate?: () => void;
  onOpenAuth?: (mode: 'signin' | 'signup') => void;
}

export const NavigationSidebar: React.FC<NavigationSidebarProps> = ({
  onNavigate,
  onOpenAuth,
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
                  active ? 'text-indigo-400' : 'text-slate-400 group-hover:text-slate-200'
                }`}
              />
              <span className="tracking-tight">{item.label}</span>
            </div>
            {item.badge ? (
              <span
                className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border transition-colors ${
                  active
                    ? 'bg-indigo-950/90 text-indigo-300 border-indigo-700/60'
                    : item.badgeColor
                }`}
              >
                {item.badge}
              </span>
            ) : active ? (
              <span className="w-1.5 h-1.5 rounded-full bg-champagne-300/80 shadow-glow-champagne" />
            ) : null}
          </Link>
        );
      })}
    </div>
  );

  return (
    <aside className="w-64 bg-slate-950/95 border-r border-slate-800/80 flex flex-col h-full select-none backdrop-blur-md">
      {/* Brand Header */}
      <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
        <Link to="/home" onClick={onNavigate} className="flex items-center space-x-2.5 group">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-indigo-600 via-sky-500 to-champagne-300 p-0.5 flex items-center justify-center text-white shadow-md shadow-indigo-600/20 group-hover:scale-105 transition-transform duration-200">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <Bot className="h-4 w-4 text-indigo-400 group-hover:text-champagne-300 transition-colors" />
            </div>
          </div>
          <div className="flex flex-col">
            <div className="flex items-center">
              <span className="text-base font-extrabold tracking-widest bg-gradient-to-r from-slate-100 via-sky-200 to-indigo-200 bg-clip-text text-transparent">
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

      {/* Persistent User Account Footer */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950/90">
        {isLoading ? (
          <div className="h-10 w-full rounded-xl bg-slate-800/40 animate-pulse border border-slate-800/50" />
        ) : user ? (
          <UserProfileMenu />
        ) : (
          <div className="space-y-2">
            <button
              onClick={() => onOpenAuth?.('signin')}
              className="w-full flex items-center justify-center space-x-1.5 py-2 px-3 text-xs font-medium text-slate-300 hover:text-white hover:bg-white/[0.04] rounded-xl transition border border-slate-800 hover:border-slate-700"
            >
              <LogIn className="h-3.5 w-3.5" />
              <span>Sign In</span>
            </button>
            <button
              onClick={() => onOpenAuth?.('signup')}
              className="w-full flex items-center justify-center py-2 px-3 text-xs font-semibold bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white rounded-xl shadow-md shadow-indigo-600/20 hover:shadow-indigo-600/35 transition"
            >
              Get Started
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};

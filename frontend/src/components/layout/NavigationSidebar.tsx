/**
 * Persistent Application Navigation Sidebar.
 * Displays the six core AUREN product areas:
 * 1. Home — Personal Command Center (/home)
 * 2. Assistant — Central AI Intelligence (/chat)
 * 3. Memory — Personal Knowledge & Context (/memories)
 * 4. Life Management — Tasks, Projects, Goals, Productivity
 * 5. Reflection — Private Journal & Reflective Intelligence
 * 6. Settings — Privacy, Preferences & Control
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
  const { user } = useAuth();
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  const coreNavItems = [
    {
      to: '/home',
      label: 'Command Center',
      icon: Home,
      badge: 'Home',
      badgeColor: 'bg-indigo-950/80 text-indigo-300 border-indigo-800/40',
    },
    {
      to: '/chat',
      label: 'AI Assistant',
      icon: MessageSquare,
      badge: 'Active',
      badgeColor: 'bg-indigo-950/80 text-indigo-300 border-indigo-800/40',
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
      badgeColor: 'bg-purple-950/80 text-purple-300 border-purple-800/40',
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
            className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition ${
              active
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                : 'text-slate-400 hover:text-white hover:bg-slate-900/60'
            }`}
          >
            <div className="flex items-center space-x-2.5">
              <Icon className={`h-4 w-4 ${active ? 'text-white' : 'text-slate-400'}`} />
              <span>{item.label}</span>
            </div>
            {item.badge && (
              <span
                className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border ${
                  active ? 'bg-indigo-700/60 text-indigo-100 border-indigo-500/40' : item.badgeColor
                }`}
              >
                {item.badge}
              </span>
            )}
          </Link>
        );
      })}
    </div>
  );

  return (
    <aside className="w-64 bg-slate-950 border-r border-slate-800/80 flex flex-col h-full select-none">
      {/* Brand Header */}
      <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
        <Link to="/home" onClick={onNavigate} className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-tr from-indigo-600 to-sky-500 p-0.5 flex items-center justify-center text-white shadow-md shadow-indigo-600/20">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <Bot className="h-4 w-4 text-indigo-400" />
            </div>
          </div>
          <div>
            <span className="text-lg font-bold tracking-tight bg-gradient-to-r from-indigo-400 via-sky-300 to-emerald-400 bg-clip-text text-transparent">
              AUREN
            </span>
            <span className="ml-1.5 text-[9px] text-slate-400 uppercase tracking-widest font-semibold px-1.5 py-0.5 bg-slate-900 rounded border border-slate-800">
              Phase 3C
            </span>
          </div>
        </Link>
      </div>

      {/* Navigation Links Scroll Container */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {/* Core Intelligence */}
        <div className="space-y-1">
          <p className="px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Command &amp; Intelligence
          </p>
          {renderNavGroup(coreNavItems)}
        </div>

        {/* Life Management */}
        <div className="space-y-1">
          <p className="px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Life Management
          </p>
          {renderNavGroup(lifeManagementItems)}
        </div>

        {/* Reflection, Search & Settings */}
        <div className="space-y-1">
          <p className="px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Reflection &amp; Settings
          </p>
          {renderNavGroup(reflectionAndSettingsItems)}
        </div>
      </div>

      {/* Persistent User Account Footer */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950">
        {user ? (
          <UserProfileMenu />
        ) : (
          <div className="space-y-2">
            <button
              onClick={() => onOpenAuth?.('signin')}
              className="w-full flex items-center justify-center space-x-1.5 py-2 px-3 text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-900 rounded-xl transition border border-slate-800"
            >
              <LogIn className="h-3.5 w-3.5" />
              <span>Sign In</span>
            </button>
            <button
              onClick={() => onOpenAuth?.('signup')}
              className="w-full flex items-center justify-center py-2 px-3 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-md shadow-indigo-600/20 transition"
            >
              Get Started
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};

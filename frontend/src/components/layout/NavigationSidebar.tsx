/**
 * Persistent Application Navigation Sidebar.
 * Displays primary functional routes, future roadmap capabilities, and user session controls.
 */

import React from 'react';
import { 
  Bot, 
  MessageSquare, 
  LayoutDashboard, 
  Brain, 
  CheckSquare, 
  FolderKanban, 
  Target, 
  BookOpen, 
  Settings,
  LogIn
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

  const primaryNavItems = [
    {
      to: '/chat',
      label: 'AI Assistant',
      icon: MessageSquare,
      badge: 'Streaming',
      badgeColor: 'bg-indigo-950/80 text-indigo-300 border-indigo-800/40',
    },
    {
      to: '/memories',
      label: 'Long-term Memory',
      icon: Brain,
      badge: 'Explorer',
      badgeColor: 'bg-cyan-950/80 text-cyan-300 border-cyan-800/40',
    },
    {
      to: '/system',
      label: 'System & Database',
      icon: LayoutDashboard,
      badge: null,
      badgeColor: '',
    },
  ];

  const roadmapNavItems = [
    {
      to: '/tasks',
      label: 'Tasks & Timetable',
      icon: CheckSquare,
      badge: 'Phase 3C.4',
    },
    {
      to: '/projects',
      label: 'Projects',
      icon: FolderKanban,
      badge: 'Phase 3C.4',
    },
    {
      to: '/goals',
      label: 'Goals & Milestones',
      icon: Target,
      badge: 'Phase 3C.4',
    },
    {
      to: '/journal',
      label: 'Private Journal',
      icon: BookOpen,
      badge: 'Phase 3C.5',
    },
    {
      to: '/settings',
      label: 'Settings',
      icon: Settings,
      badge: 'Planned',
    },
  ];

  const isRouteActive = (to: string) => {
    if (to === '/chat') {
      return currentPath === '/' || currentPath.startsWith('/chat');
    }
    return currentPath === to;
  };

  return (
    <aside className="w-64 bg-slate-950 border-r border-slate-800/80 flex flex-col h-full select-none">
      {/* Brand Header */}
      <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
        <Link to="/chat" onClick={onNavigate} className="flex items-center space-x-2.5">
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
              Phase 3C.1
            </span>
          </div>
        </Link>
      </div>

      {/* Navigation Links Scroll Container */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {/* Core Capabilities */}
        <div className="space-y-1">
          <p className="px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Intelligence &amp; System
          </p>
          {primaryNavItems.map((item) => {
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

        {/* Roadmap Capabilities */}
        <div className="space-y-1">
          <p className="px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Roadmap Capabilities
          </p>
          {roadmapNavItems.map((item) => {
            const active = isRouteActive(item.to);
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={onNavigate}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium transition ${
                  active
                    ? 'bg-slate-800 text-white border border-slate-700'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
                }`}
              >
                <div className="flex items-center space-x-2.5">
                  <Icon className="h-4 w-4 text-slate-500" />
                  <span>{item.label}</span>
                </div>
                <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-slate-900 text-slate-500 border border-slate-800">
                  {item.badge}
                </span>
              </Link>
            );
          })}
        </div>
      </div>

      {/* User Footer Region */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950">
        {user ? (
          <div className="flex items-center justify-between">
            <UserProfileMenu />
          </div>
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

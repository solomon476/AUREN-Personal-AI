/**
 * Mobile-First Bottom Navigation Bar for AUREN.
 * Provides accessible, one-handed touch navigation across primary surfaces
 * with safe-area insets, clear active state indicators, and secondary drawer access.
 */

import React from 'react';
import { Home, MessageSquare, CheckSquare, BookOpen, Grid } from 'lucide-react';
import { Link, useRouterState } from '@tanstack/react-router';

interface MobileBottomNavProps {
  onOpenMore: () => void;
  isMoreOpen?: boolean;
}

export const MobileBottomNav: React.FC<MobileBottomNavProps> = ({
  onOpenMore,
  isMoreOpen = false,
}) => {
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  const isHomeActive = currentPath === '/home' || currentPath === '/';
  const isChatActive = currentPath.startsWith('/chat');
  const isTasksActive = currentPath === '/tasks';
  const isJournalActive = currentPath === '/journal';

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-slate-950/95 backdrop-blur-xl border-t border-slate-800/80 pb-[env(safe-area-inset-bottom,0px)] shadow-2xl transition-all duration-200"
      aria-label="Mobile Bottom Navigation"
    >
      <div className="flex items-center justify-around h-16 px-2 max-w-md mx-auto">
        {/* 1. Home */}
        <Link
          to="/home"
          className={`flex-1 flex flex-col items-center justify-center py-1 rounded-xl transition-all duration-150 touch-target ${
            isHomeActive
              ? 'text-champagne-300 font-semibold'
              : 'text-slate-400 hover:text-slate-200'
          }`}
          aria-label="Mobile Home"
          aria-current={isHomeActive ? 'page' : undefined}
        >
          <div className="relative">
            <Home className={`w-5 h-5 transition-transform duration-150 ${isHomeActive ? 'scale-110 text-champagne-300' : ''}`} />
            {isHomeActive && (
              <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-champagne-300 shadow-glow-champagne" />
            )}
          </div>
          <span className="text-[10px] tracking-tight mt-1">Home</span>
        </Link>

        {/* 2. Assistant */}
        <Link
          to="/chat"
          className={`flex-1 flex flex-col items-center justify-center py-1 rounded-xl transition-all duration-150 touch-target ${
            isChatActive
              ? 'text-champagne-300 font-semibold'
              : 'text-slate-400 hover:text-slate-200'
          }`}
          aria-label="Mobile Assistant"
          aria-current={isChatActive ? 'page' : undefined}
        >
          <div className="relative">
            <MessageSquare className={`w-5 h-5 transition-transform duration-150 ${isChatActive ? 'scale-110 text-champagne-300' : ''}`} />
            {isChatActive && (
              <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-champagne-300 shadow-glow-champagne" />
            )}
          </div>
          <span className="text-[10px] tracking-tight mt-1">Assistant</span>
        </Link>

        {/* 3. Tasks */}
        <Link
          to="/tasks"
          className={`flex-1 flex flex-col items-center justify-center py-1 rounded-xl transition-all duration-150 touch-target ${
            isTasksActive
              ? 'text-champagne-300 font-semibold'
              : 'text-slate-400 hover:text-slate-200'
          }`}
          aria-label="Mobile Tasks"
          aria-current={isTasksActive ? 'page' : undefined}
        >
          <div className="relative">
            <CheckSquare className={`w-5 h-5 transition-transform duration-150 ${isTasksActive ? 'scale-110 text-champagne-300' : ''}`} />
            {isTasksActive && (
              <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-champagne-300 shadow-glow-champagne" />
            )}
          </div>
          <span className="text-[10px] tracking-tight mt-1">Tasks</span>
        </Link>

        {/* 4. Journal */}
        <Link
          to="/journal"
          className={`flex-1 flex flex-col items-center justify-center py-1 rounded-xl transition-all duration-150 touch-target ${
            isJournalActive
              ? 'text-champagne-300 font-semibold'
              : 'text-slate-400 hover:text-slate-200'
          }`}
          aria-label="Mobile Journal"
          aria-current={isJournalActive ? 'page' : undefined}
        >
          <div className="relative">
            <BookOpen className={`w-5 h-5 transition-transform duration-150 ${isJournalActive ? 'scale-110 text-champagne-300' : ''}`} />
            {isJournalActive && (
              <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-champagne-300 shadow-glow-champagne" />
            )}
          </div>
          <span className="text-[10px] tracking-tight mt-1">Journal</span>
        </Link>

        {/* 5. More Secondary Hub */}
        <button
          type="button"
          onClick={onOpenMore}
          className={`flex-1 flex flex-col items-center justify-center py-1 rounded-xl transition-all duration-150 touch-target ${
            isMoreOpen
              ? 'text-champagne-300 font-semibold'
              : 'text-slate-400 hover:text-slate-200'
          }`}
          aria-label="Mobile More Menu"
          aria-expanded={isMoreOpen}
        >
          <div className="relative">
            <Grid className={`w-5 h-5 transition-transform duration-150 ${isMoreOpen ? 'scale-110 text-champagne-300' : ''}`} />
            {isMoreOpen && (
              <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-champagne-300" />
            )}
          </div>
          <span className="text-[10px] tracking-tight mt-1">More</span>
        </button>
      </div>
    </nav>
  );
};


/**
 * Core Application Shell Layout.
 * Integrates persistent navigation sidebar (desktop), mobile bottom navigation bar (phone),
 * slide-up secondary hub sheet, responsive drawer, top bar, and main content area.
 */

import React, { useState } from 'react';
import { Menu, X, Bot, Search } from 'lucide-react';
import { Outlet, Link } from '@tanstack/react-router';
import { NavigationSidebar } from './NavigationSidebar';
import { MobileBottomNav } from './MobileBottomNav';
import { MobileMoreSheet } from './MobileMoreSheet';
import { AuthModal } from '../auth/AuthModal';
import { useAuth } from '../../context/AuthContext';
import { UserProfileMenu } from '../auth/UserProfileMenu';

export const AppLayout: React.FC = () => {
  const { user, isLoading } = useAuth();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMoreSheetOpen, setIsMoreSheetOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState<'signin' | 'signup'>('signin');

  const openAuth = (mode: 'signin' | 'signup') => {
    setAuthMode(mode);
    setIsAuthModalOpen(true);
    setIsMobileMenuOpen(false);
    setIsMoreSheetOpen(false);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100 font-sans selection:bg-indigo-600 selection:text-white">
      {/* Desktop Sidebar (Persistent) */}
      <div className="hidden md:flex flex-shrink-0 z-20">
        <NavigationSidebar onOpenAuth={openAuth} />
      </div>

      {/* Mobile Drawer (Slide-over Full Navigation) */}
      {isMobileMenuOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden animate-in fade-in duration-200">
          <div
            className="fixed inset-0 bg-slate-950/80 backdrop-blur-md"
            onClick={() => setIsMobileMenuOpen(false)}
          />
          <div className="relative flex flex-col w-72 max-w-xs bg-slate-950 shadow-2xl z-10 border-r border-slate-800/80">
            <button
              onClick={() => setIsMobileMenuOpen(false)}
              className="absolute top-4 right-3 text-slate-400 hover:text-white p-2 rounded-lg touch-target flex items-center justify-center"
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
            <NavigationSidebar
              onNavigate={() => setIsMobileMenuOpen(false)}
              onOpenAuth={openAuth}
            />
          </div>
        </div>
      )}

      {/* Main Execution View */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        {/* Subtle Ambient Background Gradient */}
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(215,186,131,0.04),rgba(255,255,255,0))]" />

        {/* Mobile Header Bar */}
        <header className="md:hidden flex items-center justify-between px-4 py-2.5 border-b border-white/[0.06] bg-[#07080c]/95 backdrop-blur-md z-30 pt-[env(safe-area-inset-top,0.5rem)]">
          <div className="flex items-center space-x-2.5">
            <button
              onClick={() => setIsMobileMenuOpen(true)}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-white/[0.04] border border-white/[0.08] touch-target flex items-center justify-center transition"
              aria-label="Open navigation menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <Link to="/home" className="flex items-center space-x-2">
              <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-[#d7ba83] via-[#be8c42] to-[#6c4327] p-0.5 flex items-center justify-center text-white shadow-sm">
                <div className="w-full h-full bg-[#07080c] rounded-[6px] flex items-center justify-center">
                  <Bot className="h-3.5 w-3.5 text-champagne-300" />
                </div>
              </div>
              <span className="text-sm font-extrabold tracking-[0.16em] text-white">
                AUREN
              </span>
            </Link>
          </div>

          <div className="flex items-center space-x-2">
            <Link
              to="/search"
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-white/[0.04] border border-white/[0.08] touch-target flex items-center justify-center transition"
              aria-label="Search"
            >
              <Search className="h-4 w-4" />
            </Link>

            {isLoading ? (
              <div className="h-7 w-16 bg-white/[0.04] rounded-xl animate-pulse" />
            ) : user ? (
              <UserProfileMenu />
            ) : (
              <button
                onClick={() => openAuth('signin')}
                className="px-3.5 py-1.5 text-xs font-semibold bg-[#d7ba83] hover:bg-[#e6d4b0] text-[#07080c] rounded-xl shadow-sm transition"
              >
                Sign In
              </button>
            )}
          </div>
        </header>

        {/* Dynamic Route Content (with bottom padding for mobile navigation bar) */}
        <main className="flex-1 overflow-y-auto p-3.5 sm:p-7 pb-20 md:pb-7 relative z-0 scrollbar-thin">
          <Outlet />
        </main>

        {/* Mobile-First Bottom Navigation Bar */}
        <MobileBottomNav
          onOpenMore={() => setIsMoreSheetOpen(true)}
          isMoreOpen={isMoreSheetOpen}
        />

        {/* Mobile More Secondary Navigation Sheet */}
        <MobileMoreSheet
          isOpen={isMoreSheetOpen}
          onClose={() => setIsMoreSheetOpen(false)}
          onOpenAuth={openAuth}
        />
      </div>

      {/* Global Auth Modal */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        defaultMode={authMode}
      />
    </div>
  );
};

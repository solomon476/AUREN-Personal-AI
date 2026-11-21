/**
 * Core Application Shell Layout.
 * Integrates persistent navigation sidebar (desktop), mobile bottom navigation bar (phone),
 * slide-up secondary hub sheet, responsive drawer, top bar, and main content area.
 * Styled with Executive White, Emerald accents, and crisp Slate typography.
 */

import React, { useState } from 'react';
import { Menu, X, Bot, Search } from 'lucide-react';
import { Outlet, Link, useRouterState } from '@tanstack/react-router';
import { NavigationSidebar } from './NavigationSidebar';
import { MobileBottomNav } from './MobileBottomNav';
import { MobileMoreSheet } from './MobileMoreSheet';
import { AuthModal } from '../auth/AuthModal';
import { useAuth } from '../../context/AuthContext';
import { UserProfileMenu } from '../auth/UserProfileMenu';
import { usePWAInstall } from '../../hooks/usePWAInstall';
import { PWAInstallBanner } from '../pwa/PWAInstallBanner';

export const AppLayout: React.FC = () => {
  const { user, isLoading } = useAuth();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMoreSheetOpen, setIsMoreSheetOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState<'signin' | 'signup'>('signin');
  const routerState = useRouterState();
  const isChat = routerState.location.pathname.startsWith('/chat');

  const {
    isInstalled,
    setIsInstallModalOpen,
  } = usePWAInstall();

  const openAuth = (mode: 'signin' | 'signup') => {
    setAuthMode(mode);
    setIsAuthModalOpen(true);
    setIsMobileMenuOpen(false);
    setIsMoreSheetOpen(false);
  };

  const handleOpenInstall = () => {
    setIsInstallModalOpen(true);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white text-slate-900 font-sans selection:bg-emerald-500 selection:text-white">
      {/* Desktop Sidebar (Persistent) */}
      <div className="hidden md:flex flex-shrink-0 z-20">
        <NavigationSidebar
          onOpenAuth={openAuth}
          onOpenInstall={handleOpenInstall}
          isInstalled={isInstalled}
        />
      </div>

      {/* Mobile Drawer (Slide-over Full Navigation) */}
      {isMobileMenuOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden animate-in fade-in duration-200">
          <div
            className="fixed inset-0 bg-slate-950/40 backdrop-blur-sm"
            onClick={() => setIsMobileMenuOpen(false)}
          />
          <div className="relative flex flex-col w-72 max-w-xs bg-white shadow-2xl z-10 border-r border-slate-200">
            <button
              onClick={() => setIsMobileMenuOpen(false)}
              className="absolute top-4 right-3 text-slate-500 hover:text-slate-900 p-2 rounded-lg touch-target flex items-center justify-center"
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
            <NavigationSidebar
              onNavigate={() => setIsMobileMenuOpen(false)}
              onOpenAuth={openAuth}
              onOpenInstall={handleOpenInstall}
              isInstalled={isInstalled}
            />
          </div>
        </div>
      )}

      {/* Main Execution View */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative bg-white">
        {/* Subtle Ambient Background Gradient */}
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(16,185,129,0.03),rgba(255,255,255,0))]" />

        {/* Global PWA Installation Alert Notification */}
        <PWAInstallBanner />

        {/* Mobile Header Bar */}
        <header className="md:hidden flex items-center justify-between px-4 py-2.5 border-b border-slate-200 bg-white/95 backdrop-blur-md z-30 pt-[env(safe-area-inset-top,0.5rem)] shadow-xs">
          <div className="flex items-center space-x-2.5">
            <button
              onClick={() => setIsMobileMenuOpen(true)}
              className="p-2 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200 touch-target flex items-center justify-center transition"
              aria-label="Open navigation menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <Link to="/home" className="flex items-center space-x-2">
              <div className="h-7 w-7 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 shadow-sm">
                <Bot className="h-4 w-4 text-emerald-600" />
              </div>
              <span className="text-sm font-extrabold tracking-[0.16em] text-slate-900">
                AUREN
              </span>
            </Link>
          </div>

          <div className="flex items-center space-x-2">
            <Link
              to="/search"
              className="p-2 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200 touch-target flex items-center justify-center transition"
              aria-label="Search"
            >
              <Search className="h-4 w-4" />
            </Link>

            {isLoading ? (
              <div className="h-7 w-16 bg-slate-100 rounded-xl animate-pulse" />
            ) : user ? (
              <UserProfileMenu />
            ) : (
              <button
                onClick={() => openAuth('signin')}
                className="px-3.5 py-1.5 text-xs font-semibold bg-emerald-500 hover:bg-emerald-400 text-white rounded-xl shadow-sm transition"
              >
                Sign In
              </button>
            )}
          </div>
        </header>

        {/* Dynamic Route Content (with bottom padding for mobile navigation bar) */}
        <main
          className={
            isChat
              ? 'flex-1 flex flex-col min-h-0 overflow-hidden p-2 sm:p-4 pb-[calc(4.5rem+env(safe-area-inset-bottom,0px))] md:pb-4 relative z-0 bg-white'
              : 'flex-1 overflow-y-auto p-3.5 sm:p-7 pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] md:pb-7 relative z-0 scrollbar-thin bg-white'
          }
        >
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
          onOpenInstall={handleOpenInstall}
          isInstalled={isInstalled}
        />

        {/* Global Auth Modal */}
        <AuthModal
          isOpen={isAuthModalOpen}
          defaultMode={authMode}
          onClose={() => setIsAuthModalOpen(false)}
        />
      </div>
    </div>
  );
};

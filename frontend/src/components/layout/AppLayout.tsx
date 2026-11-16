/**
 * Core Application Shell Layout.
 * Integrates persistent navigation sidebar, mobile responsive drawer, top bar, and main content area.
 */

import React, { useState } from 'react';
import { Menu, X, Bot } from 'lucide-react';
import { Outlet, Link } from '@tanstack/react-router';
import { NavigationSidebar } from './NavigationSidebar';
import { AuthModal } from '../auth/AuthModal';
import { useAuth } from '../../context/AuthContext';
import { UserProfileMenu } from '../auth/UserProfileMenu';

export const AppLayout: React.FC = () => {
  const { user } = useAuth();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState<'signin' | 'signup'>('signin');

  const openAuth = (mode: 'signin' | 'signup') => {
    setAuthMode(mode);
    setIsAuthModalOpen(true);
    setIsMobileMenuOpen(false);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100 font-sans">
      {/* Desktop Sidebar (Persistent) */}
      <div className="hidden md:flex flex-shrink-0">
        <NavigationSidebar onOpenAuth={openAuth} />
      </div>

      {/* Mobile Drawer (Slide-over) */}
      {isMobileMenuOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden animate-in fade-in duration-200">
          <div
            className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm"
            onClick={() => setIsMobileMenuOpen(false)}
          />
          <div className="relative flex flex-col w-72 max-w-xs bg-slate-950 shadow-2xl z-10 border-r border-slate-800">
            <button
              onClick={() => setIsMobileMenuOpen(false)}
              className="absolute top-4 right-3 text-slate-400 hover:text-white p-1 rounded-lg"
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
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile Header Bar */}
        <header className="md:hidden flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setIsMobileMenuOpen(true)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-900 border border-slate-800"
              aria-label="Open navigation menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <Link to="/chat" className="flex items-center space-x-2">
              <div className="h-7 w-7 rounded-lg bg-gradient-to-tr from-indigo-600 to-sky-500 p-0.5 flex items-center justify-center text-white">
                <Bot className="h-4 w-4 text-white" />
              </div>
              <span className="text-base font-bold bg-gradient-to-r from-indigo-400 via-sky-300 to-emerald-400 bg-clip-text text-transparent">
                AUREN
              </span>
            </Link>
          </div>

          <div className="flex items-center space-x-2">
            {user ? (
              <UserProfileMenu />
            ) : (
              <button
                onClick={() => openAuth('signin')}
                className="px-3 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition"
              >
                Sign In
              </button>
            )}
          </div>
        </header>

        {/* Dynamic Route Content */}
        <main className="flex-1 overflow-y-auto p-3 sm:p-6 bg-slate-950/50">
          <Outlet />
        </main>
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

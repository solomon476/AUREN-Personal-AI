/**
 * Authentication Modal Dialog for Login and Account Registration.
 * Elevated with AUREN Obsidian & Champagne Design System.
 */

import React, { useState } from 'react';
import { X, Lock, Mail, User, AlertCircle, Loader2, Sparkles, ArrowRight } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultMode?: 'signin' | 'signup';
}

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  defaultMode = 'signin',
}) => {
  const { signIn, signUp, isConfigured } = useAuth();
  const [mode, setMode] = useState<'signin' | 'signup'>(defaultMode);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessNotice(null);

    if (!email || !password) {
      setErrorMessage('Please fill in all required fields.');
      return;
    }

    if (password.length < 6) {
      setErrorMessage('Password must be at least 6 characters long.');
      return;
    }

    setIsSubmitting(true);

    try {
      if (mode === 'signup') {
        const result = await signUp(email, password, fullName);
        if (!result.success) {
          setErrorMessage(result.error || 'Failed to create account.');
        } else {
          setSuccessNotice('Account created successfully! Check your email if confirmation is required.');
          setTimeout(() => {
            onClose();
          }, 1500);
        }
      } else {
        const result = await signIn(email, password);
        if (!result.success) {
          setErrorMessage(result.error || 'Invalid credentials or user not found.');
        } else {
          onClose();
        }
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-md bg-slate-900/95 border border-slate-800/90 rounded-2xl shadow-modal-elevation overflow-hidden p-6 sm:p-8 animate-in zoom-in-95 duration-200"
        role="dialog"
        aria-modal="true"
      >
        {/* Ambient Top Glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-48 h-24 bg-indigo-500/10 blur-2xl pointer-events-none rounded-full" />

        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white transition p-1.5 rounded-xl hover:bg-slate-800/80 touch-target flex items-center justify-center"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Modal Header */}
        <div className="text-center space-y-1.5 mb-6 relative">
          <div className="inline-flex h-11 w-11 rounded-xl bg-gradient-to-tr from-indigo-950 to-slate-900 border border-indigo-500/30 items-center justify-center text-indigo-400 mb-2 shadow-glow-indigo">
            <Lock className="h-5 w-5 text-indigo-400" />
          </div>
          <h3 className="text-xl font-bold tracking-tight text-white">
            {mode === 'signin' ? 'Welcome Back to AUREN' : 'Create Your AUREN Account'}
          </h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            {mode === 'signin'
              ? 'Access your private memory, tasks, and personal assistant.'
              : 'Start your private personal intelligence workspace.'}
          </p>
        </div>

        {!isConfigured && (
          <div className="mb-5 p-3.5 rounded-xl bg-amber-950/30 border border-amber-800/50 space-y-2 text-xs text-amber-200">
            <div className="flex items-start space-x-2.5">
              <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5 text-amber-400" />
              <div>
                <p className="font-semibold text-amber-300">Supabase Configuration Required</p>
                <p className="text-amber-400/80 mt-0.5 leading-relaxed text-[11px]">
                  Set <code className="font-mono bg-slate-950/80 px-1 py-0.5 rounded border border-amber-800/40">VITE_SUPABASE_URL</code> and{' '}
                  <code className="font-mono bg-slate-950/80 px-1 py-0.5 rounded border border-amber-800/40">VITE_SUPABASE_ANON_KEY</code> in{' '}
                  <code className="font-mono text-amber-200">frontend/.env</code> to enable live authentication.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="w-full mt-2 py-1.5 px-3 rounded-lg bg-amber-900/30 hover:bg-amber-900/50 border border-amber-700/40 text-[11px] font-medium text-amber-200 flex items-center justify-center space-x-1.5 transition"
            >
              <span>Continue Exploring in Guest Mode</span>
              <ArrowRight className="w-3 h-3 text-amber-300" />
            </button>
          </div>
        )}

        {errorMessage && (
          <div className="mb-4 p-3 rounded-xl bg-rose-950/40 border border-rose-800/50 flex items-start space-x-2 text-xs text-rose-300 animate-in fade-in">
            <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5 text-rose-400" />
            <p className="leading-relaxed">{errorMessage}</p>
          </div>
        )}

        {successNotice && (
          <div className="mb-4 p-3 rounded-xl bg-emerald-950/40 border border-emerald-800/50 text-xs text-emerald-300 flex items-center space-x-2 animate-in fade-in">
            <Sparkles className="h-4 w-4 text-emerald-400 flex-shrink-0" />
            <p>{successNotice}</p>
          </div>
        )}

        {/* Auth Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'signup' && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300">Full Name</label>
              <div className="relative">
                <User className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
                <input
                  type="text"
                  placeholder="Solomon Yamal"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full pl-9 pr-3 py-2.5 text-xs sm:text-sm bg-slate-950/90 border border-slate-800 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/50 transition"
                />
              </div>
            </div>
          )}

          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-300">Email Address</label>
            <div className="relative">
              <Mail className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <input
                type="email"
                required
                placeholder="you@domain.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-9 pr-3 py-2.5 text-xs sm:text-sm bg-slate-950/90 border border-slate-800 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/50 transition"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-300">Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <input
                type="password"
                required
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-9 pr-3 py-2.5 text-xs sm:text-sm bg-slate-950/90 border border-slate-800 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/50 transition"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting || !isConfigured}
            className="w-full mt-3 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs sm:text-sm font-semibold shadow-lg shadow-indigo-600/30 transition flex items-center justify-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[1.01] active:scale-[0.99]"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>{mode === 'signin' ? 'Signing In...' : 'Creating Account...'}</span>
              </>
            ) : (
              <span>{mode === 'signin' ? 'Sign In' : 'Create Account'}</span>
            )}
          </button>
        </form>

        {/* Switch Mode Footer */}
        <div className="mt-6 pt-4 border-t border-slate-800/80 text-center text-xs text-slate-400">
          {mode === 'signin' ? (
            <p>
              Don't have an account yet?{' '}
              <button
                type="button"
                onClick={() => {
                  setMode('signup');
                  setErrorMessage(null);
                }}
                className="text-indigo-400 hover:text-indigo-300 font-medium underline underline-offset-2 transition"
              >
                Create one now
              </button>
            </p>
          ) : (
            <p>
              Already have an account?{' '}
              <button
                type="button"
                onClick={() => {
                  setMode('signin');
                  setErrorMessage(null);
                }}
                className="text-indigo-400 hover:text-indigo-300 font-medium underline underline-offset-2 transition"
              >
                Sign in here
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

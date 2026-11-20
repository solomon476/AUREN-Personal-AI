/**
 * Authentication Modal Dialog for Login and Account Registration.
 * Elevated with AUREN Obsidian & Champagne Design System.
 * Features:
 * - Robust email validation and password confirmation match check.
 * - Dedicated verification screen for email confirmation flow.
 * - One-click resolution for duplicate email registration ("Sign In Instead").
 * - Clear diagnostics for unconfigured environment variables.
 */

import React, { useState } from 'react';
import {
  X,
  Lock,
  Mail,
  User,
  AlertCircle,
  Loader2,
  Sparkles,
  ArrowRight,
  CheckCircle,
  KeyRound,
  ExternalLink,
} from 'lucide-react';
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
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [userExistsError, setUserExistsError] = useState(false);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);
  const [pendingConfirmationEmail, setPendingConfirmationEmail] = useState<string | null>(null);

  if (!isOpen) return null;

  const resetFormState = () => {
    setErrorMessage(null);
    setUserExistsError(false);
    setSuccessNotice(null);
    setPendingConfirmationEmail(null);
  };

  const handleModeSwitch = (newMode: 'signin' | 'signup') => {
    setMode(newMode);
    resetFormState();
    setPassword('');
    setConfirmPassword('');
  };

  const handleClose = () => {
    resetFormState();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setUserExistsError(false);
    setSuccessNotice(null);

    const cleanEmail = email.trim();

    // 1. Validate Email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!cleanEmail || !emailRegex.test(cleanEmail)) {
      setErrorMessage('Please enter a valid email address.');
      return;
    }

    // 2. Validate Password length
    if (!password || password.length < 6) {
      setErrorMessage('Password must be at least 6 characters long.');
      return;
    }

    // 3. Validate Password confirmation for registration
    if (mode === 'signup') {
      if (!confirmPassword) {
        setErrorMessage('Please confirm your password.');
        return;
      }
      if (password !== confirmPassword) {
        setErrorMessage('Passwords do not match. Please verify both entries.');
        return;
      }
    }

    setIsSubmitting(true);

    try {
      if (mode === 'signup') {
        const result = await signUp(cleanEmail, password, fullName);

        if (!result.success) {
          if (result.userExists) {
            setUserExistsError(true);
            setErrorMessage(result.error || 'An account with this email already exists. Please sign in instead.');
          } else {
            setErrorMessage(result.error || 'Failed to create account.');
          }
        } else if (result.requiresEmailConfirmation) {
          // Email confirmation is required by Supabase Auth configuration
          setPendingConfirmationEmail(cleanEmail);
        } else {
          // Auto-authenticated without email confirmation step
          setSuccessNotice('Account created successfully! Welcome to AUREN.');
          setTimeout(() => {
            handleClose();
          }, 1200);
        }
      } else {
        const result = await signIn(cleanEmail, password);
        if (!result.success) {
          setErrorMessage(result.error || 'Invalid credentials or user not found.');
        } else {
          setSuccessNotice('Signed in successfully.');
          setTimeout(() => {
            handleClose();
          }, 600);
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
          onClick={handleClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white transition p-1.5 rounded-xl hover:bg-slate-800/80 touch-target flex items-center justify-center"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        {/* State A: Email Confirmation Screen */}
        {pendingConfirmationEmail ? (
          <div className="text-center py-3 space-y-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="inline-flex h-14 w-14 rounded-2xl bg-gradient-to-tr from-indigo-950 to-slate-900 border border-indigo-500/40 items-center justify-center text-indigo-400 mb-1 shadow-glow-indigo">
              <Mail className="h-7 w-7 text-indigo-400 animate-pulse" />
            </div>

            <div className="space-y-1.5">
              <h3 className="text-xl font-bold tracking-tight text-white">Check Your Email</h3>
              <p className="text-xs text-slate-400 leading-relaxed max-w-xs mx-auto">
                We've sent an activation link to:
              </p>
              <p className="text-xs font-mono font-semibold text-indigo-300 bg-indigo-950/50 py-1.5 px-3 rounded-xl border border-indigo-800/50 inline-block max-w-full truncate">
                {pendingConfirmationEmail}
              </p>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800/80 text-left space-y-2 text-xs text-slate-400">
              <div className="flex items-start space-x-2">
                <CheckCircle className="h-4 w-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                <span className="text-[11px] text-slate-300 leading-relaxed">
                  Click the confirmation link in the email to activate your account.
                </span>
              </div>
              <div className="flex items-start space-x-2">
                <ExternalLink className="h-4 w-4 text-slate-500 flex-shrink-0 mt-0.5" />
                <span className="text-[11px] text-slate-400 leading-relaxed">
                  Once confirmed, return here to sign in with your email and password.
                </span>
              </div>
            </div>

            <div className="pt-2 space-y-2">
              <button
                type="button"
                onClick={() => {
                  setPendingConfirmationEmail(null);
                  handleModeSwitch('signin');
                }}
                className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs sm:text-sm font-semibold shadow-lg shadow-indigo-600/30 transition flex items-center justify-center space-x-2"
              >
                <span>Proceed to Sign In</span>
                <ArrowRight className="h-4 w-4" />
              </button>

              <button
                type="button"
                onClick={handleClose}
                className="w-full py-2 px-3 text-xs text-slate-400 hover:text-slate-300 transition"
              >
                Close Window
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Modal Header */}
            <div className="text-center space-y-1.5 mb-6 relative">
              <div className="inline-flex h-11 w-11 rounded-xl bg-gradient-to-tr from-indigo-950 to-slate-900 border border-indigo-500/30 items-center justify-center text-indigo-400 mb-2 shadow-glow-indigo">
                {mode === 'signin' ? (
                  <Lock className="h-5 w-5 text-indigo-400" />
                ) : (
                  <KeyRound className="h-5 w-5 text-indigo-400" />
                )}
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

            {/* Unconfigured Configuration Banner */}
            {!isConfigured && (
              <div className="mb-5 p-3.5 rounded-xl bg-amber-950/30 border border-amber-800/50 space-y-2 text-xs text-amber-200">
                <div className="flex items-start space-x-2.5">
                  <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5 text-amber-400" />
                  <div>
                    <p className="font-semibold text-amber-300">Supabase Configuration Required</p>
                    <p className="text-amber-400/80 mt-0.5 leading-relaxed text-[11px]">
                      Configure <code className="font-mono bg-slate-950/80 px-1 py-0.5 rounded border border-amber-800/40">VITE_SUPABASE_URL</code> and{' '}
                      <code className="font-mono bg-slate-950/80 px-1 py-0.5 rounded border border-amber-800/40">VITE_SUPABASE_ANON_KEY</code> in Vercel or{' '}
                      <code className="font-mono text-amber-200">frontend/.env</code> to activate authentication.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleClose}
                  className="w-full mt-2 py-1.5 px-3 rounded-lg bg-amber-900/30 hover:bg-amber-900/50 border border-amber-700/40 text-[11px] font-medium text-amber-200 flex items-center justify-center space-x-1.5 transition"
                >
                  <span>Continue Exploring in Guest Mode</span>
                  <ArrowRight className="w-3 h-3 text-amber-300" />
                </button>
              </div>
            )}

            {/* Error Message with Duplicate User Action */}
            {errorMessage && (
              <div className="mb-4 p-3 rounded-xl bg-rose-950/40 border border-rose-800/50 text-xs text-rose-300 animate-in fade-in space-y-2">
                <div className="flex items-start space-x-2">
                  <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5 text-rose-400" />
                  <p className="leading-relaxed flex-1">{errorMessage}</p>
                </div>
                {userExistsError && (
                  <button
                    type="button"
                    onClick={() => handleModeSwitch('signin')}
                    className="w-full mt-1.5 py-1.5 px-3 rounded-lg bg-rose-900/40 hover:bg-rose-900/60 border border-rose-700/50 text-xs font-semibold text-rose-200 flex items-center justify-center space-x-1.5 transition"
                  >
                    <span>Switch to Sign In</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            )}

            {/* Success Notice */}
            {successNotice && (
              <div className="mb-4 p-3 rounded-xl bg-emerald-950/40 border border-emerald-800/50 text-xs text-emerald-300 flex items-center space-x-2 animate-in fade-in">
                <Sparkles className="h-4 w-4 text-emerald-400 flex-shrink-0" />
                <p>{successNotice}</p>
              </div>
            )}

            {/* Auth Form */}
            <form onSubmit={handleSubmit} noValidate className="space-y-3.5">
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
                      disabled={isSubmitting}
                      className="w-full pl-9 pr-3 py-2.5 text-xs sm:text-sm bg-slate-950/90 border border-slate-800 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/50 transition disabled:opacity-50"
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
                    disabled={isSubmitting}
                    className="w-full pl-9 pr-3 py-2.5 text-xs sm:text-sm bg-slate-950/90 border border-slate-800 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/50 transition disabled:opacity-50"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-300">Password</label>
                  {mode === 'signup' && (
                    <span className="text-[10px] text-slate-400">Min 6 characters</span>
                  )}
                </div>
                <div className="relative">
                  <Lock className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
                  <input
                    type="password"
                    required
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={isSubmitting}
                    className="w-full pl-9 pr-3 py-2.5 text-xs sm:text-sm bg-slate-950/90 border border-slate-800 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/50 transition disabled:opacity-50"
                  />
                </div>
              </div>

              {mode === 'signup' && (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-slate-300">Confirm Password</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
                    <input
                      type="password"
                      required
                      placeholder="••••••••"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      disabled={isSubmitting}
                      className="w-full pl-9 pr-3 py-2.5 text-xs sm:text-sm bg-slate-950/90 border border-slate-800 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/50 transition disabled:opacity-50"
                    />
                  </div>
                </div>
              )}

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
                    onClick={() => handleModeSwitch('signup')}
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
                    onClick={() => handleModeSwitch('signin')}
                    className="text-indigo-400 hover:text-indigo-300 font-medium underline underline-offset-2 transition"
                  >
                    Sign in here
                  </button>
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

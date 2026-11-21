/**
 * Authenticated User Menu and Avatar Widget.
 * Clean, professional account presentation with white, black, and emerald accents.
 * Technical debug identifiers (raw database UUIDs and internal RLS markers) are omitted.
 */

import React, { useState, useRef, useEffect } from 'react';
import { LogOut, Settings, ChevronDown } from 'lucide-react';
import { Link } from '@tanstack/react-router';
import { useAuth } from '../../context/AuthContext';

export const UserProfileMenu: React.FC = () => {
  const { user, profile, signOut } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  if (!user) return null;

  const getDisplayName = (): string => {
    if (profile?.full_name?.trim()) return profile.full_name.trim();
    const metaFullName = (user.user_metadata?.full_name || user.user_metadata?.name || '') as string;
    if (metaFullName?.trim()) return metaFullName.trim();
    return 'Commander';
  };

  const displayName = getDisplayName();
  const displayEmail = user.email || 'No email associated';
  const initial = displayName.charAt(0).toUpperCase();

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center space-x-2.5 px-3 py-1.5 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-left transition focus:outline-none focus:ring-2 focus:ring-emerald-500/40 shadow-sm"
      >
        <div className="h-7 w-7 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-700 font-bold text-xs shadow-sm">
          {initial}
        </div>
        <div className="hidden sm:block text-xs">
          <p className="font-semibold text-slate-800 leading-tight truncate max-w-[120px]">{displayName}</p>
          <span className="text-[10px] text-emerald-600 font-semibold">Authenticated</span>
        </div>
        <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-64 rounded-xl bg-white border border-slate-200 shadow-xl py-2 z-50 animate-in fade-in zoom-in-95 duration-150">
          <div className="px-4 py-2.5 border-b border-slate-100">
            <p className="text-xs font-bold text-slate-900 truncate">{displayName}</p>
            <p className="text-[11px] text-slate-500 truncate mt-0.5">{displayEmail}</p>
            <div className="mt-2.5 flex items-center space-x-1.5 text-[10px] text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-md border border-emerald-200 w-fit font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(52,211,153,0.6)] animate-pulse" />
              <span>Account Active</span>
            </div>
          </div>

          <div className="py-1">
            <Link
              to="/settings"
              onClick={() => setIsOpen(false)}
              className="w-full flex items-center space-x-2.5 px-4 py-2 text-xs text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition text-left font-medium"
            >
              <Settings className="h-3.5 w-3.5 text-slate-400" />
              <span>Settings & Preferences</span>
            </Link>
            <button
              onClick={() => {
                setIsOpen(false);
                signOut();
              }}
              className="w-full flex items-center space-x-2.5 px-4 py-2 text-xs text-rose-600 hover:bg-rose-50 hover:text-rose-700 transition text-left font-medium"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

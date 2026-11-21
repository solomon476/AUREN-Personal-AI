/**
 * Authenticated User Menu and Avatar Widget.
 */

import React, { useState, useRef, useEffect } from 'react';
import { LogOut, Shield, ChevronDown } from 'lucide-react';
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

  const displayName = profile?.full_name || user.user_metadata?.full_name || user.email?.split('@')[0] || 'User';
  const displayEmail = user.email || 'No email associated';
  const initial = displayName.charAt(0).toUpperCase();

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center space-x-2.5 px-3 py-1.5 rounded-xl bg-[#0e111a] hover:bg-[#141722] border border-white/[0.08] text-left transition focus:outline-none focus:ring-2 focus:ring-champagne-400/50"
      >
        <div className="h-7 w-7 rounded-lg bg-[#141722] border border-champagne-400/30 flex items-center justify-center text-champagne-300 font-bold text-xs shadow-sm">
          {initial}
        </div>
        <div className="hidden sm:block text-xs">
          <p className="font-semibold text-slate-200 leading-tight truncate max-w-[120px]">{displayName}</p>
          <span className="text-[10px] text-emerald-400 font-medium">Authenticated</span>
        </div>
        <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-64 rounded-xl bg-[#0e111a] border border-white/[0.08] shadow-2xl py-2 z-50 animate-in fade-in zoom-in-95 duration-150">
          <div className="px-4 py-2 border-b border-white/[0.06]">
            <p className="text-xs font-semibold text-white truncate">{displayName}</p>
            <p className="text-[11px] text-slate-400 truncate mt-0.5">{displayEmail}</p>
            <div className="mt-2 flex items-center space-x-1.5 text-[10px] text-indigo-400 bg-indigo-950/40 px-2 py-0.5 rounded border border-indigo-900/60 w-fit">
              <Shield className="h-3 w-3" />
              <span>RLS Protected User ID</span>
            </div>
            <code className="text-[9px] text-slate-500 block mt-1 font-mono truncate" title={user.id}>
              {user.id}
            </code>
          </div>

          <div className="py-1">
            <button
              onClick={() => {
                setIsOpen(false);
                signOut();
              }}
              className="w-full flex items-center space-x-2 px-4 py-2 text-xs text-rose-400 hover:bg-rose-950/30 hover:text-rose-300 transition text-left"
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

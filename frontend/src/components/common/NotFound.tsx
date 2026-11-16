/**
 * 404 Not Found component for unhandled routes.
 */

import React from 'react';
import { AlertCircle, Home } from 'lucide-react';
import { Link } from '@tanstack/react-router';

export const NotFound: React.FC = () => {
  return (
    <div className="min-h-[400px] flex flex-col items-center justify-center text-center p-6 space-y-4">
      <div className="h-14 w-14 rounded-2xl bg-rose-950/40 border border-rose-800/50 flex items-center justify-center text-rose-400 shadow-xl">
        <AlertCircle className="h-7 w-7" />
      </div>
      <div className="space-y-1">
        <h2 className="text-xl font-bold text-white">Page Not Found</h2>
        <p className="text-xs text-slate-400 max-w-sm">
          The requested destination does not exist or has been moved.
        </p>
      </div>
      <Link
        to="/chat"
        className="flex items-center space-x-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold shadow-lg shadow-indigo-600/30 transition"
      >
        <Home className="h-3.5 w-3.5" />
        <span>Return to AI Chat</span>
      </Link>
    </div>
  );
};

/**
 * Reusable placeholder view for planned capabilities.
 * Presents honest, transparent status of backend foundation and roadmap phase.
 */

import React from 'react';
import { LucideIcon, Sparkles, CheckCircle2, ArrowRight } from 'lucide-react';
import { Link } from '@tanstack/react-router';

interface SectionPlaceholderProps {
  title: string;
  icon: LucideIcon;
  badge: string;
  phase: string;
  description: string;
  backendStatus: string;
  plannedFeatures: string[];
}

export const SectionPlaceholder: React.FC<SectionPlaceholderProps> = ({
  title,
  icon: Icon,
  badge,
  phase,
  description,
  backendStatus,
  plannedFeatures,
}) => {
  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-in fade-in duration-200">
      {/* Banner */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 sm:p-8 relative overflow-hidden backdrop-blur">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center space-x-4">
            <div className="h-12 w-12 rounded-2xl bg-indigo-950/80 border border-indigo-800/60 flex items-center justify-center text-indigo-400 shadow-xl">
              <Icon className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-xl sm:text-2xl font-bold text-white">{title}</h1>
                <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-800/50">
                  {badge}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 max-w-xl">{description}</p>
            </div>
          </div>
          <Link
            to="/chat"
            className="flex items-center space-x-1.5 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition"
          >
            <span>Open AI Chat</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>

      {/* Backend Foundation Status */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-5 space-y-3">
          <div className="flex items-center space-x-2 text-indigo-400">
            <Sparkles className="h-4 w-4" />
            <h3 className="text-sm font-semibold text-white">Engineering Status</h3>
          </div>
          <div className="bg-slate-950/80 p-3 rounded-lg border border-slate-800 text-xs text-slate-300 font-mono">
            {backendStatus}
          </div>
          <p className="text-xs text-slate-400">
            Target Milestone: <strong className="text-white font-medium">{phase}</strong>
          </p>
        </div>

        <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-white">Planned Capabilities</h3>
          <ul className="space-y-2">
            {plannedFeatures.map((feat, idx) => (
              <li key={idx} className="flex items-center space-x-2 text-xs text-slate-300">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 flex-shrink-0" />
                <span>{feat}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};

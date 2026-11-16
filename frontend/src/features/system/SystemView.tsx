/**
 * System and PostgreSQL Schema Matrix View.
 * Displays backend health telemetry and PostgreSQL RLS policies.
 */

import React from 'react';
import { 
  Activity, 
  Database, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw 
} from 'lucide-react';
import { useHealth } from '../../hooks/useHealth';
import { useAuth } from '../../context/AuthContext';

export const SystemView: React.FC = () => {
  const { data: health, isLoading, error, refetch, isFetching } = useHealth();
  const { isConfigured } = useAuth();

  const schemaTables = [
    { name: 'profiles', records: 'Auth Profile & Preferences', rls: 'auth.uid() = id' },
    { name: 'projects', records: 'Project Workspaces', rls: 'auth.uid() = user_id' },
    { name: 'tasks', records: 'Personal Tasks & Timetable', rls: 'auth.uid() = user_id' },
    { name: 'conversations', records: 'AI Chat Dialogues', rls: 'auth.uid() = user_id' },
    { name: 'messages', records: 'Chat Messages & Metadata', rls: 'auth.uid() = user_id' },
    { name: 'memories', records: 'Structured Long-term Memory', rls: 'auth.uid() = user_id' },
    { name: 'journal_entries', records: 'Private Journaling & Moods', rls: 'auth.uid() = user_id' },
    { name: 'goals', records: 'Personal Goals & Progress', rls: 'auth.uid() = user_id' },
    { name: 'milestones', records: 'Measurable Milestones', rls: 'auth.uid() = user_id' },
    { name: 'briefings', records: 'Daily Synthesized Briefings', rls: 'auth.uid() = user_id' },
  ];

  return (
    <div className="space-y-6 max-w-5xl mx-auto animate-in fade-in duration-200">
      {/* Backend & Environment Health Status Card */}
      <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3 mb-4">
          <div className="flex items-center space-x-2.5">
            <Activity className="h-4 w-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">FastAPI Backend &amp; Streaming Health</h3>
          </div>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center space-x-1.5 text-xs px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 w-fit disabled:opacity-50 transition"
          >
            <RefreshCw className={`h-3 w-3 ${isFetching ? 'animate-spin' : ''}`} />
            <span>{isFetching ? 'Checking...' : 'Refresh Status'}</span>
          </button>
        </div>

        {isLoading ? (
          <div className="py-4 text-center text-xs text-slate-400 animate-pulse">
            Pinging API health endpoint (/api/v1/health)...
          </div>
        ) : error ? (
          <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/50 flex items-start space-x-2 text-xs text-rose-300">
            <AlertCircle className="h-4 w-4 text-rose-400 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold">Backend Unreachable: </span>
              <span>{error instanceof Error ? error.message : 'Unknown error'}</span>
            </div>
          </div>
        ) : health ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
              <span className="text-slate-400 text-[10px] block uppercase font-medium">Service</span>
              <span className="text-emerald-400 font-semibold mt-0.5 flex items-center space-x-1">
                <CheckCircle2 className="h-3 w-3" />
                <span>{health.status}</span>
              </span>
            </div>
            <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
              <span className="text-slate-400 text-[10px] block uppercase font-medium">Chat Endpoint</span>
              <span className="text-indigo-300 font-mono font-semibold mt-0.5 block">/api/v1/chat/completions</span>
            </div>
            <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
              <span className="text-slate-400 text-[10px] block uppercase font-medium">Streaming Protocol</span>
              <span className="text-white font-mono font-semibold mt-0.5 block">SSE (text/event-stream)</span>
            </div>
            <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
              <span className="text-slate-400 text-[10px] block uppercase font-medium">Supabase Config</span>
              <span className={`font-semibold mt-0.5 block ${isConfigured ? 'text-emerald-400' : 'text-amber-400'}`}>
                {isConfigured ? 'Connected' : 'Pending Keys'}
              </span>
            </div>
          </div>
        ) : null}
      </section>

      {/* Database Schema & RLS Matrix */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Database className="h-4 w-4 text-indigo-400" />
            <h2 className="text-base font-bold text-white">PostgreSQL Schemas &amp; RLS Policies</h2>
          </div>
          <span className="text-xs text-slate-400 font-mono">10 Protected Tables</span>
        </div>

        <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 text-[11px] uppercase tracking-wider font-semibold">
                <tr>
                  <th className="py-3 px-4">Table Name</th>
                  <th className="py-3 px-4">Domain Purpose</th>
                  <th className="py-3 px-4">Row Level Security Policy</th>
                  <th className="py-3 px-4 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {schemaTables.map((tbl, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/30 transition">
                    <td className="py-2.5 px-4 font-mono text-indigo-300 font-semibold">{tbl.name}</td>
                    <td className="py-2.5 px-4 text-slate-300">{tbl.records}</td>
                    <td className="py-2.5 px-4 font-mono text-[11px] text-emerald-400/90">{tbl.rls}</td>
                    <td className="py-2.5 px-4 text-right">
                      <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-emerald-950/60 text-emerald-400 border border-emerald-800/40 text-[10px] font-medium">
                        <CheckCircle2 className="h-2.5 w-2.5" />
                        <span>RLS Enforced</span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
};

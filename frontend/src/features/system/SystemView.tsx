/**
 * System and PostgreSQL Schema Matrix View.
 * Displays backend health telemetry and PostgreSQL RLS policies.
 * Elevated with AUREN Obsidian & Champagne Design System.
 */

import React from 'react';
import { 
  Activity, 
  Database, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw,
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
    { name: 'record_links', records: 'Cross-Entity Graph Relationships', rls: 'auth.uid() = user_id (Trigger Verified)' },
    { name: 'chat_requests', records: 'Idempotency & Lifecycle Leases', rls: 'auth.uid() = user_id' },
    { name: 'journal_entries', records: 'Private Journaling & Moods', rls: 'auth.uid() = user_id' },
    { name: 'goals', records: 'Personal Goals & Progress', rls: 'auth.uid() = user_id' },
  ];

  return (
    <div className="space-y-6 max-w-5xl mx-auto animate-in fade-in duration-200">
      {/* Backend & Environment Health Status Card */}
      <section className="bg-[#0e111a]/80 border border-white/[0.07] rounded-2xl p-6 shadow-subtle-elevation backdrop-blur">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/[0.07] pb-4 mb-4">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-xl bg-champagne-500/10 border border-champagne-500/20 text-champagne-400">
              <Activity className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white tracking-tight">FastAPI Backend &amp; Streaming Health</h3>
              <p className="text-xs text-slate-400">Live operational status and service endpoints</p>
            </div>
          </div>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-200 border border-white/[0.08] w-fit disabled:opacity-50 transition shadow-sm"
          >
            <RefreshCw className={`h-3 w-3 ${isFetching ? 'animate-spin' : ''}`} />
            <span>{isFetching ? 'Checking...' : 'Refresh Status'}</span>
          </button>
        </div>

        {isLoading ? (
          <div className="py-6 text-center text-xs text-slate-400 animate-pulse font-mono">
            Pinging API health endpoint (/api/v1/health)...
          </div>
        ) : error ? (
          <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/50 flex items-start space-x-2.5 text-xs text-rose-300">
            <AlertCircle className="h-4 w-4 text-rose-400 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold">Backend Unreachable: </span>
              <span>{error instanceof Error ? error.message : 'Unknown error'}</span>
            </div>
          </div>
        ) : health ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="bg-[#07080c]/80 p-3.5 rounded-xl border border-white/[0.07]">
              <span className="text-slate-400 text-[10px] block uppercase font-mono">Service</span>
              <span className="text-emerald-400 font-semibold mt-1 flex items-center space-x-1.5">
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>{health.status}</span>
              </span>
            </div>
            <div className="bg-[#07080c]/80 p-3.5 rounded-xl border border-white/[0.07]">
              <span className="text-slate-400 text-[10px] block uppercase font-mono">Chat Endpoint</span>
              <span className="text-champagne-300 font-mono font-semibold mt-1 block">/api/v1/chat/completions</span>
            </div>
            <div className="bg-[#07080c]/80 p-3.5 rounded-xl border border-white/[0.07]">
              <span className="text-slate-400 text-[10px] block uppercase font-mono">Streaming Protocol</span>
              <span className="text-white font-mono font-semibold mt-1 block">SSE (text/event-stream)</span>
            </div>
            <div className="bg-[#07080c]/80 p-3.5 rounded-xl border border-white/[0.07]">
              <span className="text-slate-400 text-[10px] block uppercase font-mono">Supabase Config</span>
              <span className={`font-semibold mt-1 block ${isConfigured ? 'text-emerald-400' : 'text-amber-400'}`}>
                {isConfigured ? 'Connected' : 'Pending Keys'}
              </span>
            </div>
          </div>
        ) : null}
      </section>

      {/* Database Schema & RLS Matrix */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-xl bg-champagne-500/10 border border-champagne-500/20 text-champagne-400">
              <Database className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">PostgreSQL Schemas &amp; RLS Policies</h2>
              <p className="text-xs text-slate-400">Row Level Security boundary isolation matrix</p>
            </div>
          </div>
          <span className="text-xs text-champagne-300 font-mono px-2.5 py-1 rounded-lg bg-[#0e111a] border border-white/[0.08]">
            10 Protected Tables
          </span>
        </div>

        <div className="bg-[#0e111a]/80 border border-white/[0.07] rounded-2xl overflow-hidden shadow-subtle-elevation">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#07080c]/90 text-slate-400 border-b border-white/[0.07] text-[11px] uppercase tracking-wider font-semibold font-mono">
                <tr>
                  <th className="py-3 px-4">Table Name</th>
                  <th className="py-3 px-4">Domain Purpose</th>
                  <th className="py-3 px-4">Row Level Security Policy</th>
                  <th className="py-3 px-4 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {schemaTables.map((tbl, idx) => (
                  <tr key={idx} className="hover:bg-white/[0.02] transition-colors">
                    <td className="py-3 px-4 font-mono text-champagne-300 font-semibold">{tbl.name}</td>
                    <td className="py-3 px-4 text-slate-300">{tbl.records}</td>
                    <td className="py-3 px-4 font-mono text-[11px] text-emerald-400/90">{tbl.rls}</td>
                    <td className="py-3 px-4 text-right">
                      <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full bg-emerald-950/60 text-emerald-400 border border-emerald-800/40 text-[10px] font-medium font-mono">
                        <CheckCircle2 className="h-3 w-3" />
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

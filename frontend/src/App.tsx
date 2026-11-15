import { useEffect, useState } from 'react';
import { 
  Bot, 
  Activity, 
  Database, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw, 
  LogIn, 
  KeyRound, 
  MessageSquare, 
  LayoutDashboard 
} from 'lucide-react';
import { fetchHealth } from './api/health';
import { HealthResponse } from './api/types';
import { AuthProvider, useAuth } from './context/AuthContext';
import { AuthModal } from './components/auth/AuthModal';
import { UserProfileMenu } from './components/auth/UserProfileMenu';
import { ChatView } from './features/chat/ChatView';

function MainLayout() {
  const { user, profile, isConfigured } = useAuth();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isLoadingHealth, setIsLoadingHealth] = useState<boolean>(true);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState<'signin' | 'signup'>('signin');
  const [activeTab, setActiveTab] = useState<'chat' | 'system'>('chat');

  const checkBackendHealth = async () => {
    setIsLoadingHealth(true);
    setHealthError(null);
    try {
      const data = await fetchHealth();
      setHealth(data);
    } catch (err) {
      setHealthError(err instanceof Error ? err.message : 'Failed to connect to backend');
      setHealth(null);
    } finally {
      setIsLoadingHealth(false);
    }
  };

  useEffect(() => {
    checkBackendHealth();
  }, []);

  const openAuth = (mode: 'signin' | 'signup') => {
    setAuthMode(mode);
    setIsAuthModalOpen(true);
  };

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
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Navigation Bar */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-sky-500 p-0.5 flex items-center justify-center text-white shadow-lg shadow-indigo-600/20">
              <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
                <Bot className="h-5 w-5 text-indigo-400" />
              </div>
            </div>
            <div>
              <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-indigo-400 via-sky-300 to-emerald-400 bg-clip-text text-transparent">
                AUREN
              </span>
              <span className="hidden sm:inline-block ml-2 text-[10px] text-slate-400 uppercase tracking-widest font-semibold px-2 py-0.5 bg-slate-800 rounded">
                Phase 3A
              </span>
            </div>
          </div>

          {/* Navigation Mode Tabs */}
          {user && (
            <div className="hidden md:flex items-center space-x-1 bg-slate-950/80 p-1 rounded-xl border border-slate-800">
              <button
                onClick={() => setActiveTab('chat')}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                  activeTab === 'chat'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <MessageSquare className="h-3.5 w-3.5" />
                <span>AI Assistant (Streaming)</span>
              </button>
              <button
                onClick={() => setActiveTab('system')}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                  activeTab === 'system'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <LayoutDashboard className="h-3.5 w-3.5" />
                <span>System &amp; Database</span>
              </button>
            </div>
          )}

          <div className="flex items-center space-x-3">
            {user ? (
              <UserProfileMenu />
            ) : (
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => openAuth('signin')}
                  className="px-3 py-1.5 text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition"
                >
                  Sign In
                </button>
                <button
                  onClick={() => openAuth('signup')}
                  className="px-3.5 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg shadow-md shadow-indigo-600/30 transition flex items-center space-x-1.5"
                >
                  <LogIn className="h-3.5 w-3.5" />
                  <span>Get Started</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Workspace Body */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {user && activeTab === 'chat' ? (
          <div className="space-y-4">
            {/* Active Workspace Pill */}
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center space-x-2 text-xs text-slate-400">
                <span className="h-2 w-2 rounded-full bg-emerald-400"></span>
                <span>Signed in as <strong className="text-white font-medium">{profile?.full_name || user.email}</strong></span>
              </div>
              <button
                onClick={() => setActiveTab('system')}
                className="text-xs text-indigo-400 hover:text-indigo-300 transition"
              >
                View Database &amp; System Health &rarr;
              </button>
            </div>

            {/* Conversational Stream Interface */}
            <ChatView />
          </div>
        ) : (
          <div className="space-y-8">
            {/* Identity & Session Banner */}
            {user ? (
              <section className="bg-gradient-to-r from-indigo-950/40 via-slate-900/60 to-emerald-950/30 border border-indigo-900/50 rounded-2xl p-6 shadow-xl backdrop-blur relative overflow-hidden">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center space-x-2">
                      <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                      <span className="text-xs uppercase tracking-wider font-semibold text-emerald-400">
                        Active Session Verified
                      </span>
                    </div>
                    <h2 className="text-xl font-bold text-white">
                      Welcome, {profile?.full_name || user.email}!
                    </h2>
                    <p className="text-xs text-slate-400 flex items-center space-x-2">
                      <span>User ID:</span>
                      <code className="bg-slate-950 px-2 py-0.5 rounded text-indigo-300 font-mono text-[11px]">
                        {user.id}
                      </code>
                    </p>
                  </div>
                  <button
                    onClick={() => setActiveTab('chat')}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold shadow-lg shadow-indigo-600/30 transition flex items-center space-x-2 w-fit"
                  >
                    <MessageSquare className="h-4 w-4" />
                    <span>Open AI Assistant</span>
                  </button>
                </div>
              </section>
            ) : (
              <section className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 sm:p-8 text-center sm:text-left flex flex-col sm:flex-row items-center justify-between gap-6">
                <div className="space-y-2 max-w-2xl">
                  <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-full bg-indigo-950/60 border border-indigo-800/40 text-indigo-300 text-xs font-medium">
                    <KeyRound className="h-3.5 w-3.5" />
                    <span>Phase 3A: Persistent Chat &amp; SSE Streaming</span>
                  </div>
                  <h1 className="text-2xl sm:text-3xl font-extrabold text-white">
                    Private Personal AI with Verified Streaming
                  </h1>
                  <p className="text-sm text-slate-400">
                    Sign in to test conversational streaming. Every message is saved with strict ownership isolation
                    and network request deduplication.
                  </p>
                </div>
                <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
                  <button
                    onClick={() => openAuth('signup')}
                    className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold shadow-lg shadow-indigo-600/30 transition text-center"
                  >
                    Create Account
                  </button>
                  <button
                    onClick={() => openAuth('signin')}
                    className="px-5 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold border border-slate-700 transition text-center"
                  >
                    Sign In
                  </button>
                </div>
              </section>
            )}

            {/* Backend & Environment Health Status Card */}
            <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 shadow-lg backdrop-blur">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3 mb-4">
                <div className="flex items-center space-x-2.5">
                  <Activity className="h-4 w-4 text-indigo-400" />
                  <h3 className="text-sm font-semibold text-white">FastAPI Backend &amp; Streaming Health</h3>
                </div>
                <button
                  onClick={checkBackendHealth}
                  disabled={isLoadingHealth}
                  className="inline-flex items-center space-x-1.5 text-xs px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 w-fit disabled:opacity-50 transition"
                >
                  <RefreshCw className={`h-3 w-3 ${isLoadingHealth ? 'animate-spin' : ''}`} />
                  <span>{isLoadingHealth ? 'Checking...' : 'Refresh Status'}</span>
                </button>
              </div>

              {isLoadingHealth ? (
                <div className="py-4 text-center text-xs text-slate-400 animate-pulse">
                  Pinging API health endpoint (/api/v1/health)...
                </div>
              ) : healthError ? (
                <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/50 flex items-start space-x-2 text-xs text-rose-300">
                  <AlertCircle className="h-4 w-4 text-rose-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold">Backend Unreachable: </span>
                    <span>{healthError}</span>
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
        )}
      </main>

      {/* Auth Modal */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        defaultMode={authMode}
      />

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/80 py-6 text-center text-xs text-slate-500">
        <p>AUREN Personal AI Assistant &bull; Phase 3A Persistent Chat &amp; Streaming</p>
      </footer>
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <MainLayout />
    </AuthProvider>
  );
}

export default App;

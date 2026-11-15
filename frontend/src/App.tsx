import { useEffect, useState } from 'react';
import { 
  Bot, 
  Activity, 
  Database, 
  ShieldCheck, 
  Calendar, 
  BookOpen, 
  Target, 
  Sparkles, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw 
} from 'lucide-react';
import { fetchHealth } from './api/health';
import { HealthResponse } from './api/types';

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const checkBackendHealth = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchHealth();
      setHealth(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect to backend');
      setHealth(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    checkBackendHealth();
  }, []);

  const features = [
    {
      icon: Bot,
      title: 'Conversational Intelligence',
      description: 'Pluggable LLM architecture supporting multiple model backends with streaming responses.',
      status: 'Planned (Phase 3)',
    },
    {
      icon: Database,
      title: 'Semantic Long-term Memory',
      description: 'Dynamic vector memory using PostgreSQL and pgvector for persistent user context.',
      status: 'Planned (Phase 3)',
    },
    {
      icon: Calendar,
      title: 'Tasks & Timetable Planning',
      description: 'Unified schedule management, priorities, and daily calendar orchestration.',
      status: 'Planned (Phase 4)',
    },
    {
      icon: BookOpen,
      title: 'Private Journaling',
      description: 'Encrypted reflections and emotional context tracking with strict privacy boundaries.',
      status: 'Planned (Phase 4)',
    },
    {
      icon: Target,
      title: 'Goals & Progress Tracking',
      description: 'Hierarchical milestone decomposition and progress monitoring.',
      status: 'Planned (Phase 4)',
    },
    {
      icon: Sparkles,
      title: 'Daily Briefings',
      description: 'Proactive context synthesis combining daily agenda, milestones, and reflections.',
      status: 'Planned (Phase 5)',
    },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="h-9 w-9 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-indigo-400 to-cyan-400 bg-clip-text text-transparent">
                AUREN
              </span>
              <span className="hidden sm:inline-block ml-2 text-xs text-slate-400 uppercase tracking-wider font-semibold">
                Personal AI Platform
              </span>
            </div>
          </div>
          <div className="flex items-center space-x-3">
            <span className="text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700 font-mono">
              Phase 1: Scaffolding
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 sm:py-12 space-y-10">
        {/* Hero Section */}
        <section className="text-center sm:text-left space-y-4">
          <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-white">
            Independent, Intelligent <br className="hidden sm:inline" />
            <span className="bg-gradient-to-r from-indigo-400 via-sky-300 to-emerald-400 bg-clip-text text-transparent">
              Personal AI Assistant
            </span>
          </h1>
          <p className="text-base sm:text-lg text-slate-400 max-w-3xl">
            AUREN is built for structured long-term memory, daily briefings, private journaling,
            and personal productivity with strict data isolation.
          </p>
        </section>

        {/* Backend Health & Connectivity Card */}
        <section className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-xl backdrop-blur">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4 mb-4">
            <div className="flex items-center space-x-3">
              <Activity className="h-5 w-5 text-indigo-400" />
              <h2 className="text-lg font-semibold text-white">Backend Health & API Status</h2>
            </div>
            <button
              onClick={checkBackendHealth}
              disabled={isLoading}
              className="inline-flex items-center space-x-2 text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition border border-slate-700 w-fit disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              <span>{isLoading ? 'Checking...' : 'Check Status'}</span>
            </button>
          </div>

          {isLoading ? (
            <div className="py-6 text-center text-slate-400 text-sm">
              <span className="inline-block animate-pulse">Connecting to FastAPI backend (/api/v1/health)...</span>
            </div>
          ) : error ? (
            <div className="flex items-start space-x-3 p-4 rounded-lg bg-rose-950/40 border border-rose-800/50 text-rose-300">
              <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5 text-rose-400" />
              <div className="text-sm">
                <p className="font-semibold">Backend Unreachable</p>
                <p className="text-rose-400/80 text-xs mt-0.5">{error}</p>
                <p className="text-xs text-slate-400 mt-2">
                  Start the backend with: <code className="bg-slate-950 px-1.5 py-0.5 rounded text-slate-300 font-mono">cd backend &amp;&amp; .venv/bin/uvicorn app.main:app --port 8000</code>
                </p>
              </div>
            </div>
          ) : health ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/60">
                <span className="text-xs text-slate-400 block font-medium">Service Status</span>
                <div className="flex items-center space-x-2 mt-1">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  <span className="text-sm font-semibold text-emerald-400 uppercase tracking-wide">
                    {health.status}
                  </span>
                </div>
              </div>
              <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/60">
                <span className="text-xs text-slate-400 block font-medium">API Version</span>
                <span className="text-sm font-semibold text-white mt-1 block font-mono">
                  v{health.version}
                </span>
              </div>
              <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/60">
                <span className="text-xs text-slate-400 block font-medium">Environment</span>
                <span className="text-sm font-semibold text-white mt-1 block capitalize">
                  {health.environment}
                </span>
              </div>
              <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/60">
                <span className="text-xs text-slate-400 block font-medium">Verified At</span>
                <span className="text-xs text-slate-300 mt-1 block font-mono truncate" title={health.timestamp}>
                  {new Date(health.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
          ) : null}
        </section>

        {/* Feature Roadmap & Architecture Matrix */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white flex items-center space-x-2">
              <ShieldCheck className="h-5 w-5 text-indigo-400" />
              <span>Planned Platform Capabilities</span>
            </h2>
            <span className="text-xs text-slate-400">Strict User Isolation</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map((feature, idx) => {
              const Icon = feature.icon;
              return (
                <div
                  key={idx}
                  className="bg-slate-900/60 border border-slate-800 hover:border-slate-700/80 rounded-xl p-5 transition flex flex-col justify-between space-y-3"
                >
                  <div className="space-y-2">
                    <div className="h-8 w-8 rounded-lg bg-indigo-950/60 border border-indigo-800/40 flex items-center justify-center text-indigo-400">
                      <Icon className="h-4 w-4" />
                    </div>
                    <h3 className="font-semibold text-white text-base">{feature.title}</h3>
                    <p className="text-sm text-slate-400 leading-relaxed">{feature.description}</p>
                  </div>
                  <div className="pt-2 border-t border-slate-800/60">
                    <span className="text-xs px-2 py-0.5 rounded bg-slate-800/80 text-slate-400 font-medium font-mono">
                      {feature.status}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/80 py-6 text-center text-xs text-slate-500">
        <p>AUREN Personal AI Assistant &bull; Phase 1 Verified</p>
      </footer>
    </div>
  );
}

export default App;


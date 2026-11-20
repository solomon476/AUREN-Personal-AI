/**
 * Settings & Preferences Management View.
 * Real, operational configuration for Account, AI Persona & Model,
 * Memory Controls, Privacy Guarantees, and GDPR Data Export.
 * Elevated with AUREN Obsidian & Champagne Design System.
 */

import React, { useEffect, useState, useRef } from 'react';
import {
  Settings,
  User,
  Bot,
  Brain,
  Download,
  Save,
  CheckCircle2,
  Database,
  Lock,
  LogOut,
  Cpu,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useTheme, ThemeMode } from '../../context/ThemeContext';
import { useExportUserData, useUpdateUserProfile, useUserProfile } from '../../hooks/useSettings';

export const SettingsView: React.FC = () => {
  const { user, signOut } = useAuth();
  const { data: profile } = useUserProfile(user?.id);
  const updateProfileMutation = useUpdateUserProfile(user?.id);
  const exportDataMutation = useExportUserData();

  // Tab State
  const [activeTab, setActiveTab] = useState<'profile' | 'ai' | 'memory' | 'data'>('profile');

  // Form State
  const [fullName, setFullName] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const { theme, setTheme } = useTheme();
  const [aiModel, setAiModel] = useState('gemini-2.5-flash');
  const [aiTone, setAiTone] = useState('concise');
  const [aiCustomInstructions, setAiCustomInstructions] = useState('');
  const [memoryAutoExtraction, setMemoryAutoExtraction] = useState(true);
  const [memoryMinConfidence, setMemoryMinConfidence] = useState(0.7);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const hasSyncedRef = useRef(false);

  // Sync profile data when loaded
  useEffect(() => {
    if (profile && !hasSyncedRef.current) {
      hasSyncedRef.current = true;
      setFullName(profile.full_name || '');
      setAvatarUrl(profile.avatar_url || '');
      const prefs = profile.preferences || {};
      if (prefs.theme && ['dark', 'midnight', 'obsidian'].includes(String(prefs.theme))) {
        setTheme(prefs.theme as ThemeMode);
      }
      if (prefs.ai_model) setAiModel(String(prefs.ai_model));
      if (prefs.ai_tone) setAiTone(String(prefs.ai_tone));
      if (prefs.ai_custom_instructions) setAiCustomInstructions(String(prefs.ai_custom_instructions));
      if (prefs.memory_auto_extraction !== undefined) setMemoryAutoExtraction(Boolean(prefs.memory_auto_extraction));
      if (prefs.memory_min_confidence !== undefined) setMemoryMinConfidence(Number(prefs.memory_min_confidence));
    }
  }, [profile, setTheme]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveStatus(null);
    try {
      await updateProfileMutation.mutateAsync({
        full_name: fullName.trim() || undefined,
        avatar_url: avatarUrl.trim() || undefined,
        preferences: {
          theme,
          ai_model: aiModel,
          ai_tone: aiTone,
          ai_custom_instructions: aiCustomInstructions.trim() || undefined,
          memory_auto_extraction: memoryAutoExtraction,
          memory_min_confidence: memoryMinConfidence,
        },
      });
      setSaveStatus('Settings saved successfully.');
      setTimeout(() => setSaveStatus(null), 3000);
    } catch (err: any) {
      setSaveStatus(`Failed to save: ${err.message || 'Unknown error'}`);
    }
  };

  const handleExportData = async () => {
    setExportStatus('Generating complete personal data export...');
    try {
      const data = await exportDataMutation.mutateAsync();
      const jsonBlob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const downloadUrl = URL.createObjectURL(jsonBlob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `auren_data_export_${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(downloadUrl);
      setExportStatus('Data export downloaded successfully.');
      setTimeout(() => setExportStatus(null), 3500);
    } catch (err: any) {
      setExportStatus(`Export failed: ${err.message}`);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden text-slate-100">
      {/* Top Banner */}
      <div className="px-6 py-4.5 border-b border-slate-800/80 bg-slate-900/40 backdrop-blur flex items-center justify-between">
        <div className="flex items-center space-x-3.5">
          <div className="p-2.5 rounded-xl bg-slate-800/80 border border-slate-700/80 text-slate-300 shadow-sm">
            <Settings className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold tracking-tight text-slate-100">Settings &amp; Preferences</h1>
              <span className="hidden sm:inline-flex text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                AUREN Configuration
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Configure your personal AI operating system, privacy boundaries, and model parameters.
            </p>
          </div>
        </div>
      </div>

      {/* Main Container */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Navigation Tabs */}
        <div className="w-full md:w-64 border-r border-slate-800/80 p-4 space-y-1.5 bg-slate-950">
          <button
            onClick={() => setActiveTab('profile')}
            className={`w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 ${
              activeTab === 'profile'
                ? 'bg-gradient-to-r from-indigo-600 to-indigo-500 text-white shadow-md shadow-indigo-600/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-900/70'
            }`}
          >
            <User className="w-4 h-4" />
            <span>Profile &amp; Account</span>
          </button>

          <button
            onClick={() => setActiveTab('ai')}
            className={`w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 ${
              activeTab === 'ai'
                ? 'bg-gradient-to-r from-indigo-600 to-indigo-500 text-white shadow-md shadow-indigo-600/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-900/70'
            }`}
          >
            <Bot className="w-4 h-4" />
            <span>AI Model &amp; Tone</span>
          </button>

          <button
            onClick={() => setActiveTab('memory')}
            className={`w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 ${
              activeTab === 'memory'
                ? 'bg-gradient-to-r from-indigo-600 to-indigo-500 text-white shadow-md shadow-indigo-600/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-900/70'
            }`}
          >
            <Brain className="w-4 h-4" />
            <span>Memory &amp; Privacy</span>
          </button>

          <button
            onClick={() => setActiveTab('data')}
            className={`w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 ${
              activeTab === 'data'
                ? 'bg-gradient-to-r from-indigo-600 to-indigo-500 text-white shadow-md shadow-indigo-600/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-900/70'
            }`}
          >
            <Database className="w-4 h-4" />
            <span>Data Management &amp; Export</span>
          </button>
        </div>

        {/* Tab Content Panel */}
        <div className="flex-1 overflow-y-auto p-6 max-w-3xl scrollbar-thin">
          <form onSubmit={handleSave} className="space-y-6">
            {saveStatus && (
              <div className="p-3.5 rounded-xl bg-indigo-950/40 border border-indigo-800/60 text-xs text-indigo-200 flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-indigo-400" />
                <span>{saveStatus}</span>
              </div>
            )}

            {/* PROFILE TAB */}
            {activeTab === 'profile' && (
              <div className="space-y-5">
                <div className="border-b border-slate-800/80 pb-3">
                  <h2 className="text-sm font-semibold text-slate-100">User Identity &amp; Profile</h2>
                  <p className="text-xs text-slate-400">Manage your display identity and account credentials.</p>
                </div>

                <div className="space-y-3.5">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">User ID (UUID)</label>
                    <input
                      type="text"
                      disabled
                      value={user?.id || profile?.id || 'Not authenticated'}
                      className="w-full bg-slate-900/40 border border-slate-800/80 rounded-xl px-3.5 py-2 text-xs font-mono text-slate-400 select-all"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Email Address</label>
                    <input
                      type="email"
                      disabled
                      value={user?.email || profile?.email || ''}
                      className="w-full bg-slate-900/40 border border-slate-800/80 rounded-xl px-3.5 py-2 text-xs text-slate-300"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Full Name</label>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Your name..."
                      className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Avatar URL</label>
                    <input
                      type="url"
                      value={avatarUrl}
                      onChange={(e) => setAvatarUrl(e.target.value)}
                      placeholder="https://..."
                      className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Theme</label>
                    <select
                      value={theme}
                      onChange={(e) => setTheme(e.target.value as ThemeMode)}
                      className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                    >
                      <option value="dark">Dark Slate (Default)</option>
                      <option value="midnight">Midnight Indigo (Deep Contrast)</option>
                      <option value="obsidian">Pure Obsidian (OLED Black)</option>
                    </select>
                  </div>
                </div>

                {/* Session Management */}
                {user && (
                  <div className="pt-4 border-t border-slate-800/80 space-y-3">
                    <h3 className="text-xs font-semibold text-slate-300">Active Session</h3>
                    <div className="flex items-center justify-between p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                      <div>
                        <span className="text-xs text-slate-200 block font-medium">Logged in as {user.email}</span>
                        <span className="text-[10px] text-slate-500 font-mono">Role: {user.role || 'authenticated'}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => signOut()}
                        className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-rose-950/60 hover:text-rose-300 hover:border-rose-800/40 text-slate-300 text-xs font-medium transition border border-slate-700"
                      >
                        <LogOut className="w-3.5 h-3.5" />
                        <span>Sign Out</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* AI MODEL TAB */}
            {activeTab === 'ai' && (
              <div className="space-y-5">
                <div className="border-b border-slate-800/80 pb-3">
                  <h2 className="text-sm font-semibold text-slate-100">AI Model &amp; Communication Preferences</h2>
                  <p className="text-xs text-slate-400">Control how AUREN reasons, analyzes, and responds.</p>
                </div>

                <div className="space-y-3.5">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Default AI Model</label>
                    <select
                      value={aiModel}
                      onChange={(e) => setAiModel(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                    >
                      <option value="gemini-2.5-flash">Google Gemini 2.5 Flash (Fast, High Intelligence, Native)</option>
                      <option value="gemini-2.5-pro">Google Gemini 2.5 Pro (Deep Reasoning &amp; Complex Analysis)</option>
                      <option value="gemini-2.0-flash">Google Gemini 2.0 Flash (High Throughput &amp; Low Latency)</option>
                      <option value="mock">Local Development Mock (Offline testing)</option>
                    </select>
                    {!['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash', 'mock'].includes(aiModel) && (
                      <p className="text-[11px] text-amber-400 mt-1">
                        Currently saved model ({aiModel}) is not supported by the operational Gemini provider. Please select a supported model above.
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Communication Style / Tone</label>
                    <select
                      value={aiTone}
                      onChange={(e) => setAiTone(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 transition"
                    >
                      <option value="concise">Concise &amp; Direct (Clear, structured, minimal fluff)</option>
                      <option value="thoughtful">Thoughtful &amp; Socratic (Probing questions, reflective)</option>
                      <option value="detailed">Exhaustive &amp; Technical (Deep breakdowns, high precision)</option>
                      <option value="executive">Executive Brief (Action items, decisions, summaries)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">
                      Custom System Instructions
                    </label>
                    <textarea
                      value={aiCustomInstructions}
                      onChange={(e) => setAiCustomInstructions(e.target.value)}
                      placeholder="Specific preferences, goals, or instructions you want AUREN to always keep in mind..."
                      rows={4}
                      className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 leading-relaxed transition"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* MEMORY & PRIVACY TAB */}
            {activeTab === 'memory' && (
              <div className="space-y-5">
                <div className="border-b border-slate-800/80 pb-3">
                  <h2 className="text-sm font-semibold text-slate-100">Memory &amp; Privacy Policies</h2>
                  <p className="text-xs text-slate-400">Configure what AUREN remembers and inspect security invariants.</p>
                </div>

                <div className="space-y-4">
                  <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold text-slate-200 block">Automatic Memory Extraction</span>
                      <span className="text-[11px] text-slate-400">
                        Allow the background pipeline to extract persistent facts from conversations.
                      </span>
                    </div>
                    <input
                      type="checkbox"
                      checked={memoryAutoExtraction}
                      onChange={(e) => setMemoryAutoExtraction(e.target.checked)}
                      className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 bg-slate-950 border-slate-700"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                      <span>Minimum Extraction Confidence</span>
                      <span className="font-mono text-indigo-400">{Math.round(memoryMinConfidence * 100)}%</span>
                    </div>
                    <input
                      type="range"
                      min={0.5}
                      max={0.95}
                      step={0.05}
                      value={memoryMinConfidence}
                      onChange={(e) => setMemoryMinConfidence(parseFloat(e.target.value))}
                      className="w-full accent-indigo-500"
                    />
                    <span className="text-[10px] text-slate-500">
                      Inferences with confidence below this threshold are quarantined for explicit review.
                    </span>
                  </div>

                  <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-900/40 text-emerald-300 space-y-2">
                    <div className="flex items-center space-x-2 text-xs font-semibold">
                      <Lock className="w-4 h-4 text-emerald-400" />
                      <span>Cryptographic Isolation &amp; Integrity</span>
                    </div>
                    <p className="text-[11px] text-emerald-400/80 leading-relaxed">
                      Journal entries are cryptographically signed with RFC 8785 canonical JSON and HMAC SHA-256 for integrity verification. Reflections are strictly quarantined from ordinary LLM context injection and excluded from automated memory extraction.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* DATA MANAGEMENT TAB */}
            {activeTab === 'data' && (
              <div className="space-y-5">
                <div className="border-b border-slate-800/80 pb-3">
                  <h2 className="text-sm font-semibold text-slate-100">Data Management &amp; Portability</h2>
                  <p className="text-xs text-slate-400">Download all your personal data in open, structured JSON format.</p>
                </div>

                <div className="space-y-4">
                  <div className="p-4.5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
                    <div className="flex items-center space-x-2">
                      <Download className="w-4 h-4 text-indigo-400" />
                      <span className="text-xs font-semibold text-slate-200">Complete Personal Data Export</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Exports all your tasks, projects, goals, persistent memories, and private journal entries in one JSON bundle for backup or GDPR portability.
                    </p>
                    <button
                      type="button"
                      disabled={exportDataMutation.isPending}
                      onClick={handleExportData}
                      className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-100 text-xs font-medium transition border border-slate-700 disabled:opacity-50"
                    >
                      <Download className="w-4 h-4" />
                      <span>Export All Data (JSON)</span>
                    </button>
                    {exportStatus && (
                      <p className="text-xs text-indigo-300 font-mono">{exportStatus}</p>
                    )}
                  </div>

                  <div className="p-4.5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
                    <div className="flex items-center space-x-2">
                      <Cpu className="w-4 h-4 text-emerald-400" />
                      <span className="text-xs font-semibold text-slate-200">System Integrations &amp; Infrastructure</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                      <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800/80">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">Database</span>
                        <span className="text-slate-200 font-medium">PostgreSQL &amp; Supabase RLS</span>
                      </div>
                      <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800/80">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">AI Model</span>
                        <span className="text-slate-200 font-medium">{aiModel}</span>
                      </div>
                      <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800/80">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">Retrieval</span>
                        <span className="text-slate-200 font-medium">Hybrid Lexical &amp; HNSW</span>
                      </div>
                      <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800/80">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">Local Storage</span>
                        <span className="text-slate-200 font-medium">SQLite WAL Engine</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-900/30 border border-slate-800/60 space-y-1">
                    <span className="text-xs font-semibold text-slate-300">Session Security</span>
                    <p className="text-[11px] text-slate-500">
                      Authenticated via Supabase JWT with Row Level Security (RLS) enforcement at the PostgreSQL database level.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Save Button */}
            {activeTab !== 'data' && (
              <div className="pt-4 border-t border-slate-800/80 flex justify-end">
                <button
                  type="submit"
                  disabled={updateProfileMutation.isPending}
                  className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white text-xs font-semibold transition shadow-md shadow-indigo-600/20 disabled:opacity-50"
                >
                  <Save className="w-4 h-4" />
                  <span>Save Changes</span>
                </button>
              </div>
            )}
          </form>
        </div>
      </div>
    </div>
  );
};

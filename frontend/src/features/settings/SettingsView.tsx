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
  Smartphone,
  Monitor,
  ShieldCheck,
  Layers,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useTheme, ThemeMode } from '../../context/ThemeContext';
import { useExportUserData, useUpdateUserProfile, useUserProfile } from '../../hooks/useSettings';
import { usePWAInstall } from '../../hooks/usePWAInstall';

export const SettingsView: React.FC = () => {
  const { user, signOut } = useAuth();
  const { data: profile } = useUserProfile(user?.id);
  const updateProfileMutation = useUpdateUserProfile(user?.id);
  const exportDataMutation = useExportUserData();
  const { isInstalled, hasDeferredPrompt, promptInstall } = usePWAInstall();

  // Tab State
  const [activeTab, setActiveTab] = useState<'profile' | 'ai' | 'memory' | 'data' | 'app'>('profile');

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
    <div className="flex-1 flex flex-col h-full bg-[#07080c] overflow-hidden text-slate-100">
      {/* Top Banner */}
      <div className="px-6 py-4.5 border-b border-white/[0.06] bg-[#0e1017]/70 backdrop-blur-md flex items-center justify-between">
        <div className="flex items-center space-x-3.5">
          <div className="p-2.5 rounded-xl bg-champagne-500/10 border border-champagne-500/20 text-champagne-400 shadow-sm">
            <Settings className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold tracking-tight text-white">Settings &amp; Preferences</h1>
              <span className="hidden sm:inline-flex text-[10px] font-mono px-2 py-0.5 rounded bg-graphite-800/90 text-champagne-300 border border-champagne-500/20">
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
        {/* Navigation Tabs (Horizontal scroll strip on mobile, vertical sidebar on desktop) */}
        <div className="w-full md:w-64 border-b md:border-b-0 md:border-r border-white/[0.06] p-2.5 sm:p-4 flex flex-row overflow-x-auto scrollbar-none md:flex-col gap-1.5 sm:space-y-1.5 bg-[#07080c] flex-shrink-0">
          <button
            onClick={() => setActiveTab('profile')}
            className={`whitespace-nowrap flex-shrink-0 md:w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 touch-target cursor-pointer ${
              activeTab === 'profile'
                ? 'bg-white/[0.08] text-white border border-white/[0.12] shadow-sm font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <User className="w-4 h-4 text-champagne-400" />
            <span>Profile &amp; Account</span>
          </button>

          <button
            onClick={() => setActiveTab('ai')}
            className={`whitespace-nowrap flex-shrink-0 md:w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 touch-target cursor-pointer ${
              activeTab === 'ai'
                ? 'bg-white/[0.08] text-white border border-white/[0.12] shadow-sm font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Bot className="w-4 h-4 text-champagne-400" />
            <span>AI Model &amp; Tone</span>
          </button>

          <button
            onClick={() => setActiveTab('memory')}
            className={`whitespace-nowrap flex-shrink-0 md:w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 touch-target cursor-pointer ${
              activeTab === 'memory'
                ? 'bg-white/[0.08] text-white border border-white/[0.12] shadow-sm font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Brain className="w-4 h-4 text-champagne-400" />
            <span>Memory &amp; Privacy</span>
          </button>

          <button
            onClick={() => setActiveTab('data')}
            className={`whitespace-nowrap flex-shrink-0 md:w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 touch-target cursor-pointer ${
              activeTab === 'data'
                ? 'bg-white/[0.08] text-white border border-white/[0.12] shadow-sm font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Database className="w-4 h-4 text-champagne-400" />
            <span>Data Management &amp; Export</span>
          </button>

          <button
            onClick={() => setActiveTab('app')}
            className={`whitespace-nowrap flex-shrink-0 md:w-full flex items-center space-x-2.5 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 touch-target cursor-pointer ${
              activeTab === 'app'
                ? 'bg-white/[0.08] text-white border border-white/[0.12] shadow-sm font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Smartphone className="w-4 h-4 text-champagne-400" />
            <span>App &amp; PWA Installation</span>
          </button>
        </div>

        {/* Tab Content Panel */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 max-w-3xl scrollbar-thin">
          <form onSubmit={handleSave} className="space-y-6">
            {saveStatus && (
              <div className="p-3.5 rounded-xl bg-indigo-950/40 border border-indigo-500/30 text-xs text-indigo-200 flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-champagne-400" />
                <span>{saveStatus}</span>
              </div>
            )}

            {/* PROFILE TAB */}
            {activeTab === 'profile' && (
              <div className="space-y-5">
                <div className="border-b border-white/[0.06] pb-3">
                  <h2 className="text-sm font-semibold text-white">User Identity &amp; Profile</h2>
                  <p className="text-xs text-slate-400">Manage your display identity and account credentials.</p>
                </div>

                <div className="space-y-3.5">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">User ID (UUID)</label>
                    <input
                      type="text"
                      disabled
                      value={user?.id || profile?.id || 'Not authenticated'}
                      className="w-full bg-[#0e1017]/50 border border-white/[0.06] rounded-xl px-3.5 py-2 text-xs font-mono text-slate-400 select-all"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Email Address</label>
                    <input
                      type="email"
                      disabled
                      value={user?.email || profile?.email || ''}
                      className="w-full bg-[#0e1017]/50 border border-white/[0.06] rounded-xl px-3.5 py-2 text-xs text-slate-300"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Full Name</label>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Your name..."
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-champagne-500/50 transition"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Avatar URL</label>
                    <input
                      type="url"
                      value={avatarUrl}
                      onChange={(e) => setAvatarUrl(e.target.value)}
                      placeholder="https://..."
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-champagne-500/50 transition"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Theme</label>
                    <select
                      value={theme}
                      onChange={(e) => setTheme(e.target.value as ThemeMode)}
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-champagne-500/50 transition"
                    >
                      <option value="dark">Dark Slate (Default)</option>
                      <option value="midnight">Midnight Indigo (Deep Contrast)</option>
                      <option value="obsidian">Pure Obsidian (OLED Black)</option>
                    </select>
                  </div>
                </div>

                {/* Session Management */}
                {user && (
                  <div className="pt-4 border-t border-white/[0.06] space-y-3">
                    <h3 className="text-xs font-semibold text-slate-300">Active Session</h3>
                    <div className="flex items-center justify-between p-4 rounded-xl bg-[#0e1017]/70 border border-white/[0.06]">
                      <div>
                        <span className="text-xs text-slate-200 block font-medium">Logged in as {user.email}</span>
                        <span className="text-[10px] text-slate-500 font-mono">Role: {user.role || 'authenticated'}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => signOut()}
                        className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-white/[0.06] hover:bg-rose-950/60 hover:text-rose-300 hover:border-rose-800/40 text-slate-300 text-xs font-medium transition border border-white/[0.08] cursor-pointer"
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
                <div className="border-b border-white/[0.06] pb-3">
                  <h2 className="text-sm font-semibold text-white">AI Model &amp; Communication Preferences</h2>
                  <p className="text-xs text-slate-400">Control how AUREN reasons, analyzes, and responds.</p>
                </div>

                <div className="space-y-3.5">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Default AI Model</label>
                    <select
                      value={aiModel}
                      onChange={(e) => setAiModel(e.target.value)}
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-champagne-500/50 transition"
                    >
                      <option value="gemini-2.5-flash">Google Gemini 2.5 Flash (Blazing Fast, Sub-Second Latency — Recommended)</option>
                      <option value="gemini-2.0-flash">Google Gemini 2.0 Flash (High Throughput &amp; Low Latency)</option>
                      <option value="gemini-3.1-flash-lite">Google Gemini 3.1 Flash Lite (Ultra Lightweight)</option>
                      <option value="gemini-2.5-pro">Google Gemini 2.5 Pro (Deep Reasoning &amp; Complex Analysis)</option>
                      <option value="gemini-3.8-pro">Google Gemini 3.8 Pro (Advanced Analytical Reasoning)</option>
                      <option value="mock">Local Development Mock (Offline testing)</option>
                    </select>
                    {!['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-3.1-flash-lite', 'gemini-2.5-pro', 'gemini-3.8-pro', 'gemini-3.5-flash-lite', 'gemini-3.8-flash', 'mock'].includes(aiModel) && (
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
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-champagne-500/50 transition"
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
                      className="w-full bg-[#0e1017] border border-white/[0.08] rounded-xl p-3.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-champagne-500/50 leading-relaxed transition"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* MEMORY & PRIVACY TAB */}
            {activeTab === 'memory' && (
              <div className="space-y-5">
                <div className="border-b border-white/[0.06] pb-3">
                  <h2 className="text-sm font-semibold text-white">Memory &amp; Privacy Policies</h2>
                  <p className="text-xs text-slate-400">Configure what AUREN remembers and inspect security invariants.</p>
                </div>

                <div className="space-y-4">
                  <div className="p-4 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] flex items-center justify-between">
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
                      className="w-4 h-4 rounded text-champagne-500 focus:ring-champagne-500 bg-[#07080c] border-white/[0.1]"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                      <span>Minimum Extraction Confidence</span>
                      <span className="font-mono text-champagne-400 font-semibold">{Math.round(memoryMinConfidence * 100)}%</span>
                    </div>
                    <input
                      type="range"
                      min={0.5}
                      max={0.95}
                      step={0.05}
                      value={memoryMinConfidence}
                      onChange={(e) => setMemoryMinConfidence(parseFloat(e.target.value))}
                      className="w-full accent-champagne-500"
                    />
                    <span className="text-[10px] text-slate-500">
                      Inferences with confidence below this threshold are quarantined for explicit review.
                    </span>
                  </div>

                  <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-500/30 text-emerald-300 space-y-2">
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
                <div className="border-b border-white/[0.06] pb-3">
                  <h2 className="text-sm font-semibold text-white">Data Management &amp; Portability</h2>
                  <p className="text-xs text-slate-400">Download all your personal data in open, structured JSON format.</p>
                </div>

                <div className="space-y-4">
                  <div className="p-4.5 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] space-y-3">
                    <div className="flex items-center space-x-2">
                      <Download className="w-4 h-4 text-champagne-400" />
                      <span className="text-xs font-semibold text-slate-200">Complete Personal Data Export</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Exports all your tasks, projects, goals, persistent memories, and private journal entries in one JSON bundle for backup or GDPR portability.
                    </p>
                    <button
                      type="button"
                      disabled={exportDataMutation.isPending}
                      onClick={handleExportData}
                      className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] text-slate-100 text-xs font-medium transition border border-white/[0.08] disabled:opacity-50 cursor-pointer"
                    >
                      <Download className="w-4 h-4" />
                      <span>Export All Data (JSON)</span>
                    </button>
                    {exportStatus && (
                      <p className="text-xs text-champagne-300 font-mono">{exportStatus}</p>
                    )}
                  </div>

                  <div className="p-4.5 rounded-xl bg-[#0e1017]/70 border border-white/[0.06] space-y-3">
                    <div className="flex items-center space-x-2">
                      <Cpu className="w-4 h-4 text-emerald-400" />
                      <span className="text-xs font-semibold text-slate-200">System Integrations &amp; Infrastructure</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                      <div className="p-2.5 rounded-xl bg-[#07080c] border border-white/[0.06]">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">Database</span>
                        <span className="text-slate-200 font-medium">PostgreSQL &amp; Supabase RLS</span>
                      </div>
                      <div className="p-2.5 rounded-xl bg-[#07080c] border border-white/[0.06]">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">AI Model</span>
                        <span className="text-slate-200 font-medium">{aiModel}</span>
                      </div>
                      <div className="p-2.5 rounded-xl bg-[#07080c] border border-white/[0.06]">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">Retrieval</span>
                        <span className="text-slate-200 font-medium">Hybrid Lexical &amp; HNSW</span>
                      </div>
                      <div className="p-2.5 rounded-xl bg-[#07080c] border border-white/[0.06]">
                        <span className="text-[10px] text-slate-500 block uppercase font-mono">Local Storage</span>
                        <span className="text-slate-200 font-medium">SQLite WAL Engine</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-[#0e1017]/40 border border-white/[0.04] space-y-1">
                    <span className="text-xs font-semibold text-slate-300">Session Security</span>
                    <p className="text-[11px] text-slate-500">
                      Authenticated via Supabase JWT with Row Level Security (RLS) enforcement at the PostgreSQL database level.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* APP & PWA INSTALLATION TAB */}
            {activeTab === 'app' && (
              <div className="space-y-5">
                <div className="border-b border-white/[0.06] pb-3">
                  <h2 className="text-sm font-semibold text-white">App Installation &amp; PWA Identity</h2>
                  <p className="text-xs text-slate-400">
                    Install AUREN onto your smartphone or desktop for a fast, standalone application experience.
                  </p>
                </div>

                {/* Identity & Status Overview */}
                <div className="p-5 rounded-2xl bg-gradient-to-r from-champagne-950/30 via-[#0e111a] to-[#07080c] border border-white/[0.08] flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-subtle-elevation">
                  <div className="flex items-center space-x-4">
                    <div className="w-14 h-14 rounded-2xl bg-[#08090C] border border-champagne-400/40 p-1 flex items-center justify-center flex-shrink-0 shadow-md">
                      <img
                        src="/icons/icon-192.png"
                        alt="AUREN"
                        className="w-full h-full object-contain rounded-xl"
                      />
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <h3 className="text-base font-bold text-white tracking-tight">AUREN</h3>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-champagne-950/80 text-champagne-300 border border-champagne-700/40">
                          v0.1.0-alpha
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">Your Personal AI Command Center</p>
                      <p className="text-[10px] text-champagne-400/80 mt-1 font-mono">
                        Theme: Obsidian (#0C0E14) · Background: (#08090C)
                      </p>
                    </div>
                  </div>

                  <div className="flex sm:flex-col items-center sm:items-end justify-between sm:justify-center border-t sm:border-t-0 border-white/[0.06] pt-3 sm:pt-0">
                    <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">
                      Display Mode
                    </span>
                    {isInstalled ? (
                      <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-emerald-950/80 text-emerald-400 border border-emerald-800/50 text-xs font-semibold mt-1">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Standalone Active</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-amber-950/60 text-amber-300 border border-amber-800/50 text-xs font-semibold mt-1">
                        <Smartphone className="w-3.5 h-3.5" />
                        <span>Browser Mode</span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Quick 1-Click Install Button if Native Prompt is Available */}
                {!isInstalled && hasDeferredPrompt && (
                  <div className="p-4 rounded-2xl bg-champagne-950/30 border border-champagne-400/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm">
                    <div>
                      <span className="text-xs font-semibold text-champagne-300 block">
                        Native Browser Installation Ready
                      </span>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        Add AUREN to your device home screen or application launcher with one click.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => promptInstall()}
                      className="px-4 py-2 bg-[#d7ba83] hover:bg-[#e6d4b0] text-[#07080c] font-semibold text-xs rounded-xl shadow-md transition flex items-center justify-center space-x-2 flex-shrink-0 touch-target cursor-pointer"
                    >
                      <Download className="w-4 h-4" />
                      <span>Install AUREN App</span>
                    </button>
                  </div>
                )}

                {/* Installation Guides by Platform */}
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Installation Instructions
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* Android */}
                    <div className="p-4 rounded-2xl bg-[#0c0e14] border border-white/[0.06] space-y-2">
                      <div className="flex items-center space-x-2 text-xs font-semibold text-emerald-400">
                        <Smartphone className="w-4 h-4" />
                        <span>Android (Chrome)</span>
                      </div>
                      <ol className="text-[11px] text-slate-400 space-y-1.5 list-decimal list-inside leading-relaxed">
                        <li>Open this link in Chrome.</li>
                        <li>Tap the three dots (⋮) in the top-right.</li>
                        <li>Select <strong>Install app</strong> or <strong>Add to Home Screen</strong>.</li>
                      </ol>
                    </div>

                    {/* Apple iOS */}
                    <div className="p-4 rounded-2xl bg-[#0c0e14] border border-white/[0.06] space-y-2">
                      <div className="flex items-center space-x-2 text-xs font-semibold text-champagne-300">
                        <Smartphone className="w-4 h-4" />
                        <span>iPhone &amp; iPad (Safari)</span>
                      </div>
                      <ol className="text-[11px] text-slate-400 space-y-1.5 list-decimal list-inside leading-relaxed">
                        <li>Open this link in <strong>Safari</strong>.</li>
                        <li>Tap the <strong>Share</strong> icon in the bottom bar.</li>
                        <li>Tap <strong>Add to Home Screen</strong>, then <strong>Add</strong>.</li>
                      </ol>
                    </div>

                    {/* Desktop */}
                    <div className="p-4 rounded-2xl bg-[#0c0e14] border border-white/[0.06] space-y-2">
                      <div className="flex items-center space-x-2 text-xs font-semibold text-indigo-400">
                        <Monitor className="w-4 h-4" />
                        <span>Desktop (Chrome / Edge)</span>
                      </div>
                      <ol className="text-[11px] text-slate-400 space-y-1.5 list-decimal list-inside leading-relaxed">
                        <li>Look at the right side of the address bar.</li>
                        <li>Click the <strong>Install AUREN</strong> icon.</li>
                        <li>Confirm <strong>Install</strong> to launch standalone.</li>
                      </ol>
                    </div>
                  </div>
                </div>

                {/* Session Persistence & Offline Guarantee */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-1.5">
                    <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200">
                      <ShieldCheck className="w-4 h-4 text-champagne-400" />
                      <span>Persistent Supabase Session</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Your authentication token persists in local secure storage. Closing and reopening the installed application retains your active session automatically.
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-1.5">
                    <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200">
                      <Layers className="w-4 h-4 text-champagne-400" />
                      <span>Zero-Leak Offline Security</span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Static application assets cache for instant launch. Private journal entries, vector memories, and AI conversations are strictly protected and never cached offline.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Save Button */}
            {activeTab !== 'data' && activeTab !== 'app' && (
              <div className="pt-4 border-t border-white/[0.06] flex justify-end">
                <button
                  type="submit"
                  disabled={updateProfileMutation.isPending}
                  className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-[#d7ba83] hover:bg-[#e6d4b0] text-[#07080c] text-xs font-semibold transition shadow-sm hover:shadow-[0_0_16px_rgba(215,186,131,0.25)] disabled:opacity-50 cursor-pointer"
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

/**
 * AUREN PWA Installation Guide Modal.
 * Provides clear, platform-specific installation instructions for Android, iOS, and Desktop.
 * Elevated with AUREN Obsidian & Champagne Design System.
 */

import React, { useState } from 'react';
import {
  X,
  Smartphone,
  Monitor,
  Download,
  Share,
  PlusSquare,
  CheckCircle2,
  Sparkles,
  Shield,
  Layers,
} from 'lucide-react';
import { DevicePlatform } from '../../hooks/usePWAInstall';

interface InstallGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
  platform: DevicePlatform;
  hasDeferredPrompt: boolean;
  onPromptInstall: () => Promise<boolean>;
}

export const InstallGuideModal: React.FC<InstallGuideModalProps> = ({
  isOpen,
  onClose,
  platform,
  hasDeferredPrompt,
  onPromptInstall,
}) => {
  const [activeTab, setActiveTab] = useState<DevicePlatform>(platform);
  const [isInstalling, setIsInstalling] = useState(false);

  if (!isOpen) return null;

  const handleInstallClick = async () => {
    setIsInstalling(true);
    try {
      await onPromptInstall();
    } finally {
      setIsInstalling(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3.5 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="fixed inset-0"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="relative w-full max-w-lg bg-[#0c0e14] border border-white/[0.1] rounded-3xl shadow-card-elevation overflow-hidden z-10 flex flex-col max-h-[90vh]">
        {/* Subtle Ambient Radial Glow */}
        <div className="absolute top-0 right-1/3 w-64 h-32 bg-champagne-400/5 blur-3xl pointer-events-none rounded-full" />

        {/* Modal Header */}
        <div className="p-5 sm:p-6 pb-4 border-b border-white/[0.08] flex items-start justify-between relative z-10">
          <div className="flex items-center space-x-3.5">
            <div className="w-12 h-12 rounded-2xl bg-[#08090C] border border-champagne-400/30 p-1 flex items-center justify-center shadow-md flex-shrink-0">
              <img
                src="/icons/icon-192.png"
                alt="AUREN"
                className="w-full h-full object-contain rounded-xl"
              />
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight flex items-center space-x-2">
                <span>Install AUREN</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-champagne-950/80 text-champagne-300 border border-champagne-700/40">
                  PWA Standalone
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Your Personal AI Command Center on your device
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-white/[0.06] transition touch-target"
            aria-label="Close dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body Container */}
        <div className="p-5 sm:p-6 overflow-y-auto space-y-5 scrollbar-thin">
          {/* Quick 1-Click Install Button if Native Prompt is Available */}
          {hasDeferredPrompt && (
            <div className="p-4 rounded-2xl bg-gradient-to-r from-champagne-950/40 via-[#141722] to-champagne-950/20 border border-champagne-400/30 space-y-2.5">
              <div className="flex items-center space-x-2 text-xs font-semibold text-champagne-300">
                <Sparkles className="w-4 h-4 text-champagne-400" />
                <span>Instant Installation Available</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                Your browser supports one-click standalone app installation.
              </p>
              <button
                onClick={handleInstallClick}
                disabled={isInstalling}
                className="w-full py-2.5 px-4 bg-[#d7ba83] hover:bg-[#e6d4b0] disabled:opacity-50 text-[#07080c] font-semibold text-xs rounded-xl shadow-md transition flex items-center justify-center space-x-2 touch-target"
              >
                <Download className="w-4 h-4" />
                <span>{isInstalling ? 'Installing...' : 'Install AUREN App'}</span>
              </button>
            </div>
          )}

          {/* Platform Switcher Tabs */}
          <div className="flex items-center space-x-1.5 p-1 rounded-xl bg-white/[0.03] border border-white/[0.06]">
            <button
              onClick={() => setActiveTab('android')}
              className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-medium transition flex items-center justify-center space-x-1.5 ${
                activeTab === 'android'
                  ? 'bg-white/[0.09] text-white shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Smartphone className="w-3.5 h-3.5 text-emerald-400" />
              <span>Android</span>
            </button>
            <button
              onClick={() => setActiveTab('ios')}
              className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-medium transition flex items-center justify-center space-x-1.5 ${
                activeTab === 'ios'
                  ? 'bg-white/[0.09] text-white shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Smartphone className="w-3.5 h-3.5 text-champagne-300" />
              <span>iPhone / iPad</span>
            </button>
            <button
              onClick={() => setActiveTab('desktop')}
              className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-medium transition flex items-center justify-center space-x-1.5 ${
                activeTab === 'desktop'
                  ? 'bg-white/[0.09] text-white shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Monitor className="w-3.5 h-3.5 text-indigo-400" />
              <span>Desktop</span>
            </button>
          </div>

          {/* Platform Specific Instructions */}
          {activeTab === 'android' && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                Android Installation (Chrome)
              </h3>
              <div className="space-y-2.5 text-xs text-slate-300">
                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                  <div className="h-5 w-5 rounded-full bg-emerald-950/60 border border-emerald-800/40 text-emerald-400 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">
                    1
                  </div>
                  <div>
                    <span className="font-semibold text-white">Open in Google Chrome</span>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      Ensure you are using Chrome on your Android smartphone.
                    </p>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                  <div className="h-5 w-5 rounded-full bg-emerald-950/60 border border-emerald-800/40 text-emerald-400 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">
                    2
                  </div>
                  <div>
                    <span className="font-semibold text-white">Tap Chrome Menu (⋮)</span>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      Tap the three vertical dots in the top-right corner of Chrome.
                    </p>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                  <div className="h-5 w-5 rounded-full bg-emerald-950/60 border border-emerald-800/40 text-emerald-400 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">
                    3
                  </div>
                  <div>
                    <span className="font-semibold text-white">Select "Install app"</span>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      Tap <strong>Install app</strong> (or "Add to Home screen"), then confirm <strong>Install</strong>.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'ios' && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                Apple iOS Installation (Safari)
              </h3>
              <div className="space-y-2.5 text-xs text-slate-300">
                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                  <div className="h-5 w-5 rounded-full bg-champagne-950/60 border border-champagne-700/40 text-champagne-300 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">
                    1
                  </div>
                  <div>
                    <span className="font-semibold text-white">Open in Safari</span>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      Apple iOS requires using Safari to add web applications to the Home Screen.
                    </p>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                  <div className="h-5 w-5 rounded-full bg-champagne-950/60 border border-champagne-700/40 text-champagne-300 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">
                    2
                  </div>
                  <div>
                    <div className="flex items-center space-x-1.5 font-semibold text-white">
                      <span>Tap the Share Button</span>
                      <Share className="w-3.5 h-3.5 text-champagne-400" />
                    </div>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      Tap the Share icon (square with an upward arrow) in Safari's bottom toolbar.
                    </p>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                  <div className="h-5 w-5 rounded-full bg-champagne-950/60 border border-champagne-700/40 text-champagne-300 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">
                    3
                  </div>
                  <div>
                    <div className="flex items-center space-x-1.5 font-semibold text-white">
                      <span>Choose "Add to Home Screen"</span>
                      <PlusSquare className="w-3.5 h-3.5 text-champagne-400" />
                    </div>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      Scroll down the share sheet and tap <strong>Add to Home Screen</strong>, then tap <strong>Add</strong>.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'desktop' && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                Desktop Installation (Chrome, Edge, Brave)
              </h3>
              <div className="space-y-2.5 text-xs text-slate-300">
                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                  <div className="h-5 w-5 rounded-full bg-indigo-950/60 border border-indigo-700/40 text-indigo-400 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">
                    1
                  </div>
                  <div>
                    <span className="font-semibold text-white">Look in the Address Bar</span>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      In Chrome or Edge, an <strong>Install AUREN</strong> icon appears on the right side of the URL bar.
                    </p>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                  <div className="h-5 w-5 rounded-full bg-indigo-950/60 border border-indigo-700/40 text-indigo-400 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">
                    2
                  </div>
                  <div>
                    <span className="font-semibold text-white">Click "Install"</span>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      Confirm installation to place AUREN in your Applications / Start menu.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Standalone Benefits */}
          <div className="grid grid-cols-3 gap-2.5 pt-2 border-t border-white/[0.06]">
            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.04] text-center space-y-1">
              <Layers className="w-4 h-4 text-champagne-400 mx-auto" />
              <span className="text-[10px] font-semibold text-slate-200 block">No Browser UI</span>
              <span className="text-[9px] text-slate-400 block leading-tight">Clean standalone window</span>
            </div>
            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.04] text-center space-y-1">
              <Shield className="w-4 h-4 text-champagne-400 mx-auto" />
              <span className="text-[10px] font-semibold text-slate-200 block">Auth Persisted</span>
              <span className="text-[9px] text-slate-400 block leading-tight">Always stays signed in</span>
            </div>
            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.04] text-center space-y-1">
              <CheckCircle2 className="w-4 h-4 text-champagne-400 mx-auto" />
              <span className="text-[10px] font-semibold text-slate-200 block">Fast Launch</span>
              <span className="text-[9px] text-slate-400 block leading-tight">1-tap from home screen</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};


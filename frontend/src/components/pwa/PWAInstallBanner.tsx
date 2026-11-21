/**
 * Prominent PWA Installation Banner.
 * Greets users when visiting via web browser, prompting them to install
 * AUREN onto their device or Home Screen for full app capabilities.
 */

import React, { useState, useEffect } from 'react';
import { Download, Smartphone, X, Sparkles } from 'lucide-react';
import { usePWAInstall } from '../../hooks/usePWAInstall';
import { InstallGuideModal } from './InstallGuideModal';

export const PWAInstallBanner: React.FC = () => {
  const {
    isInstalled,
    platform,
    promptInstall,
    hasDeferredPrompt,
    isInstallModalOpen,
    setIsInstallModalOpen,
  } = usePWAInstall();
  const [isDismissed, setIsDismissed] = useState(true);

  useEffect(() => {
    // Check if dismissed in this session
    const dismissed = sessionStorage.getItem('auren_pwa_banner_dismissed');
    if (!dismissed) {
      setIsDismissed(false);
    }
  }, []);

  if (isInstalled || isDismissed) {
    return (
      <InstallGuideModal
        isOpen={isInstallModalOpen}
        onClose={() => setIsInstallModalOpen(false)}
        platform={platform}
        hasDeferredPrompt={hasDeferredPrompt}
        onPromptInstall={promptInstall}
      />
    );
  }

  const handleDismiss = () => {
    setIsDismissed(true);
    sessionStorage.setItem('auren_pwa_banner_dismissed', 'true');
  };

  const handleInstallClick = async () => {
    if (platform === 'ios') {
      setIsInstallModalOpen(true);
      return;
    }
    const success = await promptInstall();
    if (success) {
      setIsDismissed(true);
    }
  };

  return (
    <>
      <div className="bg-white border-b border-slate-200 px-3.5 py-2.5 sm:px-6 sm:py-3 text-slate-900 z-40 relative shadow-xs animate-in fade-in slide-in-from-top duration-300">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-3">
          <div className="flex items-center space-x-3 min-w-0">
            <div className="h-8 w-8 rounded-xl bg-emerald-50 border border-emerald-200 p-0.5 flex-shrink-0 shadow-sm flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-emerald-600" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center space-x-2">
                <span className="text-xs font-bold text-slate-900 tracking-tight">Install AUREN</span>
                <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 uppercase font-bold">
                  Official App
                </span>
              </div>
              <p className="text-[11px] text-slate-600 truncate">
                Add to your {platform === 'ios' ? 'Home Screen' : platform === 'android' ? 'device' : 'desktop'} for full screen & instant launch.
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2 flex-shrink-0">
            <button
              onClick={handleInstallClick}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 active:scale-95 text-white font-semibold text-xs transition shadow-md shadow-emerald-500/20 touch-target cursor-pointer"
            >
              {platform === 'ios' ? (
                <Smartphone className="w-3.5 h-3.5 text-white" />
              ) : (
                <Download className="w-3.5 h-3.5 text-white" />
              )}
              <span>Install App</span>
            </button>
            <button
              onClick={handleDismiss}
              className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg transition touch-target cursor-pointer"
              aria-label="Dismiss installation banner"
              title="Dismiss"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      <InstallGuideModal
        isOpen={isInstallModalOpen}
        onClose={() => setIsInstallModalOpen(false)}
        platform={platform}
        hasDeferredPrompt={hasDeferredPrompt}
        onPromptInstall={promptInstall}
      />
    </>
  );
};

/**
 * Hook to manage PWA installation detection, prompts, and standalone lifecycle.
 */

import { useState, useEffect, useCallback } from 'react';

export interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[];
  readonly userChoice: Promise<{
    outcome: 'accepted' | 'dismissed';
    platform: string;
  }>;
  prompt(): Promise<void>;
}

export type DevicePlatform = 'ios' | 'android' | 'desktop';

export function usePWAInstall() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isInstalled, setIsInstalled] = useState<boolean>(false);
  const [platform, setPlatform] = useState<DevicePlatform>('desktop');
  const [isInstallModalOpen, setIsInstallModalOpen] = useState<boolean>(false);
  const [installOutcome, setInstallOutcome] = useState<'accepted' | 'dismissed' | null>(null);

  useEffect(() => {
    // 1. Detect platform
    const userAgent = typeof window !== 'undefined' ? window.navigator.userAgent.toLowerCase() : '';
    const isIOSDevice = /iphone|ipad|ipod/.test(userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const isAndroidDevice = /android/.test(userAgent);

    if (isIOSDevice) {
      setPlatform('ios');
    } else if (isAndroidDevice) {
      setPlatform('android');
    } else {
      setPlatform('desktop');
    }

    // 2. Detect standalone launch mode
    const checkStandalone = () => {
      const isStandaloneMode =
        (typeof window !== 'undefined' && window.matchMedia('(display-mode: standalone)').matches) ||
        (typeof window !== 'undefined' && (window.navigator as any).standalone === true) ||
        (typeof document !== 'undefined' && document.referrer.includes('android-app://'));

      setIsInstalled(Boolean(isStandaloneMode));
    };

    checkStandalone();

    const mediaQuery = window.matchMedia('(display-mode: standalone)');
    const handleDisplayChange = (e: MediaQueryListEvent) => {
      setIsInstalled(e.matches);
    };

    try {
      mediaQuery.addEventListener('change', handleDisplayChange);
    } catch {
      // Fallback for older Safari
      mediaQuery.addListener(handleDisplayChange);
    }

    // 3. Listen for browser install prompt
    const handleBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };

    const handleAppInstalled = () => {
      setDeferredPrompt(null);
      setIsInstalled(true);
      setIsInstallModalOpen(false);
      setInstallOutcome('accepted');
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    window.addEventListener('appinstalled', handleAppInstalled);

    return () => {
      try {
        mediaQuery.removeEventListener('change', handleDisplayChange);
      } catch {
        mediaQuery.removeListener(handleDisplayChange);
      }
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, []);

  const promptInstall = useCallback(async (): Promise<boolean> => {
    if (!deferredPrompt) {
      // If native deferred prompt isn't supported (e.g. iOS or manual install), open install modal guide
      setIsInstallModalOpen(true);
      return false;
    }

    try {
      await deferredPrompt.prompt();
      const choice = await deferredPrompt.userChoice;
      setInstallOutcome(choice.outcome);
      if (choice.outcome === 'accepted') {
        setIsInstalled(true);
        setDeferredPrompt(null);
        setIsInstallModalOpen(false);
        return true;
      }
      return false;
    } catch (err) {
      console.warn('[AUREN PWA] Prompt install error:', err);
      return false;
    }
  }, [deferredPrompt]);

  return {
    isInstalled,
    canInstall: Boolean(deferredPrompt) || (!isInstalled && platform === 'ios'),
    hasDeferredPrompt: Boolean(deferredPrompt),
    platform,
    promptInstall,
    isInstallModalOpen,
    setIsInstallModalOpen,
    installOutcome,
  };
}


import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, renderHook, act } from '@testing-library/react';
import manifest from '../../public/manifest.json';
import { usePWAInstall } from '../hooks/usePWAInstall';
import { InstallGuideModal } from '../components/pwa/InstallGuideModal';

describe('AUREN PWA Branding, Installation & Identity Verification', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('1. Web App Manifest Integrity', () => {
    it('manifest.json contains complete AUREN brand metadata and standalone display mode', () => {
      expect(manifest.name).toBe('AUREN');
      expect(manifest.short_name).toBe('AUREN');
      expect(manifest.description).toBe('Your Personal AI Command Center.');
      expect(manifest.start_url).toBe('/');
      expect(manifest.scope).toBe('/');
      expect(manifest.display).toBe('standalone');
      expect(manifest.theme_color).toBe('#0C0E14');
      expect(manifest.background_color).toBe('#08090C');

      // Verify icon entries
      expect(Array.isArray(manifest.icons)).toBe(true);
      expect(manifest.icons.length).toBeGreaterThanOrEqual(4);

      const sizes = manifest.icons.map((i: any) => i.sizes);
      expect(sizes).toContain('192x192');
      expect(sizes).toContain('512x512');
      expect(sizes).toContain('180x180');

      // Verify maskable icon purpose
      const maskable = manifest.icons.find((i: any) => i.purpose === 'maskable');
      expect(maskable).toBeDefined();
      expect(maskable?.sizes).toBe('512x512');
    });
  });

  describe('2. usePWAInstall Lifecycle Hook', () => {
    it('initializes with default browser state when not standalone', () => {
      const { result } = renderHook(() => usePWAInstall());
      expect(result.current.isInstalled).toBe(false);
      expect(result.current.hasDeferredPrompt).toBe(false);
      expect(result.current.isInstallModalOpen).toBe(false);
    });

    it('captures beforeinstallprompt event and exposes promptInstall', async () => {
      const { result } = renderHook(() => usePWAInstall());

      const mockPrompt = vi.fn().mockResolvedValue(undefined);
      const fakeEvent = new Event('beforeinstallprompt') as any;
      fakeEvent.prompt = mockPrompt;
      fakeEvent.userChoice = Promise.resolve({ outcome: 'accepted', platform: 'web' });

      act(() => {
        window.dispatchEvent(fakeEvent);
      });

      expect(result.current.hasDeferredPrompt).toBe(true);
      expect(result.current.canInstall).toBe(true);

      let success = false;
      await act(async () => {
        success = await result.current.promptInstall();
      });

      expect(mockPrompt).toHaveBeenCalled();
      expect(success).toBe(true);
      expect(result.current.isInstalled).toBe(true);
    });

    it('detects standalone mode when media query matches', () => {
      const originalMatchMedia = window.matchMedia;
      window.matchMedia = vi.fn().mockImplementation((query) => ({
        matches: query === '(display-mode: standalone)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));

      const { result } = renderHook(() => usePWAInstall());
      expect(result.current.isInstalled).toBe(true);

      window.matchMedia = originalMatchMedia;
    });
  });

  describe('3. InstallGuideModal Component', () => {
    it('renders with AUREN branding and platform tabs', () => {
      const onClose = vi.fn();
      const onPromptInstall = vi.fn().mockResolvedValue(true);

      render(
        <InstallGuideModal
          isOpen={true}
          onClose={onClose}
          platform="android"
          hasDeferredPrompt={false}
          onPromptInstall={onPromptInstall}
        />
      );

      expect(screen.getByText('Install AUREN')).toBeInTheDocument();
      expect(screen.getByText('PWA Standalone')).toBeInTheDocument();
      expect(screen.getByText('Android Installation (Chrome)')).toBeInTheDocument();

      // Switch to iOS
      fireEvent.click(screen.getByText('iPhone / iPad'));
      expect(screen.getByText('Apple iOS Installation (Safari)')).toBeInTheDocument();
      expect(screen.getAllByText(/Share/)[0]).toBeInTheDocument();
      expect(screen.getAllByText(/Add to Home Screen/)[0]).toBeInTheDocument();

      // Switch to Desktop
      fireEvent.click(screen.getByText('Desktop'));
      expect(screen.getByText('Desktop Installation (Chrome, Edge, Brave)')).toBeInTheDocument();
    });

    it('displays 1-click install button when native prompt is available', async () => {
      const onClose = vi.fn();
      const onPromptInstall = vi.fn().mockResolvedValue(true);

      render(
        <InstallGuideModal
          isOpen={true}
          onClose={onClose}
          platform="desktop"
          hasDeferredPrompt={true}
          onPromptInstall={onPromptInstall}
        />
      );

      const installBtn = screen.getByText('Install AUREN App');
      expect(installBtn).toBeInTheDocument();

      await act(async () => {
        fireEvent.click(installBtn);
      });

      expect(onPromptInstall).toHaveBeenCalled();
    });
  });
});

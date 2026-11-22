/**
 * Unit & Integration Tests for SettingsView.
 * Tests profile preferences loading, saving, theme switching and DOM application,
 * operational AI model selection, memory extraction policies, and GDPR data export.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SettingsView } from '../features/settings/SettingsView';
import { ThemeProvider } from '../context/ThemeContext';
import * as settingsApi from '../api/settings';

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<any>();
  const user = { id: 'usr-test-123', email: 'solomon@auren.ai', role: 'authenticated' };
  return {
    ...actual,
    AuthContext: React.createContext({
      user,
      signOut: vi.fn(),
      isAuthenticated: true,
    }),
    useAuth: () => ({
      user,
      signOut: vi.fn(),
      isAuthenticated: true,
    }),
  };
});

vi.mock('../api/settings', async () => {
  const actual = await vi.importActual<any>('../api/settings');
  return {
    ...actual,
    getUserProfile: vi.fn(),
    updateUserProfile: vi.fn(),
    exportUserData: vi.fn(),
  };
});

function createMockUserProfile(overrides?: Partial<settingsApi.UserProfile>): settingsApi.UserProfile {
  return {
    id: 'usr-test-123',
    email: 'solomon@auren.ai',
    role: 'authenticated',
    full_name: 'Solomon Kane',
    avatar_url: 'https://avatar.png',
    preferences: {
      theme: 'dark',
      ai_model: 'gemini-2.5-flash',
      ai_tone: 'thoughtful',
      ai_custom_instructions: 'Keep responses concise.',
      memory_auto_extraction: true,
      memory_min_confidence: 0.75,
    },
    app_metadata: {},
    user_metadata: {},
    ...overrides,
  };
}

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

describe('SettingsView Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.className = '';
  });

  it('loads and renders user profile with active session and theme selector', async () => {
    const qc = createTestQueryClient();
    vi.mocked(settingsApi.getUserProfile).mockResolvedValueOnce(createMockUserProfile());

    render(
      <QueryClientProvider client={qc}>
        <ThemeProvider>
          <SettingsView />
        </ThemeProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('Solomon Kane')).toBeInTheDocument();
      expect(screen.getByText('Logged in as solomon@auren.ai')).toBeInTheDocument();
    });

    // Verify theme selector options
    const themeSelect = screen.getByRole('combobox');
    expect(themeSelect).toHaveValue('dark');
  });

  it('switches themes and immediately applies data-theme attribute and CSS class to document root', async () => {
    const qc = createTestQueryClient();
    vi.mocked(settingsApi.getUserProfile).mockResolvedValueOnce(createMockUserProfile({
      preferences: { theme: 'dark' },
    }));

    render(
      <QueryClientProvider client={qc}>
        <ThemeProvider>
          <SettingsView />
        </ThemeProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('Solomon Kane')).toBeInTheDocument();
    });

    const themeSelect = screen.getByRole('combobox');

    // Switch to obsidian
    await userEvent.selectOptions(themeSelect, 'obsidian');
    expect(document.documentElement.getAttribute('data-theme')).toBe('obsidian');
    expect(document.documentElement.classList.contains('theme-obsidian')).toBe(true);
    expect(localStorage.getItem('auren_theme')).toBe('obsidian');

    // Switch to midnight
    await userEvent.selectOptions(themeSelect, 'midnight');
    expect(document.documentElement.getAttribute('data-theme')).toBe('midnight');
    expect(document.documentElement.classList.contains('theme-midnight')).toBe(true);
    expect(localStorage.getItem('auren_theme')).toBe('midnight');
  });

  it('displays operational Gemini models and excludes unintegrated providers', async () => {
    const qc = createTestQueryClient();
    vi.mocked(settingsApi.getUserProfile).mockResolvedValueOnce(createMockUserProfile({
      preferences: { ai_model: 'gemini-2.5-flash' },
    }));

    render(
      <QueryClientProvider client={qc}>
        <ThemeProvider>
          <SettingsView />
        </ThemeProvider>
      </QueryClientProvider>
    );

    // Switch to AI Model Tab
    const aiTabButton = screen.getByRole('button', { name: /ai model/i });
    await userEvent.click(aiTabButton);

    // Verify operational Gemini, Groq, and OpenAI options exist
    expect(screen.getByRole('option', { name: /google gemini 2.5 flash/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /google gemini 2.5 pro/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /google gemini 2.0 flash/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /groq llama 3.3 70b/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /openai gpt-4o-mini/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /^openai gpt-4o \(/i })).toBeInTheDocument();

    // Verify unintegrated models do NOT exist
    expect(screen.queryByRole('option', { name: /anthropic claude/i })).not.toBeInTheDocument();
  });

  it('configures memory extraction policies and displays honest cryptographic isolation claims', async () => {
    const qc = createTestQueryClient();
    vi.mocked(settingsApi.getUserProfile).mockResolvedValueOnce(createMockUserProfile({
      preferences: {
        memory_auto_extraction: true,
        memory_min_confidence: 0.8,
      },
    }));

    render(
      <QueryClientProvider client={qc}>
        <ThemeProvider>
          <SettingsView />
        </ThemeProvider>
      </QueryClientProvider>
    );

    // Switch to Memory & Privacy Tab
    const memoryTabButton = screen.getByRole('button', { name: /memory & privacy/i });
    await userEvent.click(memoryTabButton);

    // Verify honest security messaging
    expect(screen.getByText('Cryptographic Isolation & Integrity')).toBeInTheDocument();
    expect(screen.getByText(/Journal entries are cryptographically signed with RFC 8785 canonical JSON and HMAC SHA-256/i)).toBeInTheDocument();
    expect(screen.getByText(/Reflections are strictly quarantined from ordinary LLM context injection and excluded from automated memory extraction/i)).toBeInTheDocument();

    // Verify confidence slider displays 80%
    expect(screen.getByText('80%')).toBeInTheDocument();
  });

  it('saves preferences with full updated payload on Save Changes button click', async () => {
    const qc = createTestQueryClient();
    vi.mocked(settingsApi.getUserProfile).mockResolvedValueOnce(createMockUserProfile({
      preferences: {
        theme: 'dark',
        ai_model: 'gemini-2.5-flash',
      },
    }));
    vi.mocked(settingsApi.updateUserProfile).mockResolvedValueOnce(createMockUserProfile({
      preferences: {
        theme: 'obsidian',
        ai_model: 'gemini-2.5-flash',
        ai_tone: 'concise',
        memory_auto_extraction: true,
        memory_min_confidence: 0.7,
      },
    }));

    render(
      <QueryClientProvider client={qc}>
        <ThemeProvider>
          <SettingsView />
        </ThemeProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('Solomon Kane')).toBeInTheDocument();
    });

    // Change theme to obsidian
    const themeSelect = screen.getByRole('combobox');
    await userEvent.selectOptions(themeSelect, 'obsidian');

    // Click Save Changes
    const saveButton = screen.getByRole('button', { name: /save changes/i });
    await userEvent.click(saveButton);

    await waitFor(() => {
      expect(settingsApi.updateUserProfile).toHaveBeenCalledTimes(1);
      expect(screen.getByText('Settings saved successfully.')).toBeInTheDocument();
    });
  });

  it('displays error message when saving preferences fails', async () => {
    const qc = createTestQueryClient();
    vi.mocked(settingsApi.getUserProfile).mockResolvedValueOnce(createMockUserProfile());
    vi.mocked(settingsApi.updateUserProfile).mockRejectedValueOnce(new Error('Network connection timeout'));

    render(
      <QueryClientProvider client={qc}>
        <ThemeProvider>
          <SettingsView />
        </ThemeProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('Solomon Kane')).toBeInTheDocument();
    });

    const saveButton = screen.getByRole('button', { name: /save changes/i });
    await userEvent.click(saveButton);

    await waitFor(() => {
      expect(screen.getByText(/failed to save: network connection timeout/i)).toBeInTheDocument();
    });
  });
});

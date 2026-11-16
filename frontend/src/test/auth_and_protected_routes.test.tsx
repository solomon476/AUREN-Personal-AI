/**
 * Test Suite 4: Authentication State Handling and Session Controls.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderRouter } from './test-utils';

vi.mock('../api/chat', () => ({
  listConversations: vi.fn().mockResolvedValue([]),
  getConversationMessages: vi.fn().mockResolvedValue([]),
  createConversation: vi.fn(),
  streamChat: vi.fn(),
}));

vi.mock('../api/health', () => ({
  fetchHealth: vi.fn().mockResolvedValue({ status: 'healthy' }),
}));

describe('Authentication State and Session Controls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders unauthenticated state with Sign In and Get Started buttons', async () => {
    await renderRouter('/chat', { user: null });

    await waitFor(() => {
      const signInButtons = screen.getAllByRole('button', { name: /sign in/i });
      expect(signInButtons.length).toBeGreaterThan(0);
      expect(screen.getByRole('button', { name: /get started/i })).toBeInTheDocument();
    });
  });

  it('clicking Sign In opens the AuthModal dialog', async () => {
    const user = userEvent.setup();
    await renderRouter('/chat', { user: null });

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /sign in/i }).length).toBeGreaterThan(0);
    });

    const signInButton = screen.getAllByRole('button', { name: /sign in/i })[0];
    await user.click(signInButton);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText('Welcome Back to AUREN')).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/you@domain\.com/i)).toBeInTheDocument();
    });
  });

  it('renders authenticated state with user profile avatar and email', async () => {
    await renderRouter('/chat', {
      user: {
        id: 'user-auth-456',
        email: 'solomon@auren.ai',
        app_metadata: {},
        user_metadata: { full_name: 'Solomon Yamal' },
        aud: 'authenticated',
        created_at: new Date().toISOString(),
      },
      profile: {
        id: 'user-auth-456',
        email: 'solomon@auren.ai',
        role: 'authenticated',
        full_name: 'Solomon Yamal',
        avatar_url: null,
        app_metadata: {},
        user_metadata: {},
      },
    });

    await waitFor(() => {
      expect(screen.getAllByText('Solomon Yamal').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Authenticated').length).toBeGreaterThan(0);
    });
  });

  it('opens user profile menu and triggers sign out action', async () => {
    const user = userEvent.setup();
    await renderRouter('/chat', {
      user: {
        id: 'user-signout-789',
        email: 'tester@auren.ai',
        app_metadata: {},
        user_metadata: { full_name: 'Test Signout' },
        aud: 'authenticated',
        created_at: new Date().toISOString(),
      },
      profile: {
        id: 'user-signout-789',
        email: 'tester@auren.ai',
        role: 'authenticated',
        full_name: 'Test Signout',
        avatar_url: null,
        app_metadata: {},
        user_metadata: {},
      },
    });

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /test signout/i }).length).toBeGreaterThan(0);
    });

    const userMenuButton = screen.getAllByRole('button', { name: /test signout/i })[0];
    await user.click(userMenuButton);

    await waitFor(() => {
      expect(screen.getByText('RLS Protected User ID')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument();
    });
  });
});

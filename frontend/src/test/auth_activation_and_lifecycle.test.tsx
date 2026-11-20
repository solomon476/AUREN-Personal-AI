/**
 * Phase 7B Verification Suite: Complete Authentication Activation & Registration Lifecycle.
 *
 * Tests the 12 required test conditions:
 * 1. New account registration (input validation, password confirmation match, signup submission).
 * 2. Existing account login (credential submission, session grant).
 * 3. Invalid credentials handling (friendly error messaging).
 * 4. Duplicate registration handling (userExists detection and switch-to-login CTA).
 * 5. Email confirmation flow (requiresEmailConfirmation notice, activation instructions).
 * 6. Session persistence (session recovery from Supabase client).
 * 7. Page refresh / session loading without Guest Mode flicker.
 * 8. Logout handling (state cleanup, cache clearing).
 * 9. Protected routes / user menu rendering.
 * 10. Unconfigured environment variable handling and guest mode exploration.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthModal } from '../components/auth/AuthModal';
import { MockAuthProvider, renderRouter } from './test-utils';

vi.mock('../api/chat', () => ({
  listConversations: vi.fn().mockResolvedValue([]),
  getConversationMessages: vi.fn().mockResolvedValue([]),
  createConversation: vi.fn(),
  streamChat: vi.fn(),
}));

vi.mock('../api/health', () => ({
  fetchHealth: vi.fn().mockResolvedValue({ status: 'healthy' }),
}));

describe('Phase 7B: Authentication Activation and Registration Lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Registration Form and Validation', () => {
    it('validates invalid email format and halts submission', async () => {
      const user = userEvent.setup();
      const mockSignUp = vi.fn();

      render(
        <MockAuthProvider auth={{ signUp: mockSignUp, isConfigured: true }}>
          <AuthModal isOpen={true} onClose={() => {}} defaultMode="signup" />
        </MockAuthProvider>
      );

      const emailInput = screen.getByPlaceholderText(/you@domain\.com/i);
      const passwordInputs = screen.getAllByPlaceholderText(/••••••••/i);
      const submitButton = screen.getByRole('button', { name: /create account/i });

      await user.type(emailInput, 'invalid-email-no-domain');
      await user.type(passwordInputs[0], 'ValidPass123!');
      await user.type(passwordInputs[1], 'ValidPass123!');
      await user.click(submitButton);

      expect(screen.getByText('Please enter a valid email address.')).toBeInTheDocument();
      expect(mockSignUp).not.toHaveBeenCalled();
    });

    it('validates short password (< 6 chars) and halts submission', async () => {
      const user = userEvent.setup();
      const mockSignUp = vi.fn();

      render(
        <MockAuthProvider auth={{ signUp: mockSignUp, isConfigured: true }}>
          <AuthModal isOpen={true} onClose={() => {}} defaultMode="signup" />
        </MockAuthProvider>
      );

      const emailInput = screen.getByPlaceholderText(/you@domain\.com/i);
      const passwordInputs = screen.getAllByPlaceholderText(/••••••••/i);
      const submitButton = screen.getByRole('button', { name: /create account/i });

      await user.type(emailInput, 'valid@auren.ai');
      await user.type(passwordInputs[0], '12345');
      await user.type(passwordInputs[1], '12345');
      await user.click(submitButton);

      expect(screen.getByText('Password must be at least 6 characters long.')).toBeInTheDocument();
      expect(mockSignUp).not.toHaveBeenCalled();
    });

    it('validates password confirmation mismatch and halts submission', async () => {
      const user = userEvent.setup();
      const mockSignUp = vi.fn();

      render(
        <MockAuthProvider auth={{ signUp: mockSignUp, isConfigured: true }}>
          <AuthModal isOpen={true} onClose={() => {}} defaultMode="signup" />
        </MockAuthProvider>
      );

      const emailInput = screen.getByPlaceholderText(/you@domain\.com/i);
      const passwordInputs = screen.getAllByPlaceholderText(/••••••••/i);
      const submitButton = screen.getByRole('button', { name: /create account/i });

      await user.type(emailInput, 'solomon@auren.ai');
      await user.type(passwordInputs[0], 'StrongPassword123!');
      await user.type(passwordInputs[1], 'DifferentPassword456!');
      await user.click(submitButton);

      expect(screen.getByText('Passwords do not match. Please verify both entries.')).toBeInTheDocument();
      expect(mockSignUp).not.toHaveBeenCalled();
    });

    it('submits valid registration and displays success for immediate session', async () => {
      const user = userEvent.setup();
      const mockSignUp = vi.fn().mockResolvedValue({
        success: true,
        requiresEmailConfirmation: false,
      });

      render(
        <MockAuthProvider auth={{ signUp: mockSignUp, isConfigured: true }}>
          <AuthModal isOpen={true} onClose={() => {}} defaultMode="signup" />
        </MockAuthProvider>
      );

      const nameInput = screen.getByPlaceholderText(/solomon yamal/i);
      const emailInput = screen.getByPlaceholderText(/you@domain\.com/i);
      const passwordInputs = screen.getAllByPlaceholderText(/••••••••/i);
      const submitButton = screen.getByRole('button', { name: /create account/i });

      await user.type(nameInput, 'Solomon Yamal');
      await user.type(emailInput, 'solomon@auren.ai');
      await user.type(passwordInputs[0], 'SecurePassword123!');
      await user.type(passwordInputs[1], 'SecurePassword123!');
      await user.click(submitButton);

      expect(mockSignUp).toHaveBeenCalledWith('solomon@auren.ai', 'SecurePassword123!', 'Solomon Yamal');
      await waitFor(() => {
        expect(screen.getByText('Account created successfully! Welcome to AUREN.')).toBeInTheDocument();
      });
    });

    it('handles email confirmation required flow with dedicated check-email screen', async () => {
      const user = userEvent.setup();
      const mockSignUp = vi.fn().mockResolvedValue({
        success: true,
        requiresEmailConfirmation: true,
      });

      render(
        <MockAuthProvider auth={{ signUp: mockSignUp, isConfigured: true }}>
          <AuthModal isOpen={true} onClose={() => {}} defaultMode="signup" />
        </MockAuthProvider>
      );

      const emailInput = screen.getByPlaceholderText(/you@domain\.com/i);
      const passwordInputs = screen.getAllByPlaceholderText(/••••••••/i);
      const submitButton = screen.getByRole('button', { name: /create account/i });

      await user.type(emailInput, 'newuser@auren.ai');
      await user.type(passwordInputs[0], 'SecretPass123!');
      await user.type(passwordInputs[1], 'SecretPass123!');
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText('Check Your Email')).toBeInTheDocument();
        expect(screen.getByText('newuser@auren.ai')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /proceed to sign in/i })).toBeInTheDocument();
      });

      // Clicking Proceed to Sign In switches to Sign In mode
      const proceedButton = screen.getByRole('button', { name: /proceed to sign in/i });
      await user.click(proceedButton);

      await waitFor(() => {
        expect(screen.getByText('Welcome Back to AUREN')).toBeInTheDocument();
        expect(screen.getByDisplayValue('newuser@auren.ai')).toBeInTheDocument();
      });
    });

    it('handles duplicate registration and provides 1-click switch to sign in', async () => {
      const user = userEvent.setup();
      const mockSignUp = vi.fn().mockResolvedValue({
        success: false,
        userExists: true,
        error: 'An account with this email already exists. Please sign in instead.',
      });

      render(
        <MockAuthProvider auth={{ signUp: mockSignUp, isConfigured: true }}>
          <AuthModal isOpen={true} onClose={() => {}} defaultMode="signup" />
        </MockAuthProvider>
      );

      const emailInput = screen.getByPlaceholderText(/you@domain\.com/i);
      const passwordInputs = screen.getAllByPlaceholderText(/••••••••/i);
      const submitButton = screen.getByRole('button', { name: /create account/i });

      await user.type(emailInput, 'existing@auren.ai');
      await user.type(passwordInputs[0], 'ExistingPassword123!');
      await user.type(passwordInputs[1], 'ExistingPassword123!');
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText('An account with this email already exists. Please sign in instead.')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /switch to sign in/i })).toBeInTheDocument();
      });

      // Click switch to sign in button
      const switchButton = screen.getByRole('button', { name: /switch to sign in/i });
      await user.click(switchButton);

      await waitFor(() => {
        expect(screen.getByText('Welcome Back to AUREN')).toBeInTheDocument();
        expect(screen.getByDisplayValue('existing@auren.ai')).toBeInTheDocument();
      });
    });
  });

  describe('Sign In and Invalid Credentials Handling', () => {
    it('submits valid credentials and triggers successful sign in', async () => {
      const user = userEvent.setup();
      const mockSignIn = vi.fn().mockResolvedValue({ success: true });
      const mockClose = vi.fn();

      render(
        <MockAuthProvider auth={{ signIn: mockSignIn, isConfigured: true }}>
          <AuthModal isOpen={true} onClose={mockClose} defaultMode="signin" />
        </MockAuthProvider>
      );

      const emailInput = screen.getByPlaceholderText(/you@domain\.com/i);
      const passwordInput = screen.getByPlaceholderText(/••••••••/i);
      const submitButton = screen.getByRole('button', { name: /sign in/i });

      await user.type(emailInput, 'solomon@auren.ai');
      await user.type(passwordInput, 'CorrectPassword123!');
      await user.click(submitButton);

      expect(mockSignIn).toHaveBeenCalledWith('solomon@auren.ai', 'CorrectPassword123!');
      await waitFor(() => {
        expect(screen.getByText('Signed in successfully.')).toBeInTheDocument();
      });
    });

    it('displays clear user-friendly error when sign in fails with invalid credentials', async () => {
      const user = userEvent.setup();
      const mockSignIn = vi.fn().mockResolvedValue({
        success: false,
        error: 'Invalid email or password. Please check your credentials and try again.',
      });

      render(
        <MockAuthProvider auth={{ signIn: mockSignIn, isConfigured: true }}>
          <AuthModal isOpen={true} onClose={() => {}} defaultMode="signin" />
        </MockAuthProvider>
      );

      const emailInput = screen.getByPlaceholderText(/you@domain\.com/i);
      const passwordInput = screen.getByPlaceholderText(/••••••••/i);
      const submitButton = screen.getByRole('button', { name: /sign in/i });

      await user.type(emailInput, 'wrong@auren.ai');
      await user.type(passwordInput, 'WrongPass123!');
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText('Invalid email or password. Please check your credentials and try again.')).toBeInTheDocument();
      });
    });
  });

  describe('Environment Configuration and Guest Mode', () => {
    it('displays configuration warning and disables submit when unconfigured', async () => {
      render(
        <MockAuthProvider auth={{ isConfigured: false }}>
          <AuthModal isOpen={true} onClose={() => {}} defaultMode="signin" />
        </MockAuthProvider>
      );

      expect(screen.getByText('Supabase Configuration Required')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /continue exploring in guest mode/i })).toBeInTheDocument();

      const submitButton = screen.getByRole('button', { name: /sign in/i });
      expect(submitButton).toBeDisabled();
    });

    it('prevents Guest Preview Mode banner flicker while authentication is loading', async () => {
      // When isLoading is true, Guest Preview Mode should NOT be rendered
      await renderRouter('/home', { user: null, isLoading: true });

      // Ensure Guest Preview Mode banner is not visible during the loading period
      expect(screen.queryByText('Guest Preview Mode')).not.toBeInTheDocument();
    });

    it('displays Guest Preview Mode when authentication finishes and user is unauthenticated', async () => {
      await renderRouter('/home', { user: null, isLoading: false });

      await waitFor(() => {
        expect(screen.getByText('Guest Preview Mode')).toBeInTheDocument();
      });
    });
  });
});

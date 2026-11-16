import type { Page } from '@playwright/test';

/**
 * Helper to initialize an authenticated test session in Playwright.
 * Seeds localStorage before application mount and mocks user profile endpoints.
 */
export async function setupAuthenticatedSession(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      'auren_test_session',
      JSON.stringify({
        user: {
          id: 'test-user-e2e-123',
          email: 'test@auren.ai',
          aud: 'authenticated',
          app_metadata: {},
          user_metadata: { full_name: 'Test User' },
          created_at: '2026-01-01T00:00:00.000Z',
        },
        session: {
          access_token: 'mock-token',
          token_type: 'bearer',
          user: { id: 'test-user-e2e-123' },
        },
        profile: {
          user_id: 'test-user-e2e-123',
          email: 'test@auren.ai',
          full_name: 'Test User',
          is_active: true,
        },
      })
    );
  });

  await page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'test-user-e2e-123',
        email: 'test@auren.ai',
        role: 'authenticated',
        full_name: 'Test User',
        avatar_url: null,
        app_metadata: {},
        user_metadata: {},
      }),
    });
  });
}


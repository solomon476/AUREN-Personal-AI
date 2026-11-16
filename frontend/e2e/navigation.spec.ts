import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession } from './helpers';

test.describe('Application Navigation & Routing', () => {
  test('application loads and redirects root route to /chat', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/chat/);
    await expect(page.getByRole('link', { name: /auren/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /ai assistant/i })).toBeVisible();
    await expect(page.getByText('System & Database')).toBeVisible();
  });

  test('direct conversation route loads correctly', async ({ page }) => {
    await setupAuthenticatedSession(page);

    // Intercept backend API to return mock thread
    await page.route('**/api/v1/chat/conversations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'direct-conv-123',
            title: 'Direct Navigation Thread',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            message_count: 1,
          },
        ]),
      });
    });

    await page.route('**/api/v1/chat/conversations/direct-conv-123/messages', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'msg-direct-1',
            conversation_id: 'direct-conv-123',
            role: 'assistant',
            content: 'Loaded directly from URL.',
            created_at: new Date().toISOString(),
          },
        ]),
      });
    });

    await page.goto('/chat/direct-conv-123');
    await expect(page).toHaveURL(/\/chat\/direct-conv-123/);
    await expect(page.getByRole('heading', { name: /direct navigation thread/i })).toBeVisible();
    await expect(page.getByText('Loaded directly from URL.')).toBeVisible();
  });

  test('browser refresh preserves intended route', async ({ page }) => {
    await page.goto('/system');
    await expect(page).toHaveURL(/\/system/);
    await expect(page.getByText('PostgreSQL Schemas & RLS Policies')).toBeVisible();

    await page.reload();
    await expect(page).toHaveURL(/\/system/);
    await expect(page.getByText('PostgreSQL Schemas & RLS Policies')).toBeVisible();
  });

  test('browser back and forward history navigation works', async ({ page }) => {
    await page.goto('/chat');
    await expect(page).toHaveURL(/\/chat/);

    await page.getByRole('link', { name: /system & database/i }).click();
    await expect(page).toHaveURL(/\/system/);

    await page.getByRole('link', { name: /long-term memory/i }).click();
    await expect(page).toHaveURL(/\/memories/);

    // Back to /system
    await page.goBack();
    await expect(page).toHaveURL(/\/system/);
    await expect(page.getByText('PostgreSQL Schemas & RLS Policies')).toBeVisible();

    // Forward to /memories
    await page.goForward();
    await expect(page).toHaveURL(/\/memories/);
    await expect(page.getByText('Long-term Memory & Epistemic Verification')).toBeVisible();
  });

  test('unknown routes display 404 Page Not Found with return action', async ({ page }) => {
    await page.goto('/unknown-destination-404');
    await expect(page.getByText('Page Not Found')).toBeVisible();
    await expect(page.getByText(/The requested destination does not exist/i)).toBeVisible();

    await page.getByRole('link', { name: /return to ai chat/i }).click();
    await expect(page).toHaveURL(/\/chat/);
  });
});

import { test, expect } from '@playwright/test';

test.describe('Authentication State & Session Controls', () => {
  test('unauthenticated visitor sees sign in controls without premature redirect', async ({ page }) => {
    await page.goto('/chat');
    await expect(page).toHaveURL(/\/chat/);
    await expect(page.getByRole('button', { name: /sign in/i }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /get started/i })).toBeVisible();
  });

  test('clicking Sign In opens AuthModal dialog with email & password form', async ({ page }) => {
    await page.goto('/chat');
    await page.getByRole('button', { name: /sign in/i }).first().click();

    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByText('Welcome Back to AUREN')).toBeVisible();
    await expect(page.getByPlaceholder(/you@domain\.com/i)).toBeVisible();

    // Close modal via close button
    await page.getByRole('button', { name: /^close$/i }).click();
    await expect(page.getByRole('dialog')).not.toBeVisible();
  });
});

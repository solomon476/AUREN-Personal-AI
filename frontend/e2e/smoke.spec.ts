import { test, expect } from '@playwright/test';

/**
 * Smoke E2E Test Suite for AUREN.
 * Verifies core navigation, application shell initialization, and routing.
 */
test.describe('AUREN Smoke Suite', () => {
  test('initializes application and redirects to /chat', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/chat/);
    await expect(page.getByText('AUREN')).toBeVisible();
    await expect(page.getByText('Phase 3C.1')).toBeVisible();
  });

  test('navigates to system health and database schema matrix', async ({ page }) => {
    await page.goto('/chat');
    await page.getByRole('link', { name: /system & database/i }).click();
    await expect(page).toHaveURL(/\/system/);
    await expect(page.getByText('FastAPI Backend & Streaming Health')).toBeVisible();
  });

  test('navigates to long-term memory roadmap placeholder', async ({ page }) => {
    await page.goto('/chat');
    await page.getByRole('link', { name: /long-term memory/i }).click();
    await expect(page).toHaveURL(/\/memories/);
    await expect(page.getByText('Long-term Memory & Epistemic Verification')).toBeVisible();
  });
});

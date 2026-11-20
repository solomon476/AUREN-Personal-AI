import { test, expect } from '@playwright/test';

/**
 * Smoke E2E Test Suite for AUREN.
 * Verifies core navigation, application shell initialization, and routing.
 */
test.describe('AUREN Smoke Suite', () => {
  test('initializes application and redirects to /home', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/home/);
    await expect(page.getByRole('link', { name: /auren/i }).first()).toBeVisible();
    await expect(page.getByText('Personal AI', { exact: true })).toBeVisible();
  });

  test('navigates to system health and database schema matrix', async ({ page }) => {
    await page.goto('/chat');
    await page.getByRole('link', { name: /system & database/i }).click();
    await expect(page).toHaveURL(/\/system/);
    await expect(page.getByText('FastAPI Backend & Streaming Health')).toBeVisible();
  });

  test('navigates to long-term memory explorer', async ({ page }) => {
    await page.goto('/chat');
    await page.getByRole('link', { name: /long-term memory/i }).click();
    await expect(page).toHaveURL(/\/memories/);
    await expect(page.getByRole('heading', { name: /long-term memory explorer/i })).toBeVisible();
  });
});

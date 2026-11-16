import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession } from './helpers';

test.describe('Conversation Lifecycle: Rename & Delete', () => {
  test('opens existing conversation, renames it, and deletes it cleanly', async ({ page }) => {
    await setupAuthenticatedSession(page);

    let currentTitle = 'Initial Thread Title';
    let conversations = [
      {
        id: 'conv-e2e-1',
        title: currentTitle,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 2,
      },
    ];

    // Intercept GET /conversations
    await page.route('**/api/v1/chat/conversations', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(conversations),
        });
      } else {
        await route.continue();
      }
    });

    // Intercept messages
    await page.route('**/api/v1/chat/conversations/conv-e2e-1/messages', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'm1',
            conversation_id: 'conv-e2e-1',
            role: 'user',
            content: 'Hello AUREN',
            created_at: new Date().toISOString(),
          },
          {
            id: 'm2',
            conversation_id: 'conv-e2e-1',
            role: 'assistant',
            content: 'Hello! Ready to assist you.',
            created_at: new Date().toISOString(),
          },
        ]),
      });
    });

    // Intercept PATCH and DELETE for /conversations/conv-e2e-1
    await page.route('**/api/v1/chat/conversations/conv-e2e-1', async (route) => {
      if (route.request().method() === 'PATCH') {
        const payload = JSON.parse(route.request().postData() || '{}');
        currentTitle = payload.title;
        conversations[0].title = currentTitle;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(conversations[0]),
        });
      } else if (route.request().method() === 'DELETE') {
        conversations = [];
        await route.fulfill({
          status: 204,
        });
      } else {
        await route.continue();
      }
    });

    // 1. Navigate to thread
    await page.goto('/chat/conv-e2e-1');
    await expect(page.getByText('Initial Thread Title').first()).toBeVisible();

    // 2. Open Rename Modal
    await page.getByRole('button', { name: /rename conversation/i }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByText('Rename Conversation')).toBeVisible();

    const titleInput = page.getByLabel(/title/i);
    await titleInput.fill('Updated E2E Project Roadmap');
    await page.getByRole('button', { name: /save/i }).click();

    // 3. Verify Renamed Title is displayed
    await expect(page.getByText('Updated E2E Project Roadmap').first()).toBeVisible();

    // 4. Open Delete Modal
    await page.getByRole('button', { name: /delete conversation/i }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByText('Are you sure you want to delete this conversation?')).toBeVisible();

    // 5. Confirm Deletion in Dialog
    await page.getByRole('dialog').getByRole('button', { name: /delete conversation/i }).click();

    // 6. Verify Redirected to /chat and thread removed
    await expect(page).toHaveURL(/\/chat$/);
    await expect(page.getByText('Updated E2E Project Roadmap')).not.toBeVisible();
  });
});
